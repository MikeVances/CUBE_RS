#!/usr/bin/env python3
"""
Telegram Bot для управления системой КУБ-1063
ВКЛЮЧЕНЫ ВСЕ UX УЛУЧШЕНИЯ ПОЛЬЗОВАТЕЛЯ!
- Эмуляция печатания
- Кнопки возврата в главное меню  
- Подтверждения действий
- Улучшенная навигация
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
    """Telegram Bot для управления КУБ-1063 с улучшенным UX"""
    
    def __init__(self, token: str, config_file: str = "config/telegram_bot.json"):
        self.token = token
        self.config = self._load_config(config_file)
        
        # Компоненты системы
        self.kub_system = None
        self.bot_db = TelegramBotDB()
        
        # Telegram Application
        self.application = None
        
        logger.info("🤖 KUBTelegramBot с UX улучшениями инициализирован")
    
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
        """Команда /start - регистрация и главное меню"""
        user = update.effective_user
        
        # 🎯 UX: Показываем печатание
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

        # Проверяем лимит команд
        allowed, message = check_command_rate_limit(user.id, self.bot_db)
        if not allowed:
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await update.message.reply_text(
                error_message(f"Превышен лимит команд\n{message}"),
                reply_markup=back_menu,
                parse_mode="Markdown"
            )
            return

        try:
            # 🎯 UX: Показываем печатание
            await send_typing_action(update, context)
            
            if not self.kub_system:
                access_level = self.bot_db.get_user_access_level(user.id)
                back_menu = build_back_menu(access_level)
                await update.message.reply_text(
                    error_message("Система КУБ-1063 не инициализирована"),
                    reply_markup=back_menu,
                    parse_mode="Markdown"
                )
                return
            
            data = self.kub_system.get_current_data()
            if not data:
                access_level = self.bot_db.get_user_access_level(user.id)
                back_menu = build_back_menu(access_level)
                await update.message.reply_text(
                    error_message("Нет данных от КУБ-1063"),
                    reply_markup=back_menu,
                    parse_mode="Markdown"
                )
                return
            
            status_text = format_sensor_data(data)
            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_main_menu(access_level)
            
            # 🎯 UX: Обрезаем текст если слишком длинный
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
            self.bot_db.log_user_command(user.id, "read", None, False)
    
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /stats - статистика системы"""
        user = update.effective_user

        if not check_user_permission(user.id, "read", self.bot_db):
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await update.message.reply_text(
                error_message("У вас нет прав для чтения статистики"),
                reply_markup=back_menu,
                parse_mode="Markdown"
            )
            return

        try:
            # 🎯 UX: Показываем печатание
            await send_typing_action(update, context)
            
            if not self.kub_system:
                system_stats = {"error": "Система не инициализирована"}
            else:
                system_stats = self.kub_system.get_system_statistics()
            
            # Получаем статистику пользователя
            user_stats = self.bot_db.get_user_stats(user.id)
            
            stats_text = format_system_stats(system_stats)
            
            if user_stats:
                stats_text += f"\n**👤 ВАША СТАТИСТИКА:**\n"
                stats_text += f"• Всего команд: `{user_stats['total_commands']}`\n"
                stats_text += f"• За сегодня: `{user_stats['commands_today']}`\n"
                stats_text += f"• Успешность: `{user_stats['success_rate']:.1f}%`\n"
            
            # 🎯 UX: Специальное меню для статистики
            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_stats_menu(access_level)
            
            # 🎯 UX: Обрезаем текст если слишком длинный
            stats_text = truncate_text(stats_text, 4000)
            
            await update.message.reply_text(
                stats_text,
                parse_mode='Markdown',
                reply_markup=menu
            )
            
            self.bot_db.log_user_command(user.id, "stats", None, True)
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await update.message.reply_text(
                error_message(f"Ошибка получения статистики: {str(e)}"),
                reply_markup=back_menu,
                parse_mode="Markdown"
            )
            self.bot_db.log_user_command(user.id, "stats", None, False)
    
    async def cmd_reset_alarms(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /reset - сброс аварий"""
        user = update.effective_user

        # Проверяем права доступа
        if not check_user_permission(user.id, "reset_alarms", self.bot_db):
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await update.message.reply_text(
                error_message("У вас нет прав для сброса аварий"),
                reply_markup=back_menu,
                parse_mode="Markdown"
            )
            return

        # 🎯 UX: Показываем подтверждение с кнопками
        confirmation_menu = build_confirmation_menu("reset_alarms_confirmed", "main_menu")
        
        await update.message.reply_text(
            warning_message("Вы уверены, что хотите сбросить все аварии?\n\nЭто действие нельзя отменить!"),
            reply_markup=confirmation_menu,
            parse_mode="Markdown"
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help - справка"""
        user = update.effective_user
        
        # 🎯 UX: Показываем печатание
        await send_typing_action(update, context)
        
        access_level = self.bot_db.get_user_access_level(user.id)
        
        help_text = (
            "ℹ️ **Справка по КУБ-1063 Control Bot**\n\n"
            "**📱 ОСНОВНЫЕ КОМАНДЫ:**\n"
            "• `/start` — главное меню\n"
            "• `/status` — показания датчиков\n"
            "• `/stats` — статистика системы\n"
            "• `/help` — эта справка\n\n"
            "**🔘 КНОПКИ МЕНЮ:**\n"
            "• 📊 Показания — текущие данные\n"
            "• 🔄 Обновить — свежие данные\n"
            "• 📈 Статистика — история и статистика\n"
            "• 🏠 Главное меню — возврат в главное меню\n"
        )
        
        if access_level in ("operator", "admin", "engineer"):
            help_text += "• 🚨 Сброс аварий — сброс активных аварий\n"
        
        if access_level in ("admin", "engineer"):
            help_text += "• ⚙️ Настройки — управление системой\n"
        
        help_text += f"\n**🔐 ВАШ УРОВЕНЬ ДОСТУПА:** `{access_level}`\n"
        
        permissions = self.bot_db.get_access_permissions(access_level)
        if permissions:
            help_text += f"• Лимит команд: `{permissions.get('commands_per_hour', 5)}/час`\n"
        
        help_text += "\n💡 **Совет:** Используйте кнопки для быстрой навигации!"
        
        menu = build_main_menu(access_level)
        
        await update.message.reply_text(
            help_text,
            reply_markup=menu,
            parse_mode="Markdown"
        )
        
        self.bot_db.log_user_command(user.id, "help", None, True)
    
    # =======================================================================
    # ОБРАБОТЧИКИ CALLBACK QUERY (INLINE КНОПКИ)
    # =======================================================================
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🎯 UX: Обработчик inline кнопок с улучшенной навигацией"""
        query = update.callback_query
        await query.answer()  # Убираем "часики" на кнопке
        
        data = query.data
        
        try:
            # 🎯 UX: Показываем печатание для всех действий
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
        """🎯 UX: Показать главное меню"""
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
        """🎯 UX: Обновление статуса с улучшенной обработкой"""
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
            if not self.kub_system:
                access_level = self.bot_db.get_user_access_level(user.id)
                back_menu = build_back_menu(access_level)
                await query.edit_message_text(
                    error_message("Система КУБ-1063 не инициализирована"),
                    reply_markup=back_menu,
                    parse_mode="Markdown"
                )
                return
            
            data = self.kub_system.get_current_data()
            status_text = format_sensor_data(data) if data else error_message("Нет данных")
            
            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_main_menu(access_level)
            
            # 🎯 UX: Обрезаем текст если слишком длинный
            status_text = truncate_text(status_text, 4000)
            
            await query.edit_message_text(
                status_text,
                reply_markup=menu,
                parse_mode="Markdown"
            )
            
            self.bot_db.log_user_command(user.id, "read", None, True)
            
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
        """🎯 UX: Обновление статистики с специальным меню"""
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
            if not self.kub_system:
                system_stats = {"error": "Система не инициализирована"}
            else:
                system_stats = self.kub_system.get_system_statistics()
            
            user_stats = self.bot_db.get_user_stats(user.id)
            
            stats_text = format_system_stats(system_stats)
            
            if user_stats:
                stats_text += f"\n**👤 ВАША СТАТИСТИКА:**\n"
                stats_text += f"• Всего команд: `{user_stats['total_commands']}`\n"
                stats_text += f"• За сегодня: `{user_stats['commands_today']}`\n"
                stats_text += f"• Успешность: `{user_stats['success_rate']:.1f}%`\n"
            
            # 🎯 UX: Специальное меню для статистики
            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_stats_menu(access_level)
            
            # 🎯 UX: Обрезаем текст если слишком длинный
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
        """🎯 UX: Запрос подтверждения сброса аварий с кнопками"""
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
        
        # 🎯 UX: Используем специальное меню подтверждения
        confirmation_menu = build_confirmation_menu("reset_alarms_confirmed", "main_menu")
        
        await query.edit_message_text(
            warning_message("Вы уверены, что хотите сбросить все аварии?\n\nЭто действие нельзя отменить!"),
            reply_markup=confirmation_menu,
            parse_mode="Markdown"
        )

    async def _handle_confirm_reset_alarms(self, query, context):
        """🎯 UX: Подтвержденный сброс аварий с обратной связью"""
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
            if not self.kub_system:
                access_level = self.bot_db.get_user_access_level(user.id)
                back_menu = build_back_menu(access_level)
                await query.edit_message_text(
                    error_message("Система КУБ-1063 не инициализирована"),
                    reply_markup=back_menu,
                    parse_mode="Markdown"
                )
                return
            
            # 🎯 UX: Показываем процесс выполнения
            await query.edit_message_text(
                loading_message("Выполняется сброс аварий..."),
                parse_mode="Markdown"
            )
            
            # Выполняем сброс аварий через систему
            result = self.kub_system.reset_alarms()
            
            access_level = self.bot_db.get_user_access_level(user.id)
            menu = build_main_menu(access_level)
            
            if result:
                await query.edit_message_text(
                    success_message("🔄 Все аварии были успешно сброшены!"),
                    reply_markup=menu,
                    parse_mode="Markdown"
                )
                self.bot_db.log_user_command(user.id, "reset_alarms", "0x0020", True)
            else:
                await query.edit_message_text(
                    error_message("Ошибка выполнения сброса аварий\n\nПопробуйте еще раз или обратитесь к администратору."),
                    reply_markup=menu,
                    parse_mode="Markdown"
                )
                self.bot_db.log_user_command(user.id, "reset_alarms", "0x0020", False)
                
        except Exception as e:
            logger.error(f"❌ Ошибка сброса аварий: {e}")
            access_level = self.bot_db.get_user_access_level(user.id)
            back_menu = build_back_menu(access_level)
            await query.edit_message_text(
                error_message(f"Ошибка: {str(e)}\n\nОбратитесь к администратору."),
                reply_markup=back_menu,
                parse_mode="Markdown"
            )
            self.bot_db.log_user_command(user.id, "reset_alarms", "0x0020", False)

    async def _handle_show_help(self, query, context):
        """🎯 UX: Показать справку через callback"""
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
        """🎯 UX: Настройки (для админов) с обратной связью"""
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
    # ЗАПУСК И ОСТАНОВКА БОТА
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

            logger.info("🚀 Запуск Telegram Bot с UX улучшениями...")

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
                if hasattr(self.application, 'updater') and self.application.updater.running:
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
    try:
        from secure_config import SecureConfig
        config = SecureConfig()
        token = config.get_bot_token()
    except ImportError:
        # Fallback если secure_config недоступен
        token = os.getenv('TELEGRAM_BOT_TOKEN')

    if not token:
        print("❌ Не найден TELEGRAM_BOT_TOKEN")
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
    print("🤖 TELEGRAM BOT ДЛЯ КУБ-1063 (Enhanced UX)")
    print("=" * 50)
    asyncio.run(main())