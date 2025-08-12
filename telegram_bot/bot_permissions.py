#!/usr/bin/env python3
"""
Модуль для проверки прав доступа пользователей Telegram Bot
"""

import logging
from typing import Optional, List
from bot_database import TelegramBotDB

logger = logging.getLogger(__name__)

def check_user_permission(telegram_id: int, action: str, bot_db: TelegramBotDB) -> bool:
    """
    Проверка разрешения пользователя на выполнение действия
    
    Args:
        telegram_id: ID пользователя Telegram
        action: Тип действия ('read', 'write', 'reset_alarms')
        bot_db: Экземпляр базы данных бота
        
    Returns:
        bool: True если действие разрешено
    """
    try:
        # Получаем пользователя
        user = bot_db.get_user(telegram_id)
        if not user:
            logger.warning(f"⚠️ Пользователь {telegram_id} не найден в базе")
            return False
        
        # Проверяем активность
        if not user.get('is_active', True):
            logger.warning(f"🔒 Пользователь {telegram_id} деактивирован")
            return False
        
        # Получаем уровень доступа
        access_level = user.get('access_level', 'user')
        
        # Получаем разрешения для уровня доступа
        permissions = bot_db.get_access_permissions(access_level)
        if not permissions:
            logger.error(f"❌ Не найдены разрешения для уровня {access_level}")
            return False
        
        # Проверяем конкретное действие
        if action == 'read':
            return permissions.get('can_read', False)
        elif action == 'write':
            return permissions.get('can_write', False)
        elif action == 'reset_alarms':
            return permissions.get('can_reset_alarms', False)
        else:
            logger.warning(f"⚠️ Неизвестное действие: {action}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка проверки прав доступа {telegram_id}: {e}")
        return False

def check_command_rate_limit(telegram_id: int, bot_db: TelegramBotDB) -> tuple[bool, str]:
    """
    Проверка лимита команд пользователя
    
    Returns:
        tuple: (разрешено, сообщение)
    """
    try:
        # Получаем пользователя и его уровень доступа
        user = bot_db.get_user(telegram_id)
        if not user:
            return False, "Пользователь не найден"
        
        access_level = user.get('access_level', 'user')
        permissions = bot_db.get_access_permissions(access_level)
        
        if not permissions:
            return False, "Разрешения не найдены"
        
        # Получаем лимит команд в час
        max_commands_per_hour = permissions.get('max_commands_per_hour', 5)
        
        # Считаем команды за последний час
        commands_last_hour = bot_db.get_user_command_count_last_hour(telegram_id)
        
        if commands_last_hour >= max_commands_per_hour:
            return False, f"Превышен лимит команд ({commands_last_hour}/{max_commands_per_hour} в час)"
        
        return True, f"Доступно команд: {max_commands_per_hour - commands_last_hour}/{max_commands_per_hour}"
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки лимита команд {telegram_id}: {e}")
        return False, "Ошибка проверки лимита"

def get_user_access_level(telegram_id: int, bot_db: TelegramBotDB) -> str:
    """Получение уровня доступа пользователя"""
    return bot_db.get_user_access_level(telegram_id)

def get_allowed_registers(telegram_id: int, bot_db: TelegramBotDB) -> List[str]:
    """Получение списка разрешённых регистров для пользователя"""
    try:
        user = bot_db.get_user(telegram_id)
        if not user:
            return []
        
        access_level = user.get('access_level', 'user')
        permissions = bot_db.get_access_permissions(access_level)
        
        if permissions and permissions.get('allowed_registers'):
            return permissions['allowed_registers']
        
        return []
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения разрешённых регистров {telegram_id}: {e}")
        return []

def can_access_register(telegram_id: int, register: str, bot_db: TelegramBotDB) -> bool:
    """Проверка доступа к конкретному регистру"""
    try:
        allowed_registers = get_allowed_registers(telegram_id, bot_db)
        
        # Проверяем точное совпадение
        if register in allowed_registers:
            return True
        
        # Проверяем диапазоны (например "0x0100-0x010F")
        for allowed in allowed_registers:
            if '-' in allowed:
                try:
                    start, end = allowed.split('-')
                    start_addr = int(start, 16)
                    end_addr = int(end, 16)
                    register_addr = int(register, 16)
                    
                    if start_addr <= register_addr <= end_addr:
                        return True
                except ValueError:
                    continue
        
        return False
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки доступа к регистру {register}: {e}")
        return False

def get_user_permissions_info(telegram_id: int, bot_db: TelegramBotDB) -> dict:
    """Получение полной информации о правах пользователя"""
    try:
        user = bot_db.get_user(telegram_id)
        if not user:
            return {}
        
        access_level = user.get('access_level', 'user')
        permissions = bot_db.get_access_permissions(access_level)
        
        if not permissions:
            return {}
        
        # Получаем статистику команд
        commands_last_hour = bot_db.get_user_command_count_last_hour(telegram_id)
        max_commands = permissions.get('max_commands_per_hour', 5)
        
        return {
            'access_level': access_level,
            'description': permissions.get('description', ''),
            'can_read': permissions.get('can_read', False),
            'can_write': permissions.get('can_write', False),
            'can_reset_alarms': permissions.get('can_reset_alarms', False),
            'allowed_registers': permissions.get('allowed_registers', []),
            'commands_used': commands_last_hour,
            'commands_limit': max_commands,
            'commands_remaining': max(0, max_commands - commands_last_hour)
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения информации о правах {telegram_id}: {e}")
        return {}

def is_admin_user(telegram_id: int, admin_list: List[int] = None) -> bool:
    """Проверка является ли пользователь администратором"""
    if not admin_list:
        admin_list = []
    
    return telegram_id in admin_list

def promote_user(telegram_id: int, new_access_level: str, promoted_by: int, 
                bot_db: TelegramBotDB, admin_list: List[int] = None) -> tuple[bool, str]:
    """
    Повышение уровня доступа пользователя
    
    Args:
        telegram_id: ID пользователя для повышения
        new_access_level: Новый уровень доступа
        promoted_by: ID пользователя, который повышает
        bot_db: База данных
        admin_list: Список ID администраторов
        
    Returns:
        tuple: (успех, сообщение)
    """
    try:
        # Проверяем права промоутера
        if not is_admin_user(promoted_by, admin_list):
            return False, "У вас нет прав для изменения уровня доступа"
        
        # Проверяем валидность нового уровня
        valid_levels = ['user', 'operator', 'admin', 'engineer']
        if new_access_level not in valid_levels:
            return False, f"Недопустимый уровень доступа: {new_access_level}"
        
        # Проверяем существование пользователя
        user = bot_db.get_user(telegram_id)
        if not user:
            return False, "Пользователь не найден"
        
        # Обновляем уровень доступа
        success = bot_db.set_user_access_level(telegram_id, new_access_level)
        
        if success:
            old_level = user.get('access_level', 'user')
            logger.info(f"🔝 Пользователь {telegram_id} повышен с {old_level} до {new_access_level} пользователем {promoted_by}")
            return True, f"Уровень доступа изменён: {old_level} → {new_access_level}"
        else:
            return False, "Ошибка обновления уровня доступа"
            
    except Exception as e:
        logger.error(f"❌ Ошибка повышения пользователя {telegram_id}: {e}")
        return False, f"Ошибка: {str(e)}"

# =============================================================================
# ДЕКОРАТОРЫ ДЛЯ ПРОВЕРКИ ПРАВ
# =============================================================================

def require_permission(action: str):
    """Декоратор для проверки прав доступа"""
    def decorator(func):
        async def wrapper(self, update, context):
            user_id = update.effective_user.id
            
            if not check_user_permission(user_id, action, self.bot_db):
                await update.message.reply_text(f"❌ У вас нет прав для действия: {action}")
                return
            
            # Проверяем лимит команд для write операций
            if action in ['write', 'reset_alarms']:
                allowed, message = check_command_rate_limit(user_id, self.bot_db)
                if not allowed:
                    await update.message.reply_text(f"⏰ {message}")
                    return
            
            return await func(self, update, context)
        return wrapper
    return decorator

def admin_only(admin_list: List[int]):
    """Декоратор только для администраторов"""
    def decorator(func):
        async def wrapper(self, update, context):
            user_id = update.effective_user.id
            
            if not is_admin_user(user_id, admin_list):
                await update.message.reply_text("❌ Эта команда доступна только администраторам")
                return
            
            return await func(self, update, context)
        return wrapper
    return decorator

# =============================================================================
# ТЕСТИРОВАНИЕ МОДУЛЯ
# =============================================================================

def test_permissions():
    """Тест системы прав доступа"""
    print("🧪 Тестирование системы прав доступа")
    print("=" * 40)
    
    try:
        db = TelegramBotDB()
        test_user_id = 123456789
        
        # Регистрируем тестового пользователя
        db.register_user(test_user_id, "test_user", "Test", "User", "operator")
        
        print("1. Тест проверки прав чтения...")
        can_read = check_user_permission(test_user_id, "read", db)
        print(f"   Права чтения: {'✅' if can_read else '❌'}")
        
        print("2. Тест проверки прав записи...")
        can_write = check_user_permission(test_user_id, "write", db)
        print(f"   Права записи: {'✅' if can_write else '❌'}")
        
        print("3. Тест проверки прав сброса аварий...")
        can_reset = check_user_permission(test_user_id, "reset_alarms", db)
        print(f"   Права сброса аварий: {'✅' if can_reset else '❌'}")
        
        print("4. Тест лимита команд...")
        allowed, message = check_command_rate_limit(test_user_id, db)
        print(f"   Лимит команд: {'✅' if allowed else '❌'} - {message}")
        
        print("5. Тест информации о правах...")
        info = get_user_permissions_info(test_user_id, db)
        print(f"   Уровень доступа: {info.get('access_level')}")
        print(f"   Описание: {info.get('description')}")
        print(f"   Остаток команд: {info.get('commands_remaining')}")
        
        print("\n✅ Все тесты прав доступа пройдены!")
        
    except Exception as e:
        print(f"❌ Ошибка тестирования прав: {e}")

if __name__ == "__main__":
    test_permissions()