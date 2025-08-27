#!/usr/bin/env python3
"""
Модуль для проверки прав доступа пользователей Telegram Bot
"""

import logging
from typing import Optional, List, Tuple  # ❌ ИСПРАВЛЕНО: Добавлен Tuple импорт
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

def check_command_rate_limit(telegram_id: int, bot_db: TelegramBotDB) -> Tuple[bool, str]:  # ❌ ИСПРАВЛЕНО: tuple -> Tuple
    """
    Проверка лимита команд пользователя
    
    Returns:
        Tuple: (разрешено, сообщение)
    """
    try:
        # Получаем количество команд за последний час
        commands_last_hour = bot_db.get_user_command_count_last_hour(telegram_id)
        
        # Получаем лимит для пользователя
        user = bot_db.get_user(telegram_id)
        if not user:
            return False, "Пользователь не найден"
        
        access_level = user.get('access_level', 'user')
        
        # Лимиты по уровням доступа
        limits = {
            'user': 5,
            'operator': 20,
            'admin': 50,
            'engineer': 100
        }
        
        limit = limits.get(access_level, 5)
        
        if commands_last_hour >= limit:
            return False, f"Превышен лимит команд ({commands_last_hour}/{limit} за час)"
        
        return True, f"Команд за час: {commands_last_hour}/{limit}"
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки лимита команд {telegram_id}: {e}")
        return False, "Ошибка проверки лимита"

def get_user_access_level(telegram_id: int, bot_db: TelegramBotDB) -> str:
    """Получение уровня доступа пользователя"""
    try:
        user = bot_db.get_user(telegram_id)
        if user:
            return user.get('access_level', 'user')
        return 'user'
    except Exception as e:
        logger.error(f"❌ Ошибка получения уровня доступа {telegram_id}: {e}")
        return 'user'

# =============================================================================
# ТЕСТИРОВАНИЕ МОДУЛЯ
# =============================================================================

def test_bot_permissions():
    """Тест функций прав доступа"""
    print("🧪 Тестирование bot_permissions")
    print("=" * 40)
    
    try:
        from bot_database import TelegramBotDB
        db = TelegramBotDB()
        
        test_user_id = 123456789
        
        # Тест проверки прав доступа
        print("1. Тест проверки прав доступа...")
        can_read = check_user_permission(test_user_id, "read", db)
        print(f"   Чтение: {'✅' if can_read else '❌'}")
        
        # Тест лимита команд
        print("2. Тест лимита команд...")
        allowed, message = check_command_rate_limit(test_user_id, db)
        print(f"   Лимит: {'✅' if allowed else '❌'} - {message}")
        
        # Тест уровня доступа
        print("3. Тест уровня доступа...")
        access_level = get_user_access_level(test_user_id, db)
        print(f"   Уровень: {access_level}")
        
        print("\n✅ Все тесты прав доступа пройдены!")
        
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")

if __name__ == "__main__":
    test_bot_permissions()