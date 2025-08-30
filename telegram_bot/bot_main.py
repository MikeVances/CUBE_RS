#!/usr/bin/env python3
"""
Telegram Bot для управления системой КУБ-1063
Использует централизованный конфиг-менеджер для всех настроек.
"""

import os
import sys
import json
import logging
import asyncio
import sqlite3
from typing import Dict, Any
from datetime import datetime

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Импорт централизованного конфиг-менеджера и безопасности
try:
    from core.config_manager import get_config
    from core.security_manager import log_security_event
    from core.log_filter import setup_secure_logging
    config = get_config()
    SECURITY_AVAILABLE = True
except ImportError as e:
    if "security_manager" in str(e) or "log_filter" in str(e):
        from core.config_manager import get_config
        config = get_config()
        SECURITY_AVAILABLE = False
        logging.warning("⚠️ Модули безопасности недоступны - логирование безопасности отключено")
    else:
        logging.error("❌ Не удалось импортировать ConfigManager. Убедитесь что установлен PyYAML.")
        sys.exit(1)

# Telegram Bot imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Наши модули
from bot_database import TelegramBotDB
from bot_permissions import check_user_permission, check_command_rate_limit, get_user_access_level
from bot_utils import (
    format_sensor_data, format_system_stats, 
    build_main_menu, build_confirmation_menu, build_back_menu, build_stats_menu,
    send_typing_action, send_upload_action,
    error_message, success_message, info_message, warning_message, loading_message,
    truncate_text
)

# Настройка логирования из конфига
log_file = config.config_dir / "logs" / "telegram.log"
log_file.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=getattr(logging, config.system.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# КРИТИЧНО: Настройка безопасного логирования для предотвращения утечки токенов
if SECURITY_AVAILABLE:
    # Устанавливаем фильтр секретов для всех логгеров
    security_filter = setup_secure_logging()
    logger.info("🔐 Установлен фильтр безопасности для логов")
else:
    # Fallback: просто отключаем подробное логирование 
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.WARNING)
    logging.getLogger("telegram.request").setLevel(logging.WARNING)

class KUBTelegramBot:
    """Telegram Bot для управления КУБ-1063 с централизованной конфигурацией"""
    
    def __init__(self, token: str):
        self.token = token
        self.config = config  # Используем глобальный конфиг-менеджер
        
        # НЕ создаем UnifiedKUBSystem - работаем через базы данных
        self.kub_system = None
        self.bot_db = TelegramBotDB()
        
        # Telegram Application
        self.application = None
        
        logger.info(f"✅ Загружено {len(self.config.telegram.admin_users)} администраторов")
        logger.info("🤖 KUBTelegramBot с UX улучшениями инициализирован")

    # =======================================================================
    # РАБОТА С ДАННЫМИ ЧЕРЕЗ SQLite (вместо прямого RS485)
    # =======================================================================
    
    def get_current_data_from_db(self):
        """Читаем текущие данные из SQLite (заполняется основной системой)"""
        try:
            import sqlite3
            with sqlite3.connect("kub_data.db") as conn:
                cursor = conn.execute("""
                    SELECT temp_inside, temp_target, humidity, co2, nh3, pressure,
                           ventilation_level, ventilation_target, active_alarms,
                           active_warnings, updated_at 
                    FROM latest_data WHERE id=1
                """)
                row = cursor.fetchone()
                if row:
                    return {
                        'temp_inside': row[0] if row[0] else 0,  # Данные уже конвертированы Gateway
                        'temp_target': row[1] if row[1] else 0,
                        'humidity': row[2] if row[2] else 0,
                        'co2': row[3] if row[3] else 0,
                        'nh3': row[4] if row[4] else 0,
                        'pressure': row[5] if row[5] else 0,
                        'ventilation_level': row[6] if row[6] else 0,
                        'ventilation_target': row[7] if row[7] else 0,
                        'active_alarms': row[8] if row[8] else 0,
                        'active_warnings': row[9] if row[9] else 0,
                        'updated_at': row[10],
                        'connection_status': 'connected' if row[10] else 'disconnected'
                    }
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка чтения данных из БД: {e}")
            return None

    def add_write_command_to_db(self, register: int, value: int, user_info: str):
        """Добавляем команду записи в очередь (выполнит основная система)"""
        try:
            import sqlite3
            import uuid
            from datetime import datetime
            
            command_id = str(uuid.uuid4())[:8]
            
            with sqlite3.connect("kub_commands.db") as conn:
                conn.execute("""
                    INSERT INTO write_commands 
                    (id, register, value, user_info, created_at, status, priority)
                    VALUES (?, ?, ?, ?, ?, 'pending', 1)
                """, (command_id, register, value, user_info, datetime.now().isoformat()))
                conn.commit()
            
            logger.info(f"📝 Команда записи добавлена: reg=0x{register:04X}, val={value}, id={command_id}")
            return True, command_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка добавления команды: {e}")
            return False, str(e)

    # =======================================================================
    # ОБРАБОТЧИКИ КОМАНД
    # =======================================================================
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start - обработка приглашений и защита от незарегистрированных пользователей"""
        user = update.effective_user
        
        # Логирование события безопасности
        if SECURITY_AVAILABLE:
            log_security_event("BOT_START_ATTEMPT", user_id=user.id, details={
                "username": user.username,
                "first_name": user.first_name,
                "has_args": bool(context.args)
            })
        
        # Показываем печатание
        await send_typing_action(update, context)
        
        # Проверяем, есть ли приглашение в сообщении
        invitation_code = None
        if context.args:
            # Ищем код приглашения в формате invite_XXXXXXXX
            for arg in context.args:
                if arg.startswith('invite_'):
                    invitation_code = arg.replace('invite_', '')
                    break
        
        # Проверяем, зарегистрирован ли пользователь
        existing_user = self.bot_db.get_user(user.id)
        
        if existing_user:
            # Пользователь уже зарегистрирован - показываем главное меню
            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_main_menu(access_level)
            
            welcome_text = (
                f"👋 С возвращением, {user.first_name or user.username}!\n\n"
                f"**КУБ-1063 Control Bot**\n"
                f"🔐 Ваш уровень доступа: **{access_level}**\n\n"
                "Выберите действие в меню ниже ⬇️"
            )
            
            await update.message.reply_text(
                welcome_text, 
                reply_markup=menu, 
                parse_mode="Markdown"
            )
            
            self.bot_db.log_user_command(user.id, "start", None, True)
            return
        
        # Новый пользователь - требуется приглашение
        if not invitation_code:
            # Нет приглашения - отклоняем доступ
            await update.message.reply_text(
                "🔒 **Доступ ограничен**\n\n"
                "Для использования бота необходимо приглашение.\n"
                "Обратитесь к администратору системы КУБ-1063 за ссылкой-приглашением.\n\n"
                "📋 **Как получить доступ:**\n"
                "1. Попросите администратора создать приглашение\n"
                "2. Перейдите по ссылке-приглашению\n"
                "3. Получите доступ к системе",
                parse_mode="Markdown"
            )
            return
        
        # Есть код приглашения - проверяем его
        try:
            import sqlite3
            import datetime
            
            conn = sqlite3.connect('kub_commands.db')
            cursor = conn.cursor()
            
            # Ищем приглашение
            cursor.execute('''
                SELECT invitation_code, invited_by, access_level, expires_at, used_by
                FROM user_invitations 
                WHERE invitation_code = ?
            ''', (invitation_code,))
            
            invitation = cursor.fetchone()
            
            if not invitation:
                conn.close()
                await update.message.reply_text(
                    "❌ **Недействительное приглашение**\n\n"
                    "Код приглашения не найден или устарел.\n"
                    "Попросите новое приглашение у администратора.",
                    parse_mode="Markdown"
                )
                return
            
            code, invited_by, level, expires_at_str, used_by = invitation
            
            # Проверяем, не использовано ли приглашение
            if used_by:
                conn.close()
                await update.message.reply_text(
                    "❌ **Приглашение уже использовано**\n\n"
                    "Это приглашение уже было активировано.\n"
                    "Попросите новое приглашение у администратора.",
                    parse_mode="Markdown"
                )
                return
            
            # Проверяем срок действия
            expires_at = datetime.datetime.fromisoformat(expires_at_str)
            if datetime.datetime.now() > expires_at:
                conn.close()
                await update.message.reply_text(
                    "⏰ **Приглашение истекло**\n\n"
                    "Срок действия приглашения истёк.\n"
                    "Попросите новое приглашение у администратора.",
                    parse_mode="Markdown"
                )
                return
            
            # Приглашение действительно - регистрируем пользователя
            self.bot_db.register_user(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                access_level=level
            )
            
            # Отмечаем приглашение как использованное
            cursor.execute('''
                UPDATE user_invitations 
                SET used_by = ?, used_at = ?
                WHERE invitation_code = ?
            ''', (user.id, datetime.datetime.now().isoformat(), invitation_code))
            
            conn.commit()
            conn.close()
            
            # Получаем информацию о пригласившем
            inviter_info = self.bot_db.get_user(invited_by)
            inviter_name = inviter_info.get('username', 'Администратор') if inviter_info else 'Администратор'
            
            menu = build_main_menu(level)
            
            level_names = {
                'user': '👤 User (Пользователь)',
                'operator': '⚙️ Operator (Оператор)',
                'engineer': '🔧 Engineer (Инженер)'
            }
            
            welcome_text = (
                f"🎉 **Добро пожаловать в КУБ-1063 Control Bot!**\n\n"
                f"👋 Привет, {user.first_name or user.username}!\n\n"
                f"✅ **Регистрация успешна**\n"
                f"🔐 **Уровень доступа:** {level_names.get(level, level)}\n"
                f"👤 **Приглашение от:** @{inviter_name}\n\n"
                f"**Ваши возможности:**\n"
                f"• Мониторинг датчиков КУБ-1063\n"
                f"• Просмотр текущих данных\n"
                f"• Управление системой (по уровню доступа)\n\n"
                "Выберите действие в меню ниже ⬇️"
            )
            
            await update.message.reply_text(
                welcome_text, 
                reply_markup=menu, 
                parse_mode="Markdown"
            )
            
            self.bot_db.log_user_command(user.id, "start", f"invite_{invitation_code}", True)
            logger.info(f"✅ Новый пользователь {user.id} (@{user.username}) зарегистрирован по приглашению {invitation_code}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки приглашения: {e}")
            await update.message.reply_text(
                error_message(f"Ошибка обработки приглашения: {str(e)}"),
                parse_mode="Markdown"
            )
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status - показать текущие данные"""
        user = update.effective_user

        # Проверяем права доступа
        if not check_user_permission(user.id, "read", self.bot_db):
            await update.message.reply_text(
                error_message("У вас нет прав для чтения данных"), 
                parse_mode="Markdown"
            )
            return

        try:
            await send_typing_action(update, context)
            
            # Читаем данные из SQLite
            data = self.get_current_data_from_db()
            
            if data:
                status_text = format_sensor_data(data)
            else:
                status_text = error_message(
                    "Нет данных от КУБ-1063\n\n"
                    "Запустите основную систему:\n"
                    "`python tools/start_all_services.py`"
                )
            
            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_main_menu(access_level)
            
            status_text = truncate_text(status_text, 4000)
            
            await update.message.reply_text(
                status_text,
                parse_mode='Markdown',
                reply_markup=menu
            )
            
            self.bot_db.log_user_command(user.id, "read", None, True)
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса: {e}")
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await update.message.reply_text(
                error_message(f"Ошибка получения данных: {str(e)}"),
                reply_markup=back_menu,
                parse_mode="Markdown"
            )

    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /stats - статистика системы"""
        user = update.effective_user

        if not check_user_permission(user.id, "read", self.bot_db):
            await update.message.reply_text(
                error_message("У вас нет прав для чтения статистики"),
                parse_mode="Markdown"
            )
            return

        try:
            await send_typing_action(update, context)
            
            # Простая статистика без UnifiedKUBSystem
            stats_text = "📈 **СТАТИСТИКА СИСТЕМЫ КУБ-1063**\n\n"
            
            # Получаем информацию из базы
            data = self.get_current_data_from_db()
            if data:
                stats_text += f"🔄 **Последнее обновление:** `{data.get('updated_at', 'неизвестно')}`\n"
                stats_text += f"🌡️ **Текущая температура:** `{data.get('temp_inside', 0):.1f}°C`\n"
                stats_text += f"💧 **Влажность:** `{data.get('humidity', 0):.1f}%`\n"
                stats_text += f"🚨 **Активные аварии:** `{data.get('active_alarms', 0)}`\n"
            else:
                stats_text += "❌ Нет данных от основной системы\n"
            
            # Получаем статистику пользователя
            user_stats = self.bot_db.get_user_stats(user.id)
            
            if user_stats:
                stats_text += f"\n**👤 ВАША СТАТИСТИКА:**\n"
                stats_text += f"• Всего команд: `{user_stats.get('total_commands', 0)}`\n"
                stats_text += f"• За сегодня: `{user_stats.get('commands_today', 0)}`\n"
                stats_text += f"• Успешность: `{user_stats.get('success_rate', 0):.1f}%`\n"
            
            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_stats_menu(access_level)
            
            stats_text = truncate_text(stats_text, 4000)
            
            await update.message.reply_text(
                stats_text,
                parse_mode='Markdown',
                reply_markup=menu
            )
            
            self.bot_db.log_user_command(user.id, "stats", None, True)
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            await update.message.reply_text(
                error_message(f"Ошибка получения статистики: {str(e)}"),
                parse_mode="Markdown"
            )

    # =======================================================================
    # УПРАВЛЕНИЕ РОЛЯМИ ПОЛЬЗОВАТЕЛЕЙ
    # =======================================================================
    
    async def cmd_promote(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /promote - повышение пользователя (только админы)"""
        user = update.effective_user
        
        # Логирование попытки изменения прав
        if SECURITY_AVAILABLE:
            log_security_event("PRIVILEGE_ESCALATION_ATTEMPT", user_id=user.id, details={
                "username": user.username,
                "args": context.args,
                "is_admin": user.id in self.config.telegram.admin_users
            }, level="WARNING" if user.id not in self.config.telegram.admin_users else "INFO")
        
        # Проверяем права админа
        if user.id not in self.config.telegram.admin_users:
            await update.message.reply_text("❌ У вас нет прав администратора")
            return
        
        try:
            args = context.args
            if len(args) < 2:
                await update.message.reply_text(
                    "📖 Использование: `/promote @username уровень`\n\n"
                    "Доступные уровни:\n"
                    "• `user` - только чтение\n"
                    "• `operator` - чтение + сброс аварий\n"
                    "• `admin` - полный доступ\n"
                    "• `engineer` - максимальный доступ",
                    parse_mode="Markdown"
                )
                return
            
            username = args[0].replace('@', '')
            new_level = args[1].lower()
            
            if new_level not in ['user', 'operator', 'admin', 'engineer']:
                await update.message.reply_text("❌ Неверный уровень доступа")
                return
            
            # Ищем пользователя по username
            target_user = self.bot_db.find_user_by_username(username)
            if not target_user:
                await update.message.reply_text(f"❌ Пользователь @{username} не найден")
                return
            
            # Обновляем уровень доступа
            success = self.bot_db.set_user_access_level(target_user['telegram_id'], new_level)
            
            if success:
                await update.message.reply_text(
                    f"✅ Пользователь @{username} повышен до уровня `{new_level}`",
                    parse_mode="Markdown"
                )
                logger.info(f"🔝 Админ {user.id} повысил @{username} до {new_level}")
            else:
                await update.message.reply_text("❌ Ошибка обновления прав доступа")
                
        except Exception as e:
            logger.error(f"❌ Ошибка команды promote: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def cmd_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /users - список пользователей (только админы)"""
        user = update.effective_user
        
        if user.id not in self.config.telegram.admin_users:
            await update.message.reply_text("❌ У вас нет прав администратора")
            return
        
        try:
            users = self.bot_db.get_all_users()
            
            if not users:
                await update.message.reply_text("📋 Пользователи не найдены")
                return
            
            text = "👥 **СПИСОК ПОЛЬЗОВАТЕЛЕЙ:**\n\n"
            
            for user_data in users:
                username = user_data.get('username', 'нет')
                first_name = user_data.get('first_name', '')
                access_level = user_data.get('access_level', 'user')
                is_active = user_data.get('is_active', True)
                
                status = "✅" if is_active else "❌"
                
                text += f"{status} **{first_name}** (@{username})\n"
                text += f"   ID: `{user_data['telegram_id']}`\n"
                text += f"   Доступ: `{access_level}`\n\n"
            
            # Разбиваем длинное сообщение на части
            if len(text) > 4000:
                parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
                for part in parts:
                    await update.message.reply_text(part, parse_mode="Markdown")
            else:
                await update.message.reply_text(text, parse_mode="Markdown")
                
        except Exception as e:
            logger.error(f"❌ Ошибка команды users: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help - справка"""
        user = update.effective_user
        
        await send_typing_action(update, context)
        
        access_level = self.bot_db.get_user_access_level(user.id)
        
        help_text = (
            "ℹ️ **Справка по КУБ-1063 Control Bot**\n\n"
            "**📱 ОСНОВНЫЕ КОМАНДЫ:**\n"
            "• `/start` — главное меню\n"
            "• `/status` — показания датчиков\n"
            "• `/stats` — статистика системы\n"
            "• `/help` — эта справка\n\n"
        )
        
        if user.id in self.config.telegram.admin_users or access_level in ['admin', 'engineer']:
            help_text += (
                "**👑 КОМАНДЫ АДМИНИСТРАТОРА:**\n"
                "• `/promote @user уровень` — изменить права\n"
                "• `/users` — список всех пользователей\n"
                "• `/switch_level <уровень>` — временное переключение уровня\n"
                "• `/level_info` — информация о текущем уровне\n"
                "• `/block_user ID` — заблокировать пользователя\n"
                "• `/unblock_user ID` — разблокировать пользователя\n\n"
            )
        
        help_text += f"**🔐 ВАШ УРОВЕНЬ ДОСТУПА:** `{access_level}`\n"
        
        menu = build_main_menu(access_level)
        
        await update.message.reply_text(
            help_text,
            reply_markup=menu,
            parse_mode="Markdown"
        )

    async def cmd_switch_level(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /switch_level - временное переключение уровня доступа"""
        user = update.effective_user
        
        # Проверяем, что пользователь имеет высокий уровень доступа
        current_level = self.bot_db.get_user_access_level(user.id)
        if current_level not in ['admin', 'engineer']:
            await update.message.reply_text(
                "❌ У вас недостаточно прав для переключения уровня доступа", 
                parse_mode="Markdown"
            )
            return
        
        # Получаем аргументы команды
        args = context.args
        if not args:
            await update.message.reply_text(
                "📝 **Использование:** `/switch_level <уровень> [часы]`\n\n"
                "**Доступные уровни:**\n"
                "• `user` — базовый уровень\n"
                "• `operator` — операторский уровень\n"
                "• `engineer` — инженерный уровень\n" 
                "• `admin` — администраторский уровень\n\n"
                "**Примеры:**\n"
                "• `/switch_level user` — переключиться на user на 24 часа\n"
                "• `/switch_level operator 2` — переключиться на operator на 2 часа\n"
                "• `/switch_level restore` — восстановить оригинальный уровень",
                parse_mode="Markdown"
            )
            return
        
        target_level = args[0].lower()
        duration_hours = int(args[1]) if len(args) > 1 else 24
        
        try:
            # Специальная команда для восстановления
            if target_level == 'restore':
                success = self.bot_db.restore_user_original_level(user.id)
                if success:
                    new_level = self.bot_db.get_user_access_level(user.id)
                    await update.message.reply_text(
                        f"🔄 **Восстановлен оригинальный уровень доступа**\n\n"
                        f"Текущий уровень: `{new_level}`",
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text("❌ Ошибка восстановления уровня доступа")
                return
            
            # Проверяем валидность целевого уровня
            valid_levels = ['user', 'operator', 'engineer', 'admin']
            if target_level not in valid_levels:
                await update.message.reply_text(
                    f"❌ Неверный уровень: `{target_level}`\n"
                    f"Доступные: {', '.join(valid_levels)}",
                    parse_mode="Markdown"
                )
                return
            
            # Устанавливаем временный уровень
            success = self.bot_db.set_user_temporary_level(user.id, target_level, duration_hours)
            if success:
                level_info = self.bot_db.get_user_level_info(user.id)
                await update.message.reply_text(
                    f"🕐 **Временный уровень доступа установлен**\n\n"
                    f"Новый уровень: `{target_level}`\n"
                    f"Длительность: {duration_hours} час(ов)\n"
                    f"Оригинальный уровень: `{level_info.get('original_level')}`\n\n"
                    f"Используйте `/switch_level restore` для восстановления.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Ошибка установки временного уровня")
                
        except ValueError:
            await update.message.reply_text("❌ Неверный формат времени. Укажите число часов.")
        except Exception as e:
            logger.error(f"❌ Ошибка переключения уровня: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def cmd_level_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /level_info - информация о текущем уровне доступа"""
        user = update.effective_user
        
        try:
            level_info = self.bot_db.get_user_level_info(user.id)
            if not level_info:
                await update.message.reply_text("❌ Пользователь не найден в системе")
                return
            
            current_level = level_info.get('current_level')
            original_level = level_info.get('original_level')
            is_temporary = level_info.get('is_temporary')
            temp_expires = level_info.get('temp_expires')
            
            info_text = f"🔐 **Информация о вашем уровне доступа**\n\n"
            info_text += f"**Текущий уровень:** `{current_level}`\n"
            
            if is_temporary and original_level:
                info_text += f"**Оригинальный уровень:** `{original_level}`\n"
                info_text += f"**Статус:** Временный\n"
                if temp_expires:
                    info_text += f"**Истекает:** {temp_expires}\n"
                info_text += f"\n💡 Используйте `/switch_level restore` для восстановления."
            else:
                info_text += f"**Статус:** Постоянный\n"
            
            # Показываем текущие права
            permissions = self.bot_db.get_access_permissions(current_level)
            if permissions:
                info_text += f"\n**🔓 Ваши права:**\n"
                if permissions.get('can_read'):
                    info_text += "• ✅ Чтение данных\n"
                if permissions.get('can_write'):
                    info_text += "• ✅ Запись команд\n"
                if permissions.get('can_reset_alarms'):
                    info_text += "• ✅ Сброс аварий\n"
            
            await update.message.reply_text(info_text, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения информации об уровне: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def cmd_block_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /block_user - блокировка пользователя"""
        user = update.effective_user
        
        # Логирование попытки блокировки пользователя
        if SECURITY_AVAILABLE:
            log_security_event("USER_BLOCK_ATTEMPT", user_id=user.id, details={
                "username": user.username,
                "args": context.args
            }, level="WARNING")
        
        # Проверяем права доступа
        access_level = self.bot_db.get_user_access_level(user.id)
        if access_level not in ['engineer', 'admin']:
            await update.message.reply_text(
                "❌ У вас недостаточно прав для блокировки пользователей", 
                parse_mode="Markdown"
            )
            return
        
        # Получаем аргументы команды
        args = context.args
        if not args:
            await update.message.reply_text(
                "📝 **Использование:** `/block_user ID_пользователя`\n\n"
                "**Пример:** `/block_user 123456789`\n\n"
                "Используйте команду `/users` для получения списка пользователей с их ID.",
                parse_mode="Markdown"
            )
            return
        
        try:
            target_user_id = int(args[0])
            
            # Проверяем, что пользователь не блокирует самого себя
            if target_user_id == user.id:
                await update.message.reply_text("❌ Вы не можете заблокировать самого себя")
                return
            
            # Блокируем пользователя
            success = self.bot_db.deactivate_user(target_user_id)
            
            if success:
                # Получаем информацию о заблокированном пользователе
                target_user = self.bot_db.get_user(target_user_id)
                target_username = target_user.get('username', 'Unknown') if target_user else 'Unknown'
                
                await update.message.reply_text(
                    f"🔒 **Пользователь заблокирован**\n\n"
                    f"👤 **Пользователь:** @{target_username} (ID: {target_user_id})\n"
                    f"👮‍♂️ **Заблокировал:** @{user.username or 'Unknown'}\n\n"
                    f"Пользователь больше не сможет использовать бота до разблокировки.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Ошибка блокировки пользователя. Возможно, пользователь не найден.")
                
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID пользователя. Укажите числовой ID.")
        except Exception as e:
            logger.error(f"❌ Ошибка блокировки пользователя: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def cmd_unblock_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /unblock_user - разблокировка пользователя"""
        user = update.effective_user
        
        # Проверяем права доступа
        access_level = self.bot_db.get_user_access_level(user.id)
        if access_level not in ['engineer', 'admin']:
            await update.message.reply_text(
                "❌ У вас недостаточно прав для разблокировки пользователей", 
                parse_mode="Markdown"
            )
            return
        
        # Получаем аргументы команды
        args = context.args
        if not args:
            await update.message.reply_text(
                "📝 **Использование:** `/unblock_user ID_пользователя`\n\n"
                "**Пример:** `/unblock_user 123456789`\n\n"
                "Используйте меню **Настройки → Управление пользователями → Разблокировать пользователя** "
                "для получения списка заблокированных пользователей.",
                parse_mode="Markdown"
            )
            return
        
        try:
            target_user_id = int(args[0])
            
            # Разблокируем пользователя (устанавливаем is_active = 1)
            try:
                with sqlite3.connect('kub_commands.db') as conn:
                    cursor = conn.execute("""
                        UPDATE telegram_users 
                        SET is_active = 1, last_active = CURRENT_TIMESTAMP
                        WHERE telegram_id = ?
                    """, (target_user_id,))
                    
                    success = cursor.rowcount > 0
            except Exception as db_error:
                logger.error(f"❌ Ошибка базы данных при разблокировке: {db_error}")
                success = False
            
            if success:
                # Получаем информацию о разблокированном пользователе
                target_user = self.bot_db.get_user(target_user_id)
                target_username = target_user.get('username', 'Unknown') if target_user else 'Unknown'
                
                await update.message.reply_text(
                    f"✅ **Пользователь разблокирован**\n\n"
                    f"👤 **Пользователь:** @{target_username} (ID: {target_user_id})\n"
                    f"👮‍♂️ **Разблокировал:** @{user.username or 'Unknown'}\n\n"
                    f"Пользователь снова может использовать бота.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Ошибка разблокировки пользователя. Возможно, пользователь не найден или уже активен.")
                
        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID пользователя. Укажите числовой ID.")
        except Exception as e:
            logger.error(f"❌ Ошибка разблокировки пользователя: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    # =======================================================================
    # ОБРАБОТЧИКИ CALLBACK QUERY (INLINE КНОПКИ)
    # =======================================================================
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик inline кнопок"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        try:
            await send_typing_action(query, context)
            
            if data == "show_status":
                await self._handle_show_status(query, context)
            elif data == "refresh_status":
                await self._handle_refresh_status(query, context)
            elif data == "show_stats":
                await self._handle_show_stats(query, context)
            elif data == "refresh_stats":
                await self._handle_refresh_stats(query, context)
            elif data == "reset_alarms":
                await self._handle_reset_alarms(query, context)
            elif data == "reset_alarms_confirmed":
                await self._handle_confirm_reset_alarms(query, context)
            elif data == "main_menu":
                await self._handle_main_menu(query, context)
            elif data == "show_help":
                await self._handle_show_help(query, context)
            elif data == "settings":
                await self._handle_settings(query, context)
            
            # НОВЫЕ ОБРАБОТЧИКИ МЕНЮ НАСТРОЕК
            elif data == "manage_users":
                await self._handle_manage_users(query, context)
            elif data == "switch_level_menu":
                await self._handle_switch_level_menu(query, context)
            elif data == "system_config":
                await self._handle_system_config(query, context)
            elif data == "system_logs":
                await self._handle_system_logs(query, context)
            elif data == "permissions_config":
                await self._handle_permissions_config(query, context)
            elif data == "backup_config":
                await self._handle_backup_config(query, context)
            
            # УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ
            elif data == "list_users":
                await self._handle_list_users(query, context)
            elif data == "invite_user":
                await self._handle_invite_user(query, context)
            elif data == "block_user":
                await self._handle_block_user(query, context)
            elif data == "unblock_user":
                await self._handle_unblock_user(query, context)
            elif data == "change_permissions":
                await self._handle_change_permissions(query, context)
            elif data == "user_stats":
                await self._handle_user_stats(query, context)
            
            # ПЕРЕКЛЮЧЕНИЕ УРОВНЕЙ
            elif data.startswith("temp_level_"):
                level = data.replace("temp_level_", "")
                await self._handle_temp_level(query, context, level)
            elif data == "restore_level":
                await self._handle_restore_level(query, context)
            elif data == "level_info_menu":
                await self._handle_level_info_menu(query, context)
            
            # ИНТЕРАКТИВНОЕ УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ
            elif data.startswith("promote_user_"):
                user_id = int(data.replace("promote_user_", ""))
                await self._handle_promote_user_selected(query, context, user_id)
            elif data.startswith("block_user_"):
                user_id = int(data.replace("block_user_", ""))
                await self._handle_block_user_selected(query, context, user_id)
            elif data.startswith("unblock_user_"):
                user_id = int(data.replace("unblock_user_", ""))
                await self._handle_unblock_user_selected(query, context, user_id)
            elif data.startswith("set_level_"):
                parts = data.replace("set_level_", "").split("_")
                user_id = int(parts[0])
                new_level = parts[1]
                await self._handle_set_user_level(query, context, user_id, new_level)
            elif data.startswith("invite_level_"):
                level = data.replace("invite_level_", "")
                await self._handle_invite_level_selected(query, context, level)
            elif data.startswith("confirm_invite_"):
                level = data.replace("confirm_invite_", "")
                await self._handle_confirm_invite(query, context, level)
            elif data.startswith("copy_link_"):
                await query.answer("📋 Ссылка готова к копированию! Нажмите на неё выше ☝️", show_alert=True)
            elif data == "promote_users":
                await self._handle_change_permissions(query, context)
            
            else:
                await query.edit_message_text(
                    error_message("Неизвестная команда"), 
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"❌ Ошибка обработки callback {data}: {e}")
            access_level = self.bot_db.get_user_access_level(query.from_user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message(f"Ошибка выполнения команды: {str(e)}"),
                reply_markup=back_menu,
                parse_mode="Markdown"
            )

    async def _handle_main_menu(self, query, context):
        """Показать главное меню"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        menu = build_main_menu(access_level)
        
        await query.edit_message_text(
            "🏠 **Главное меню**\n\nВыберите действие:",
            reply_markup=menu,
            parse_mode="Markdown"
        )

    async def _handle_show_status(self, query, context):
        """Показать статус"""
        await self._handle_refresh_status(query, context)

    async def _handle_refresh_status(self, query, context):
        """Обновление статуса из SQLite базы"""
        user = query.from_user
        
        if not check_user_permission(user.id, "read", self.bot_db):
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message("У вас нет прав для чтения данных"),
                reply_markup=back_menu,
                parse_mode="Markdown"
            )
            return
        
        try:
            # Читаем данные из SQLite
            data = self.get_current_data_from_db()
            
            if data:
                status_text = format_sensor_data(data)
            else:
                status_text = error_message(
                    "Нет данных от КУБ-1063\n\n"
                    "Возможные причины:\n"
                    "• Основная система не запущена\n"
                    "• Нет связи с контроллером\n\n"
                    "Запустите: `python tools/start_all_services.py`"
                )
            
            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_main_menu(access_level)
            
            status_text = truncate_text(status_text, 4000)
            
            # Проверяем, изменился ли контент перед редактированием
            try:
                await query.edit_message_text(
                    status_text,
                    reply_markup=menu,
                    parse_mode="Markdown"
                )
            except Exception as edit_error:
                if "message is not modified" in str(edit_error).lower():
                    # Сообщение не изменилось, просто отправляем ответ без редактирования
                    await query.answer("🔄 Данные обновлены", show_alert=False)
                else:
                    raise edit_error
            
            self.bot_db.log_user_command(user.id, "read", None, data is not None)
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления статуса: {e}")
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message(f"Ошибка получения данных: {str(e)}"),
                reply_markup=back_menu,
                parse_mode="Markdown"
            )

    async def _handle_show_stats(self, query, context):
        """Показать статистику"""
        await self._handle_refresh_stats(query, context)

    async def _handle_refresh_stats(self, query, context):
        """Обновление статистики"""
        user = query.from_user
        
        if not check_user_permission(user.id, "read", self.bot_db):
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message("У вас нет прав для чтения статистики"),
                reply_markup=back_menu,
                parse_mode="Markdown"
            )
            return
        
        try:
            # Простая статистика
            stats_text = "📈 **СТАТИСТИКА СИСТЕМЫ КУБ-1063**\n\n"
            
            data = self.get_current_data_from_db()
            if data:
                stats_text += f"🔄 **Последнее обновление:** `{data.get('updated_at', 'неизвестно')}`\n"
                stats_text += f"🌡️ **Температура:** `{data.get('temp_inside', 0):.1f}°C`\n"
                stats_text += f"💧 **Влажность:** `{data.get('humidity', 0):.1f}%`\n"
            else:
                stats_text += "❌ Нет данных от основной системы\n"
            
            user_stats = self.bot_db.get_user_stats(user.id)
            if user_stats:
                stats_text += f"\n**👤 ВАША СТАТИСТИКА:**\n"
                stats_text += f"• Всего команд: `{user_stats.get('total_commands', 0)}`\n"
            
            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_stats_menu(access_level)
            
            stats_text = truncate_text(stats_text, 4000)
            
            # Проверяем, изменился ли контент перед редактированием
            try:
                await query.edit_message_text(
                    stats_text,
                    reply_markup=menu,
                    parse_mode="Markdown"
                )
            except Exception as edit_error:
                if "message is not modified" in str(edit_error).lower():
                    # Сообщение не изменилось, просто отправляем ответ без редактирования
                    await query.answer("📈 Статистика обновлена", show_alert=False)
                else:
                    raise edit_error
            
            self.bot_db.log_user_command(user.id, "stats", None, True)
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message(f"Ошибка получения статистики: {str(e)}"),
                reply_markup=back_menu,
                parse_mode="Markdown"
            )

    async def _handle_reset_alarms(self, query, context):
        """Запрос подтверждения сброса аварий"""
        user = query.from_user
        
        if not check_user_permission(user.id, "reset_alarms", self.bot_db):
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message("У вас нет прав для сброса аварий"),
                reply_markup=back_menu,
                parse_mode="Markdown"
            )
            return
        
        confirmation_menu = build_confirmation_menu("reset_alarms_confirmed", "main_menu")
        
        await query.edit_message_text(
            warning_message("Вы уверены, что хотите сбросить все аварии?\n\nЭто действие нельзя отменить!"),
            reply_markup=confirmation_menu,
            parse_mode="Markdown"
        )

    async def _handle_confirm_reset_alarms(self, query, context):
        """Подтвержденный сброс аварий через систему команд"""
        user = query.from_user
        
        if not check_user_permission(user.id, "reset_alarms", self.bot_db):
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message("У вас нет прав для сброса аварий"),
                reply_markup=back_menu,
                parse_mode="Markdown"
            )
            return
        
        try:
            # Показываем процесс выполнения
            await query.edit_message_text(
                loading_message("Выполняется сброс аварий..."),
                parse_mode="Markdown"
            )
            
            # Добавляем команду сброса в очередь (регистр 0x0020, значение 1)
            user_info = f"telegram_user_{user.id}_{user.username or user.first_name}"
            success, result = self.add_write_command_to_db(0x0020, 1, user_info)
            
            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_main_menu(access_level)
            
            if success:
                await query.edit_message_text(
                    success_message(f"🔄 Команда сброса аварий отправлена!\n\nID команды: `{result}`\n\nВыполнение может занять несколько секунд."),
                    reply_markup=menu,
                    parse_mode="Markdown"
                )
                self.bot_db.log_user_command(user.id, "reset_alarms", "0x0020", True)
            else:
                await query.edit_message_text(
                    error_message(f"Ошибка отправки команды:\n{result}"),
                    reply_markup=menu,
                    parse_mode="Markdown"
                )
                self.bot_db.log_user_command(user.id, "reset_alarms", "0x0020", False)
                
        except Exception as e:
            logger.error(f"❌ Ошибка сброса аварий: {e}")
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message(f"Ошибка: {str(e)}"),
                reply_markup=back_menu,
                parse_mode="Markdown"
            )

    async def _handle_show_help(self, query, context):
        """Показать справку через callback"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        
        help_text = (
            "ℹ️ **Справка по КУБ-1063 Control Bot**\n\n"
            "**🔘 КНОПКИ МЕНЮ:**\n"
            "• 📊 Показания — текущие данные с датчиков\n"
            "• 🔄 Обновить — получить свежие данные\n"
            "• 📈 Статистика — статистика системы\n"
            "• 🏠 Главное меню — возврат в главное меню\n"
        )
        
        if access_level in ("operator", "admin", "engineer"):
            help_text += "• 🚨 Сброс аварий — сброс активных аварий\n"
        
        if access_level in ("admin", "engineer"):
            help_text += "• ⚙️ Настройки — управление системой\n"
        
        help_text += f"\n**🔐 ВАШ ДОСТУП:** `{access_level}`\n"
        help_text += "\n💡 **Совет:** Кнопки быстрее команд!"
        
        menu = build_main_menu(access_level)
        
        await query.edit_message_text(
            help_text,
            reply_markup=menu,
            parse_mode="Markdown"
        )

    async def _handle_settings(self, query, context):
        """Настройки системы"""
        user = query.from_user
        
        # Проверяем базовые права доступа
        if not check_user_permission(user.id, "read", self.bot_db):
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message("У вас нет прав для настроек"),
                reply_markup=back_menu,
                parse_mode="Markdown"
            )
            return
        
        access_level = self.bot_db.get_user_access_level(user.id)
        
        # Получаем информацию о пользователе для отображения
        user_info = self.bot_db.get_user(user.id)
        username = user_info.get('username', 'Unknown') if user_info else 'Unknown'
        
        settings_text = (
            f"⚙️ **НАСТРОЙКИ СИСТЕМЫ**\n\n"
            f"👤 **Пользователь:** @{username}\n"
            f"🔐 **Уровень доступа:** `{access_level}`\n\n"
            f"Выберите раздел настроек:"
        )
        
        from telegram_bot.bot_utils import build_settings_menu
        menu = build_settings_menu(access_level)
        
        try:
            await query.edit_message_text(
                settings_text,
                reply_markup=menu,
                parse_mode="Markdown"
            )
        except Exception as edit_error:
            if "message is not modified" in str(edit_error).lower():
                await query.answer("⚙️ Меню настроек открыто", show_alert=False)
            else:
                raise edit_error

    # =======================================================================
    # НОВЫЕ ОБРАБОТЧИКИ МЕНЮ НАСТРОЕК
    # =======================================================================

    async def _handle_manage_users(self, query, context):
        """Управление пользователями"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        
        if access_level not in ['operator', 'engineer', 'admin']:
            await query.answer("❌ Недостаточно прав для управления пользователями", show_alert=True)
            return
        
        users_text = (
            f"👥 **УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ**\n\n"
            f"🔐 **Ваш уровень:** `{access_level}`\n\n"
            f"Выберите действие:"
        )
        
        from telegram_bot.bot_utils import build_user_management_menu
        menu = build_user_management_menu(access_level)
        
        try:
            await query.edit_message_text(
                users_text,
                reply_markup=menu,
                parse_mode="Markdown"
            )
        except Exception as edit_error:
            if "message is not modified" in str(edit_error).lower():
                await query.answer("👥 Управление пользователями", show_alert=False)
            else:
                raise edit_error

    async def _handle_switch_level_menu(self, query, context):
        """Меню переключения уровня доступа"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        
        if access_level not in ['engineer', 'admin']:
            await query.answer("❌ Недостаточно прав для переключения уровня", show_alert=True)
            return
        
        # Упрощенный текст без проверки временных уровней (методы еще не загружены)
        switch_text = (
            f"🔄 **ПЕРЕКЛЮЧЕНИЕ УРОВНЯ ДОСТУПА**\n\n"
            f"📊 **Текущий уровень:** `{access_level}`\n\n"
            f"⚠️ **Временно недоступно:** Методы переключения уровней будут активны после полной перезагрузки системы.\n\n"
            f"Используйте команды:\n"
            f"• `/switch_level user` - переключиться на user\n"
            f"• `/switch_level restore` - восстановить уровень\n"
            f"• `/level_info` - информация об уровне"
        )
        
        from telegram_bot.bot_utils import build_switch_level_menu
        menu = build_switch_level_menu(access_level)
        
        try:
            await query.edit_message_text(
                switch_text,
                reply_markup=menu,
                parse_mode="Markdown"
            )
        except Exception as edit_error:
            if "message is not modified" in str(edit_error).lower():
                await query.answer("🔄 Переключение уровня", show_alert=False)
            else:
                raise edit_error

    async def _handle_list_users(self, query, context):
        """Список пользователей"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        
        if access_level not in ['operator', 'engineer', 'admin']:
            await query.answer("❌ Недостаточно прав", show_alert=True)
            return
        
        try:
            all_users = self.bot_db.get_all_users()
            
            users_text = f"👤 **СПИСОК ПОЛЬЗОВАТЕЛЕЙ** (всего: {len(all_users)})\n\n"
            
            for user_data in all_users[:10]:  # Показываем первых 10 пользователей
                username = user_data.get('username') or 'Без username'
                first_name = user_data.get('first_name') or 'Без имени'
                user_access_level = user_data.get('access_level', 'user')
                is_active = user_data.get('is_active', True)
                
                status_emoji = "✅" if is_active else "❌"
                level_emoji = {"user": "👤", "operator": "👷", "engineer": "🔧", "admin": "👑"}.get(user_access_level, "❓")
                
                users_text += f"{status_emoji} {level_emoji} **{first_name}** (@{username})\n"
                users_text += f"   ID: `{user_data['telegram_id']}` | Уровень: `{user_access_level}`\n\n"
            
            if len(all_users) > 10:
                users_text += f"... и еще {len(all_users) - 10} пользователей\n"
            
            from telegram_bot.bot_utils import build_user_management_menu
            menu = build_user_management_menu(access_level)
            
            await query.edit_message_text(
                users_text,
                reply_markup=menu,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения списка пользователей: {e}")
            await query.answer("❌ Ошибка получения списка пользователей", show_alert=True)

    async def _handle_temp_level(self, query, context, level):
        """Установка временного уровня"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        
        if access_level not in ['engineer', 'admin']:
            await query.answer("❌ Недостаточно прав", show_alert=True)
            return
        
        # Временная заглушка - методы еще не загружены
        await query.answer(f"⚠️ Функция временно недоступна. Используйте команду: /switch_level {level}", show_alert=True)

    async def _handle_restore_level(self, query, context):
        """Восстановление оригинального уровня"""
        user = query.from_user
        
        # Временная заглушка - методы еще не загружены
        await query.answer("⚠️ Функция временно недоступна. Используйте команду: /switch_level restore", show_alert=True)

    async def _handle_level_info_menu(self, query, context):
        """Информация о текущем уровне доступа"""
        user = query.from_user
        
        # Упрощенная информация без новых методов
        try:
            current_level = self.bot_db.get_user_access_level(user.id)
            
            info_text = f"ℹ️ **ИНФОРМАЦИЯ ОБ УРОВНЕ ДОСТУПА**\n\n"
            info_text += f"📊 **Текущий уровень:** `{current_level}`\n"
            info_text += f"⚡ **Статус:** Постоянный\n"
            
            # Показываем права доступа
            permissions = self.bot_db.get_access_permissions(current_level)
            if permissions:
                info_text += f"\n🔓 **Ваши права:**\n"
                if permissions.get('can_read'):
                    info_text += "• ✅ Чтение данных\n"
                if permissions.get('can_write'):
                    info_text += "• ✅ Запись команд\n"
                if permissions.get('can_reset_alarms'):
                    info_text += "• ✅ Сброс аварий\n"
            
            info_text += f"\n💡 **Команды переключения:**\n"
            info_text += f"• `/switch_level user` - временно стать user\n"
            info_text += f"• `/level_info` - подробная информация\n"
            
            from telegram_bot.bot_utils import build_switch_level_menu
            menu = build_switch_level_menu(current_level)
            
            await query.edit_message_text(
                info_text,
                reply_markup=menu,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения информации об уровне: {e}")
            await query.answer("❌ Ошибка получения информации", show_alert=True)

    # Заглушки для остальных функций настроек
    async def _handle_system_config(self, query, context):
        await query.answer("🔧 Настройки системы - в разработке", show_alert=True)

    async def _handle_system_logs(self, query, context):
        await query.answer("📋 Логи системы - в разработке", show_alert=True)

    async def _handle_permissions_config(self, query, context):
        await query.answer("🔐 Управление правами - в разработке", show_alert=True)

    async def _handle_backup_config(self, query, context):
        await query.answer("💾 Резервные копии - в разработке", show_alert=True)

    async def _handle_invite_user(self, query, context):
        """Приглашение пользователя - выбор уровня доступа"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        
        if access_level not in ['operator', 'engineer', 'admin']:
            await query.answer("❌ Недостаточно прав для приглашения пользователей", show_alert=True)
            return
        
        invite_text = (
            f"➕ **ПРИГЛАШЕНИЕ ПОЛЬЗОВАТЕЛЯ**\n\n"
            f"🔐 **Ваш уровень:** `{access_level}`\n\n"
            f"Выберите уровень доступа для нового пользователя:\n\n"
            f"**Доступные уровни:**\n"
            f"• **👤 User** - только чтение данных\n"
            f"• **⚙️ Operator** - чтение + запись команд\n"
            f"• **🔧 Engineer** - расширенные функции\n\n"
            f"После выбора будет создана уникальная ссылка-приглашение."
        )
        
        from telegram_bot.bot_utils import build_invitation_level_menu
        menu = build_invitation_level_menu()
        
        try:
            await query.edit_message_text(
                invite_text,
                reply_markup=menu,
                parse_mode="Markdown"
            )
        except Exception as edit_error:
            if "message is not modified" in str(edit_error).lower():
                await query.answer("➕ Приглашение пользователя", show_alert=False)
            else:
                raise edit_error

    async def _handle_block_user(self, query, context):
        """Блокировка пользователя"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        
        if access_level not in ['engineer', 'admin']:
            await query.answer("❌ Недостаточно прав для блокировки пользователей", show_alert=True)
            return
        
        try:
            all_users = self.bot_db.get_all_users()
            active_users = [u for u in all_users if u.get('is_active', True)]
            
            if not active_users:
                await query.answer("❌ Нет активных пользователей для блокировки", show_alert=True)
                return
            
            block_text = (
                f"🔒 **БЛОКИРОВКА ПОЛЬЗОВАТЕЛЯ**\n\n"
                f"**Нажмите на пользователя для блокировки:**\n\n"
                f"⚠️ **Внимание:** Заблокированный пользователь не сможет использовать бота до разблокировки."
            )
            
            from telegram_bot.bot_utils import build_user_list_menu
            menu = build_user_list_menu(active_users, "block", access_level)
            
            await query.edit_message_text(
                block_text,
                reply_markup=menu,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения списка для блокировки: {e}")
            await query.answer("❌ Ошибка получения списка пользователей", show_alert=True)

    async def _handle_unblock_user(self, query, context):
        """Разблокировка пользователя"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        
        if access_level not in ['engineer', 'admin']:
            await query.answer("❌ Недостаточно прав для разблокировки пользователей", show_alert=True)
            return
        
        try:
            all_users = self.bot_db.get_all_users()
            blocked_users = [u for u in all_users if not u.get('is_active', True)]
            
            if not blocked_users:
                unblock_text = (
                    f"✅ **РАЗБЛОКИРОВКА ПОЛЬЗОВАТЕЛЯ**\n\n"
                    f"🎉 **Все пользователи активны!**\n\n"
                    f"В системе нет заблокированных пользователей."
                )
                
                from telegram_bot.bot_utils import build_user_management_menu
                menu = build_user_management_menu(access_level)
                
                await query.edit_message_text(
                    unblock_text,
                    reply_markup=menu,
                    parse_mode="Markdown"
                )
            else:
                unblock_text = (
                    f"✅ **РАЗБЛОКИРОВКА ПОЛЬЗОВАТЕЛЯ**\n\n"
                    f"**Нажмите на пользователя для разблокировки:**"
                )
                
                from telegram_bot.bot_utils import build_user_list_menu
                menu = build_user_list_menu(blocked_users, "unblock", access_level)
                
                await query.edit_message_text(
                    unblock_text,
                    reply_markup=menu,
                    parse_mode="Markdown"
                )
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения списка для разблокировки: {e}")
            await query.answer("❌ Ошибка получения списка пользователей", show_alert=True)

    async def _handle_change_permissions(self, query, context):
        """Изменение прав пользователей"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        
        if access_level != 'admin':
            await query.answer("❌ Только администраторы могут изменять права", show_alert=True)
            return
        
        try:
            all_users = self.bot_db.get_all_users()
            
            if not all_users:
                await query.answer("❌ Пользователи не найдены", show_alert=True)
                return
            
            permissions_text = (
                f"👑 **ИЗМЕНЕНИЕ ПРАВ ПОЛЬЗОВАТЕЛЕЙ**\n\n"
                f"**Нажмите на пользователя для изменения его прав:**\n\n"
                f"**Доступные уровни:**\n"
                f"• 👤 `user` - только чтение\n"
                f"• 👷 `operator` - чтение + запись\n"
                f"• 🔧 `engineer` - расширенные функции\n"
                f"• 👑 `admin` - полный доступ"
            )
            
            from telegram_bot.bot_utils import build_user_list_menu
            menu = build_user_list_menu(all_users, "promote", access_level)
            
            await query.edit_message_text(
                permissions_text,
                reply_markup=menu,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения информации о правах: {e}")
            await query.answer("❌ Ошибка получения информации", show_alert=True)

    async def _handle_user_stats(self, query, context):
        """Статистика пользователей"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        
        if access_level not in ['operator', 'engineer', 'admin']:
            await query.answer("❌ Недостаточно прав для просмотра статистики", show_alert=True)
            return
        
        try:
            all_users = self.bot_db.get_all_users()
            
            if not all_users:
                await query.answer("❌ Пользователи не найдены", show_alert=True)
                return
            
            # Подсчитываем статистику
            total_users = len(all_users)
            active_users = sum(1 for u in all_users if u.get('is_active', True))
            inactive_users = total_users - active_users
            
            # Статистика по уровням доступа
            level_stats = {}
            for user_data in all_users:
                level = user_data.get('access_level', 'user')
                level_stats[level] = level_stats.get(level, 0) + 1
            
            stats_text = f"📊 **СТАТИСТИКА ПОЛЬЗОВАТЕЛЕЙ**\n\n"
            stats_text += f"👥 **Всего пользователей:** {total_users}\n"
            stats_text += f"✅ **Активных:** {active_users}\n"
            stats_text += f"❌ **Неактивных:** {inactive_users}\n\n"
            
            stats_text += f"**📊 По уровням доступа:**\n"
            level_emojis = {"user": "👤", "operator": "👷", "engineer": "🔧", "admin": "👑"}
            for level, count in level_stats.items():
                emoji = level_emojis.get(level, "❓")
                stats_text += f"{emoji} **{level.capitalize()}:** {count} чел.\n"
            
            # Показываем последнюю активность
            recent_users = [u for u in all_users if u.get('last_active')][:5]
            if recent_users:
                stats_text += f"\n**🕐 Последняя активность:**\n"
                for user_data in recent_users:
                    username = user_data.get('username') or 'Без username'
                    last_active = user_data.get('last_active', 'неизвестно')
                    stats_text += f"• @{username} - {last_active}\n"
            
            # Получаем детальную статистику от базы данных
            stats_text += f"\n**📈 Активность системы:**\n"
            
            # Подсчитываем команды из истории
            try:
                import sqlite3
                with sqlite3.connect('kub_commands.db') as conn:
                    cursor = conn.execute("SELECT COUNT(*) FROM user_command_history WHERE timestamp > datetime('now', '-24 hours')")
                    commands_24h = cursor.fetchone()[0]
                    
                    cursor = conn.execute("SELECT COUNT(*) FROM user_command_history WHERE timestamp > datetime('now', '-1 hour')")
                    commands_1h = cursor.fetchone()[0]
                    
                    stats_text += f"• Команд за час: {commands_1h}\n"
                    stats_text += f"• Команд за сутки: {commands_24h}\n"
            except:
                stats_text += f"• Статистика команд недоступна\n"
            
            from telegram_bot.bot_utils import build_user_management_menu
            menu = build_user_management_menu(access_level)
            
            await query.edit_message_text(
                stats_text,
                reply_markup=menu,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики пользователей: {e}")
            await query.answer("❌ Ошибка получения статистики", show_alert=True)

    # =======================================================================
    # ИНТЕРАКТИВНЫЕ ОБРАБОТЧИКИ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ
    # =======================================================================

    async def _handle_promote_user_selected(self, query, context, user_id: int):
        """Обработка выбора пользователя для изменения прав"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        
        if access_level != 'admin':
            await query.answer("❌ Только администраторы могут изменять права", show_alert=True)
            return
        
        try:
            # Получаем информацию о выбранном пользователе
            target_user = self.bot_db.get_user(user_id)
            if not target_user:
                await query.answer("❌ Пользователь не найден", show_alert=True)
                return
            
            target_username = target_user.get('username', 'Без username')
            target_first_name = target_user.get('first_name', 'Без имени')
            current_level = target_user.get('access_level', 'user')
            
            # Не позволяем изменять права самому себе
            if user_id == user.id:
                await query.answer("❌ Вы не можете изменить свои собственные права", show_alert=True)
                return
            
            level_emojis = {"user": "👤", "operator": "👷", "engineer": "🔧", "admin": "👑"}
            current_emoji = level_emojis.get(current_level, "❓")
            
            promote_text = (
                f"👑 **ИЗМЕНЕНИЕ ПРАВ ПОЛЬЗОВАТЕЛЯ**\n\n"
                f"**Выбранный пользователь:**\n"
                f"{current_emoji} **{target_first_name}** (@{target_username})\n"
                f"**Текущий уровень:** `{current_level}`\n\n"
                f"**Выберите новый уровень доступа:**"
            )
            
            from telegram_bot.bot_utils import build_level_selection_menu
            menu = build_level_selection_menu(user_id, current_level)
            
            await query.edit_message_text(
                promote_text,
                reply_markup=menu,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка выбора пользователя для изменения прав: {e}")
            await query.answer("❌ Ошибка обработки запроса", show_alert=True)

    async def _handle_set_user_level(self, query, context, user_id: int, new_level: str):
        """Установка нового уровня доступа пользователю"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        
        if access_level != 'admin':
            await query.answer("❌ Только администраторы могут изменять права", show_alert=True)
            return
        
        try:
            # Получаем информацию о пользователе
            target_user = self.bot_db.get_user(user_id)
            if not target_user:
                await query.answer("❌ Пользователь не найден", show_alert=True)
                return
            
            target_username = target_user.get('username', 'Без username')
            target_first_name = target_user.get('first_name', 'Без имени')
            old_level = target_user.get('access_level', 'user')
            
            # Обновляем уровень доступа напрямую в базе данных
            try:
                with sqlite3.connect('kub_commands.db') as conn:
                    cursor = conn.execute("""
                        UPDATE telegram_users 
                        SET access_level = ?, last_active = CURRENT_TIMESTAMP
                        WHERE telegram_id = ?
                    """, (new_level, user_id))
                    
                    success = cursor.rowcount > 0
            except Exception as db_error:
                logger.error(f"❌ Ошибка базы данных при изменении уровня: {db_error}")
                success = False
            
            if success:
                level_emojis = {"user": "👤", "operator": "👷", "engineer": "🔧", "admin": "👑"}
                old_emoji = level_emojis.get(old_level, "❓")
                new_emoji = level_emojis.get(new_level, "❓")
                
                success_text = (
                    f"✅ **ПРАВА ПОЛЬЗОВАТЕЛЯ ИЗМЕНЕНЫ**\n\n"
                    f"**Пользователь:** {target_first_name} (@{target_username})\n"
                    f"**Изменение:** {old_emoji} `{old_level}` → {new_emoji} `{new_level}`\n"
                    f"**Изменил:** @{user.username or 'Unknown'}\n\n"
                    f"Изменения вступили в силу немедленно."
                )
                
                from telegram_bot.bot_utils import build_user_management_menu
                menu = build_user_management_menu(access_level)
                
                await query.edit_message_text(
                    success_text,
                    reply_markup=menu,
                    parse_mode="Markdown"
                )
                
                await query.answer("✅ Права пользователя изменены", show_alert=False)
            else:
                await query.answer("❌ Ошибка изменения прав пользователя", show_alert=True)
                
        except Exception as e:
            logger.error(f"❌ Ошибка установки уровня пользователя: {e}")
            await query.answer("❌ Ошибка обработки запроса", show_alert=True)

    async def _handle_block_user_selected(self, query, context, user_id: int):
        """Обработка выбора пользователя для блокировки"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        
        if access_level not in ['engineer', 'admin']:
            await query.answer("❌ Недостаточно прав для блокировки пользователей", show_alert=True)
            return
        
        # Проверяем, что пользователь не блокирует самого себя
        if user_id == user.id:
            await query.answer("❌ Вы не можете заблокировать самого себя", show_alert=True)
            return
        
        try:
            # Получаем информацию о пользователе
            target_user = self.bot_db.get_user(user_id)
            if not target_user:
                await query.answer("❌ Пользователь не найден", show_alert=True)
                return
            
            target_username = target_user.get('username', 'Без username')
            target_first_name = target_user.get('first_name', 'Без имени')
            
            # Блокируем пользователя
            success = self.bot_db.deactivate_user(user_id)
            
            if success:
                block_text = (
                    f"🔒 **ПОЛЬЗОВАТЕЛЬ ЗАБЛОКИРОВАН**\n\n"
                    f"**Пользователь:** {target_first_name} (@{target_username})\n"
                    f"**Заблокировал:** @{user.username or 'Unknown'}\n\n"
                    f"Пользователь больше не сможет использовать бота до разблокировки."
                )
                
                from telegram_bot.bot_utils import build_user_management_menu
                menu = build_user_management_menu(access_level)
                
                await query.edit_message_text(
                    block_text,
                    reply_markup=menu,
                    parse_mode="Markdown"
                )
                
                await query.answer("🔒 Пользователь заблокирован", show_alert=False)
            else:
                await query.answer("❌ Ошибка блокировки пользователя", show_alert=True)
                
        except Exception as e:
            logger.error(f"❌ Ошибка блокировки пользователя: {e}")
            await query.answer("❌ Ошибка обработки запроса", show_alert=True)

    async def _handle_unblock_user_selected(self, query, context, user_id: int):
        """Обработка выбора пользователя для разблокировки"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        
        if access_level not in ['engineer', 'admin']:
            await query.answer("❌ Недостаточно прав для разблокировки пользователей", show_alert=True)
            return
        
        try:
            # Получаем информацию о пользователе
            target_user = self.bot_db.get_user(user_id)
            if not target_user:
                await query.answer("❌ Пользователь не найден", show_alert=True)
                return
            
            target_username = target_user.get('username', 'Без username')
            target_first_name = target_user.get('first_name', 'Без имени')
            
            # Разблокируем пользователя
            try:
                with sqlite3.connect('kub_commands.db') as conn:
                    cursor = conn.execute("""
                        UPDATE telegram_users 
                        SET is_active = 1, last_active = CURRENT_TIMESTAMP
                        WHERE telegram_id = ?
                    """, (user_id,))
                    
                    success = cursor.rowcount > 0
            except Exception as db_error:
                logger.error(f"❌ Ошибка базы данных при разблокировке: {db_error}")
                success = False
            
            if success:
                unblock_text = (
                    f"✅ **ПОЛЬЗОВАТЕЛЬ РАЗБЛОКИРОВАН**\n\n"
                    f"**Пользователь:** {target_first_name} (@{target_username})\n"
                    f"**Разблокировал:** @{user.username or 'Unknown'}\n\n"
                    f"Пользователь снова может использовать бота."
                )
                
                from telegram_bot.bot_utils import build_user_management_menu
                menu = build_user_management_menu(access_level)
                
                await query.edit_message_text(
                    unblock_text,
                    reply_markup=menu,
                    parse_mode="Markdown"
                )
                
                await query.answer("✅ Пользователь разблокирован", show_alert=False)
            else:
                await query.answer("❌ Ошибка разблокировки пользователя", show_alert=True)
                
        except Exception as e:
            logger.error(f"❌ Ошибка разблокировки пользователя: {e}")
            await query.answer("❌ Ошибка обработки запроса", show_alert=True)

    # =======================================================================
    # ЗАПУСК БЕЗ КОНФЛИКТОВ
    # =======================================================================

    async def start_bot(self):
        """Исправленный запуск бота БЕЗ создания собственной системы RS485"""
        try:
            logger.info("🚀 Инициализация Telegram Bot (без RS485)...")
            
            # Инициализируем только базы данных
            from modbus.modbus_storage import init_db
            init_db()
            
            # Создаём приложение Telegram
            self.application = Application.builder().token(self.token).build()

            # Регистрируем обработчики команд
            self.application.add_handler(CommandHandler("start", self.cmd_start))
            self.application.add_handler(CommandHandler("status", self.cmd_status))
            self.application.add_handler(CommandHandler("stats", self.cmd_stats))
            self.application.add_handler(CommandHandler("help", self.cmd_help))
            
            # УПРАВЛЕНИЕ РОЛЯМИ
            self.application.add_handler(CommandHandler("promote", self.cmd_promote))
            self.application.add_handler(CommandHandler("users", self.cmd_users))
            
            # ПЕРЕКЛЮЧЕНИЕ УРОВНЕЙ ДОСТУПА
            self.application.add_handler(CommandHandler("switch_level", self.cmd_switch_level))
            self.application.add_handler(CommandHandler("level_info", self.cmd_level_info))
            
            # БЛОКИРОВКА ПОЛЬЗОВАТЕЛЕЙ
            self.application.add_handler(CommandHandler("block_user", self.cmd_block_user))
            self.application.add_handler(CommandHandler("unblock_user", self.cmd_unblock_user))
            
            # Обработчик кнопок
            self.application.add_handler(CallbackQueryHandler(self.handle_callback))

            logger.info("🚀 Запуск Telegram Bot...")

            # Инициализируем приложение
            await self.application.initialize()
            await self.application.start()
            
            # Запускаем polling вручную для лучшего контроля
            await self.application.updater.start_polling(drop_pending_updates=True)
            
            logger.info("🤖 Бот запущен и ждет сообщения...")
            
            # Проверяем истекшие временные уровни доступа (временно отключено)
            try:
                expired_count = self.bot_db.check_and_restore_expired_levels()
                if expired_count > 0:
                    logger.info(f"⏰ Восстановлено {expired_count} истекших временных уровней доступа")
            except AttributeError:
                logger.info("⚠️ Методы переключения уровней будут доступны после полной перезагрузки системы")
            
            try:
                # Ждем бесконечно
                await asyncio.sleep(float('inf'))
            except KeyboardInterrupt:
                logger.info("🛑 Получен сигнал остановки...")
            finally:
                # Корректная остановка
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска бота: {e}")
            raise

    async def _handle_invite_level_selected(self, query, context, level: str):
        """Обработка выбора уровня доступа для приглашения"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        
        if access_level not in ['operator', 'engineer', 'admin']:
            await query.answer("❌ Недостаточно прав", show_alert=True)
            return
        
        # Проверяем доступность выбранного уровня
        if level == 'engineer' and access_level not in ['engineer', 'admin']:
            await query.answer("❌ Недостаточно прав для создания Engineer приглашения", show_alert=True)
            return
            
        level_names = {
            'user': 'User (Пользователь)',
            'operator': 'Operator (Оператор)',
            'engineer': 'Engineer (Инженер)'
        }
        
        confirmation_text = (
            f"✅ **ПОДТВЕРЖДЕНИЕ ПРИГЛАШЕНИЯ**\n\n"
            f"🎯 **Уровень доступа:** `{level_names.get(level, level)}`\n"
            f"⏰ **Срок действия:** 24 часа\n"
            f"👤 **Приглашает:** @{user.username}\n\n"
            f"Создать уникальную ссылку-приглашение?"
        )
        
        from telegram_bot.bot_utils import build_invitation_confirmation_menu
        menu = build_invitation_confirmation_menu(level)
        
        try:
            await query.edit_message_text(
                confirmation_text,
                reply_markup=menu,
                parse_mode="Markdown"
            )
        except Exception as edit_error:
            if "message is not modified" in str(edit_error).lower():
                await query.answer("✅ Подтверждение приглашения", show_alert=False)
            else:
                raise edit_error

    async def _handle_confirm_invite(self, query, context, level: str):
        """Создание приглашения и генерация уникальной ссылки"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        
        if access_level not in ['operator', 'engineer', 'admin']:
            await query.answer("❌ Недостаточно прав", show_alert=True)
            return
        
        try:
            # Получаем имя бота для создания ссылки
            bot_username = self.application.bot.username if hasattr(self, 'application') and hasattr(self.application, 'bot') else 'your_bot'
            
            # Временно создаём приглашение напрямую в базе (методы загрузятся после перезапуска)
            import uuid
            import datetime
            import sqlite3
            
            invitation_code = str(uuid.uuid4())[:8].upper()
            expires_at = datetime.datetime.now() + datetime.timedelta(hours=24)
            
            # Прямая вставка в базу данных
            conn = sqlite3.connect('kub_commands.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO user_invitations (invitation_code, invited_by, access_level, expires_at)
                VALUES (?, ?, ?, ?)
            ''', (invitation_code, user.id, level, expires_at.isoformat()))
            
            conn.commit()
            conn.close()
            
            # Генерируем ссылку
            invite_link = f"https://t.me/{bot_username}?start=invite_{invitation_code}"
            
            level_names = {
                'user': '👤 User',
                'operator': '⚙️ Operator', 
                'engineer': '🔧 Engineer'
            }
            
            # Первое сообщение - информация о приглашении
            info_text = (
                f"🎉 **ПРИГЛАШЕНИЕ СОЗДАНО**\n\n"
                f"📋 **Детали:**\n"
                f"• **Код:** `{invitation_code}`\n"
                f"• **Уровень:** {level_names.get(level, level)}\n"
                f"• **Срок действия:** 24 часа\n"
                f"• **Создал:** @{user.username}\n\n"
                f"📤 **Ссылка отправлена в следующем сообщении для удобного копирования**"
            )
            
            from telegram_bot.bot_utils import build_user_management_menu
            menu = build_user_management_menu(access_level)
            
            await query.edit_message_text(
                info_text,
                reply_markup=menu,
                parse_mode="Markdown"
            )
            
            # Второе сообщение - только ссылка с кнопками для отправки
            link_text = (
                f"🔗 **Ссылка-приглашение:**\n\n"
                f"{invite_link}\n\n"
                f"📱 **Нажмите на ссылку выше для копирования**\n"
                f"📤 **Или используйте кнопки ниже для отправки**"
            )
            
            from telegram_bot.bot_utils import build_invitation_share_menu
            share_menu = build_invitation_share_menu(invite_link, access_level)
            
            await query.message.reply_text(
                link_text,
                reply_markup=share_menu,
                parse_mode="Markdown"
            )
            
            logger.info(f"✅ Создано приглашение {invitation_code} для уровня {level} пользователем {user.id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания приглашения: {e}")
            from telegram_bot.bot_utils import build_user_management_menu
            menu = build_user_management_menu(access_level)
            
            await query.edit_message_text(
                error_message(f"Ошибка создания приглашения: {str(e)}"),
                reply_markup=menu,
                parse_mode="Markdown"
            )

# =============================================================================
# ОСНОВНАЯ ФУНКЦИЯ
# =============================================================================

def main():
    """Основная функция запуска"""
    print("🤖 TELEGRAM BOT ДЛЯ КУБ-1063 (ЦЕНТРАЛИЗОВАННАЯ КОНФИГУРАЦИЯ)")
    print("=" * 60)
    
    # Получаем токен через конфиг-менеджер
    token = config.telegram.token
    
    if not token:
        print("❌ Не найден TELEGRAM_BOT_TOKEN")
        print("💡 Добавьте токен в config/bot_secrets.json:")
        print('{"telegram": {"bot_token": "your_token", "admin_users": [your_id]}}')
        print("💡 Или установите переменную окружения TELEGRAM_BOT_TOKEN")
        return

    logger.info(f"✅ Токен загружен через ConfigManager")
    logger.info(f"📊 Администраторов: {len(config.telegram.admin_users)}")
    logger.info(f"⚙️ Сервисы включены: telegram={config.services.telegram_enabled}")
    
    # Создаём бота
    bot = KUBTelegramBot(token)

    try:
        import asyncio
        asyncio.run(bot.start_bot())
        
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки...")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    main()