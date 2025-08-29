#!/usr/bin/env python3
"""
Telegram Bot для управления системой КУБ-1063
ИСПРАВЛЕННАЯ ВЕРСИЯ - БЕЗ КОНФЛИКТОВ RS485
"""

import os
import sys
import json
import logging
import asyncio
from typing import Dict, Any
from datetime import datetime

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

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

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('telegram_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class KUBTelegramBot:
    """Telegram Bot для управления КУБ-1063 БЕЗ конфликтов RS485"""
    
    def __init__(self, token: str, config_file: str = "config/telegram_bot.json"):
        self.token = token
        self.config = self._load_config(config_file)
        
        # НЕ создаем UnifiedKUBSystem - работаем через базы данных
        self.kub_system = None
        self.bot_db = TelegramBotDB()
        
        # Telegram Application
        self.application = None
        
        logger.info("🤖 KUBTelegramBot с UX улучшениями инициализирован")
    
    def _load_config(self, config_file: str = "config/telegram_bot.json") -> Dict[str, Any]:
        """Загрузка конфигурации бота"""
        config = {
            "admin_users": [],
            "allowed_users": [],
            "default_access_level": "user",
            "max_message_length": 4000
        }
        
        try:
            # Пробуем загрузить основной конфиг
            with open(config_file, 'r', encoding='utf-8') as f:
                main_config = json.load(f)
                config.update(main_config)
        except FileNotFoundError:
            logger.warning(f"⚠️ Конфиг {config_file} не найден")
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга {config_file}: {e}")
        
        try:
            # Загружаем секреты из bot_secrets.json
            secrets_file = "config/bot_secrets.json"
            with open(secrets_file, 'r', encoding='utf-8') as f:
                secrets = json.load(f)
                
            # Извлекаем admin_users из секретов
            if "telegram" in secrets:
                telegram_config = secrets["telegram"]
                if "admin_users" in telegram_config:
                    config["admin_users"] = telegram_config["admin_users"]
                    logger.info(f"✅ Загружено {len(config['admin_users'])} администраторов")
            
        except FileNotFoundError:
            logger.warning("⚠️ Файл config/bot_secrets.json не найден")
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга bot_secrets.json: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки секретов: {e}")
        
        return config

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
        """Команда /start - регистрация и главное меню"""
        user = update.effective_user
        
        # Показываем печатание
        await send_typing_action(update, context)
        
        # Регистрируем пользователя
        self.bot_db.register_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        access_level = self.bot_db.get_user_access_level(user.id)
        menu = build_main_menu(access_level)
        
        welcome_text = (
            f"👋 Привет, {user.first_name or user.username}!\n\n"
            f"Добро пожаловать в **КУБ-1063 Control Bot**.\n"
            f"Твой уровень доступа: **{access_level}**.\n\n"
            "Выбери действие в меню ниже ⬇️"
        )
        
        await update.message.reply_text(
            welcome_text, 
            reply_markup=menu, 
            parse_mode="Markdown"
        )
        
        self.bot_db.log_user_command(user.id, "start", None, True)
    
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
        
        # Проверяем права админа
        if user.id not in self.config.get("admin_users", []):
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
        
        if user.id not in self.config.get("admin_users", []):
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
        
        if user.id in self.config.get("admin_users", []):
            help_text += (
                "**👑 КОМАНДЫ АДМИНИСТРАТОРА:**\n"
                "• `/promote @user уровень` — изменить права\n"
                "• `/users` — список всех пользователей\n\n"
            )
        
        help_text += f"**🔐 ВАШ УРОВЕНЬ ДОСТУПА:** `{access_level}`\n"
        
        menu = build_main_menu(access_level)
        
        await update.message.reply_text(
            help_text,
            reply_markup=menu,
            parse_mode="Markdown"
        )

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
            
            await query.edit_message_text(
                status_text,
                reply_markup=menu,
                parse_mode="Markdown"
            )
            
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
            
            await query.edit_message_text(
                stats_text,
                reply_markup=menu,
                parse_mode="Markdown"
            )
            
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
        """Настройки (для админов)"""
        user = query.from_user
        
        if not check_user_permission(user.id, "write", self.bot_db):
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message("У вас нет прав для настроек"),
                reply_markup=back_menu,
                parse_mode="Markdown"
            )
            return
        
        access_level = self.bot_db.get_user_access_level(user.id)
        menu = build_main_menu(access_level)
        
        await query.edit_message_text(
            info_message("⚙️ **Настройки системы**\n\nФункции настроек пока находятся в разработке.\n\nВ ближайшем обновлении будут доступны:\n• Настройка уведомлений\n• Управление пользователями\n• Конфигурация системы"),
            reply_markup=menu,
            parse_mode="Markdown"
        )

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
            
            # Обработчик кнопок
            self.application.add_handler(CallbackQueryHandler(self.handle_callback))

            logger.info("🚀 Запуск Telegram Bot...")

            # Инициализируем приложение
            await self.application.initialize()
            await self.application.start()
            
            # Запускаем polling вручную для лучшего контроля
            await self.application.updater.start_polling(drop_pending_updates=True)
            
            logger.info("🤖 Бот запущен и ждет сообщения...")
            
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

# =============================================================================
# ОСНОВНАЯ ФУНКЦИЯ
# =============================================================================

def main():
    """Основная функция запуска"""
    print("🤖 TELEGRAM BOT ДЛЯ КУБ-1063 (ИСПРАВЛЕННЫЙ)")
    print("=" * 50)
    
    # Получаем токен из bot_secrets.json или переменной окружения
    token = None
    
    try:
        # Сначала пробуем bot_secrets.json
        with open("config/bot_secrets.json", 'r', encoding='utf-8') as f:
            secrets = json.load(f)
            if "telegram" in secrets and "bot_token" in secrets["telegram"]:
                token = secrets["telegram"]["bot_token"]
                logger.info("✅ Токен загружен из bot_secrets.json")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось загрузить токен из bot_secrets.json: {e}")
    
    # Если не удалось из файла, пробуем переменную окружения
    if not token:
        token = os.getenv('TELEGRAM_BOT_TOKEN')
        if token:
            logger.info("✅ Токен загружен из переменной окружения")
    
    # Если не удалось из secure_config.py
    if not token:
        try:
            from telegram_bot.secure_config import SecureConfig
            config = SecureConfig()
            token = config.get_bot_token()
            if token:
                logger.info("✅ Токен загружен из secure_config.py")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить из secure_config.py: {e}")

    if not token:
        print("❌ Не найден TELEGRAM_BOT_TOKEN")
        print("💡 Добавьте токен в config/bot_secrets.json:")
        print('{"telegram": {"bot_token": "your_token", "admin_users": [your_id]}}')
        return

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