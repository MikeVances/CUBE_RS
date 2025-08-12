#!/usr/bin/env python3
"""
Telegram Bot для управления системой КУБ-1063
Использует UnifiedKUBSystem для чтения данных и выполнения команд
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
from modbus.unified_system import UnifiedKUBSystem
from bot_database import TelegramBotDB
from bot_permissions import check_user_permission, get_user_access_level
from bot_utils import (
    format_sensor_data, format_system_stats, build_main_menu, send_typing_action, error_message
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
    """Telegram Bot для управления КУБ-1063"""
    
    def __init__(self, token: str, config_file: str = "config/telegram_bot.json"):
        self.token = token
        self.config = self._load_config(config_file)
        
        # Компоненты системы
        self.kub_system = None
        self.bot_db = TelegramBotDB()
        
        # Telegram Application
        self.application = None
        
        logger.info("🤖 KUBTelegramBot инициализирован")
    
    def _load_config(self, config_file: str) -> Dict[str, Any]:
        """Загрузка конфигурации бота"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"⚠️ Конфиг {config_file} не найден, используем defaults")
            return {
                "allowed_users": [],
                "admin_users": [],
                "default_access_level": "user",
                "command_timeout": 30,
                "max_message_length": 4000
            }
    
    async def initialize_system(self):
        """Инициализация UnifiedKUBSystem"""
        try:
            logger.info("🚀 Инициализация UnifiedKUBSystem...")
            self.kub_system = UnifiedKUBSystem()
            self.kub_system.start()
            logger.info("✅ UnifiedKUBSystem запущен")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации системы: {e}")
            return False
    
    # =======================================================================
    # ОБРАБОТЧИКИ КОМАНД
    # =======================================================================
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        self.bot_db.register_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        access_level = self.bot_db.get_user_access_level(user.id)
        menu = build_main_menu(access_level)
        welcome_text = (
            f"👋 Привет, {user.first_name or user.username}!\n"
            f"Добро пожаловать в КУБ-1063 Control Bot.\n"
            f"Твой уровень доступа: <b>{access_level}</b>.\n\n"
            "Выбери действие в меню ниже ⬇️"
        )
        await update.message.reply_text(welcome_text, reply_markup=menu, parse_mode="HTML")
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status - показать текущие данные"""
        user = update.effective_user

        # Проверяем права доступа
        if not check_user_permission(user.id, "read", self.bot_db):
            await update.message.reply_text(error_message("У вас нет прав для чтения данных"), parse_mode="HTML")
            return

        try:
            await send_typing_action(update, context)
            data = self.kub_system.get_current_data()
            if not data:
                await update.message.reply_text(error_message("Нет данных от КУБ-1063"), parse_mode="HTML")
                return
            status_text = format_sensor_data(data)
            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_main_menu(access_level)
            await update.message.reply_text(
                status_text,
                parse_mode='Markdown',
                reply_markup=menu
            )
            self.bot_db.log_user_command(user.id, "read", None, True)
        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса: {e}")
            await update.message.reply_text(error_message(f"Ошибка получения данных: {str(e)}"), parse_mode="HTML")
    
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /stats - статистика системы"""
        user = update.effective_user

        if not check_user_permission(user.id, "read", self.bot_db):
            await update.message.reply_text(error_message("У вас нет прав для просмотра статистики"), parse_mode="HTML")
            return

        try:
            await send_typing_action(update, context)
            stats = self.kub_system.get_system_statistics()
            stats_text = format_system_stats(stats)
            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_main_menu(access_level)
            await update.message.reply_text(
                stats_text,
                parse_mode='Markdown',
                reply_markup=menu
            )
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            await update.message.reply_text(error_message(f"Ошибка: {str(e)}"), parse_mode="HTML")
    
    async def cmd_reset_alarms(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда сброса аварий"""
        user = update.effective_user

        # Проверяем права
        if not check_user_permission(user.id, "reset_alarms", self.bot_db):
            await update.message.reply_text(error_message("У вас нет прав для сброса аварий"), parse_mode="HTML")
            return

        try:
            await send_typing_action(update, context)
            # Подтверждение сброса аварий
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Подтвердить", callback_data="reset_alarms_confirmed")],
                [InlineKeyboardButton("❌ Отмена", callback_data="main_menu")]
            ])
            await update.message.reply_text(
                "⚠️ <b>ВНИМАНИЕ!</b>\nВы уверены, что хотите сбросить все аварии?",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"❌ Ошибка подготовки сброса аварий: {e}")
            await update.message.reply_text(error_message(f"Ошибка: {str(e)}"), parse_mode="HTML")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help - справка"""
        user = update.effective_user
        access_level = get_user_access_level(user.id, self.bot_db)
        help_text = (
            "ℹ️ <b>СПРАВКА ПО КОМАНДАМ КУБ-1063 BOT</b>\n\n"
            "• <b>/start</b> — Главное меню\n"
            "• <b>/status</b> — Показания датчиков 🌡️\n"
            "• <b>/stats</b> — Статистика системы 📊\n"
            "• <b>/help</b> — Эта справка\n\n"
            f"Ваш уровень доступа: <b>{access_level}</b>\n"
            f"{self._get_access_info(access_level)}\n\n"
            "<i>Для вопросов и поддержки обращайтесь к администратору системы.</i>"
        )
        menu = build_main_menu(access_level)
        await update.message.reply_text(help_text, parse_mode='HTML', reply_markup=menu)

    # =======================================================================
    # ОБРАБОТЧИКИ CALLBACK'ОВ (КНОПОК)
    # =======================================================================

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик inline кнопок"""
        query = update.callback_query
        await query.answer()
        user = query.from_user
        data = query.data

        if data == "refresh_status":
            await self._handle_refresh_status(query, context)
        elif data == "show_stats":
            await self._handle_refresh_stats(query, context)
        elif data == "refresh_stats":
            await self._handle_refresh_stats(query, context)
        elif data == "reset_alarms":
            await self._handle_reset_alarms(query, context)
        elif data == "reset_alarms_confirmed":
            await self._handle_confirm_reset_alarms(query, context)
        elif data == "main_menu":
            await self._handle_main_menu(query, context)
        else:
            await query.edit_message_text(error_message("Неизвестная команда"), parse_mode="HTML")

    async def _handle_main_menu(self, query, context):
        """Показать главное меню"""
        user = query.from_user
        access_level = self.bot_db.get_user_access_level(user.id)
        menu = build_main_menu(access_level)
        await query.edit_message_text(
            "Главное меню:",
            reply_markup=menu,
            parse_mode="HTML"
        )

    async def _handle_refresh_status(self, query, context):
        """Обновление статуса"""
        user = query.from_user
        try:
            await send_typing_action(query, context)
            data = self.kub_system.get_current_data()
            status_text = format_sensor_data(data) if data else error_message("Нет данных")
            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_main_menu(access_level)
            await query.edit_message_text(
                status_text,
                parse_mode='Markdown',
                reply_markup=menu
            )
        except Exception as e:
            await query.edit_message_text(error_message(f"Ошибка обновления: {str(e)}"), parse_mode="HTML")

    async def _handle_refresh_stats(self, query, context):
        """Обновление статистики"""
        user = query.from_user
        try:
            await send_typing_action(query, context)
            stats = self.kub_system.get_system_statistics()
            stats_text = format_system_stats(stats)
            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_main_menu(access_level)
            await query.edit_message_text(
                stats_text,
                parse_mode='Markdown',
                reply_markup=menu
            )
        except Exception as e:
            await query.edit_message_text(error_message(f"Ошибка: {str(e)}"), parse_mode="HTML")

    async def _handle_reset_alarms(self, query, context):
        """Показать подтверждение на сброс аварий"""
        user = query.from_user
        if not check_user_permission(user.id, "reset_alarms", self.bot_db):
            await query.edit_message_text(error_message("У вас нет прав для сброса аварий"), parse_mode="HTML")
            return
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Подтвердить", callback_data="reset_alarms_confirmed")],
            [InlineKeyboardButton("❌ Отмена", callback_data="main_menu")]
        ])
        await query.edit_message_text(
            "⚠️ <b>ВНИМАНИЕ!</b>\nВы уверены, что хотите сбросить все аварии?",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    async def _handle_confirm_reset_alarms(self, query, context):
        """Выполнить сброс аварий после подтверждения"""
        user = query.from_user
        if not check_user_permission(user.id, "reset_alarms", self.bot_db):
            await query.edit_message_text(error_message("У вас нет прав для сброса аварий"), parse_mode="HTML")
            return
        try:
            await send_typing_action(query, context)
            success, result = self.kub_system.add_write_command(
                register=0x0020,
                value=1,
                source_ip="telegram_bot",
                user_info=json.dumps({
                    "telegram_id": user.id,
                    "username": user.username,
                    "source": "telegram_bot_button"
                })
            )
            if success:
                await query.edit_message_text(
                    "🔄 Все аварии были успешно сброшены.",
                    parse_mode="HTML"
                )
                self.bot_db.log_user_command(user.id, "write", "0x0020", True)
            else:
                await query.edit_message_text(error_message(f"Ошибка: {result}"), parse_mode="HTML")
        except Exception as e:
            await query.edit_message_text(error_message(f"Ошибка: {str(e)}"), parse_mode="HTML")

    def _get_access_info(self, access_level: str) -> str:
        """Информация о правах доступа"""
        access_info = {
            'user': "👀 <b>Доступ:</b> только чтение показаний",
            'operator': "🔧 <b>Доступ:</b> чтение + сброс аварий",
            'admin': "⚙️ <b>Доступ:</b> чтение + управление + настройки",
            'engineer': "🛠️ <b>Доступ:</b> полный доступ ко всем функциям"
        }
        return access_info.get(access_level, "❓ Неизвестный уровень доступа")

    # =======================================================================
    # ЗАПУСК БОТА
    # =======================================================================

    async def start_bot(self):
        """Запуск Telegram Bot"""
        try:
            # Инициализируем систему
            if not await self.initialize_system():
                logger.error("❌ Не удалось инициализировать систему")
                return False

            # Создаём Telegram Application
            self.application = Application.builder().token(self.token).build()

            # Регистрируем обработчики команд
            self.application.add_handler(CommandHandler("start", self.cmd_start))
            self.application.add_handler(CommandHandler("status", self.cmd_status))
            self.application.add_handler(CommandHandler("stats", self.cmd_stats))
            self.application.add_handler(CommandHandler("reset", self.cmd_reset_alarms))
            self.application.add_handler(CommandHandler("help", self.cmd_help))

            # Обработчик inline кнопок
            self.application.add_handler(CallbackQueryHandler(self.handle_callback))

            logger.info("🚀 Запуск Telegram Bot...")

            # Инициализируем приложение
            await self.application.initialize()
            await self.application.start()

            # Запускаем polling
            await self.application.updater.start_polling(drop_pending_updates=True)

            # Ждём остановки
            await self.application.updater.idle()

        except Exception as e:
            logger.error(f"❌ Ошибка запуска бота: {e}")
            raise

    async def stop_bot(self):
        """Остановка бота"""
        try:
            logger.info("🛑 Остановка Telegram Bot...")

            if self.application:
                if self.application.updater.running:
                    await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()

            if self.kub_system:
                self.kub_system.stop()

            logger.info("🛑 Telegram Bot остановлен")

        except Exception as e:
            logger.error(f"❌ Ошибка остановки: {e}")

# =============================================================================
# ОСНОВНАЯ ФУНКЦИЯ
# =============================================================================

async def main():
    """Основная функция запуска"""
    # Получаем токен бота
    from telegram_bot.secure_config import SecureConfig
    config = SecureConfig()
    token = config.get_bot_token()

    if not token:
        print("❌ Не найден TELEGRAM_BOT_TOKEN в переменных окружения")
        print("💡 Установите токен: export TELEGRAM_BOT_TOKEN='your_token_here'")
        return

    # Создаём и запускаем бота
    bot = KUBTelegramBot(token)

    try:
        await bot.start_bot()
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки...")
        await bot.stop_bot()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        await bot.stop_bot()

if __name__ == "__main__":
    print("🤖 TELEGRAM BOT ДЛЯ КУБ-1063")
    print("=" * 50)
    asyncio.run(main())