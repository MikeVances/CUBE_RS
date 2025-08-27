#!/usr/bin/env python3
"""
Multi-Tenant Telegram Bot для CUBE_RS
Поддержка множественных организаций и устройств
Каждый пользователь видит только свое оборудование
"""

import os
import sys
import json
import logging
import asyncio
from typing import Dict, Any, List
from datetime import datetime

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Telegram Bot imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Наши модули
from modbus.unified_system import UnifiedKUBSystem
from bot_database import TelegramBotDB
from bot_permissions import check_user_permission, check_command_rate_limit
from bot_utils import (
    format_sensor_data, format_system_stats, 
    build_main_menu, build_confirmation_menu, build_back_menu,
    send_typing_action, error_message, success_message, info_message, warning_message
)

# Multi-tenant модуль
from multi_tenant_manager import MultiTenantManager, MultiTenantTelegramMixin

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('telegram_bot_multitenant.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class MultiTenantKUBTelegramBot(MultiTenantTelegramMixin):
    """Multi-Tenant Telegram Bot для управления КУБ-1063 устройствами"""
    
    def __init__(self, token: str, config_file: str = "config/telegram_bot.json"):
        self.token = token
        self.config = self._load_config(config_file)
        
        # Компоненты системы
        self.kub_system = None
        self.bot_db = TelegramBotDB()
        self.mt_manager = MultiTenantManager()  # Multi-tenant менеджер
        
        # Telegram Application
        self.application = None
        
        # Состояние пользователей (для навигации между устройствами)
        self.user_states = {}
        
        logger.info("🏭 Multi-Tenant KUB Telegram Bot инициализирован")
    
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
    # MULTI-TENANT ОБРАБОТЧИКИ КОМАНД
    # =======================================================================
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start с multi-tenant поддержкой"""
        user = update.effective_user
        
        await send_typing_action(update, context)
        
        # Регистрируем в обеих системах
        self.bot_db.register_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        self.mt_manager.register_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        # Получаем устройства пользователя
        devices = self.mt_manager.get_user_devices(user.id)
        organizations = self.mt_manager.get_user_organizations(user.id)
        
        if not devices:
            welcome_text = (
                f"👋 Привет, {user.first_name or user.username}!\n\n"
                f"🏭 **КУБ-1063 Multi-Tenant Control Bot**\n\n"
                f"❌ У вас пока нет доступа к устройствам.\n"
                f"Обратитесь к администратору для получения доступа к оборудованию.\n\n"
                f"📧 Для получения доступа укажите:\n"
                f"• Ваш Telegram ID: `{user.id}`\n"
                f"• Организацию, к которой хотите получить доступ"
            )
            
            await update.message.reply_text(
                welcome_text,
                parse_mode="Markdown"
            )
            return
        
        # Формируем приветствие с информацией об устройствах
        welcome_text = (
            f"👋 Привет, {user.first_name or user.username}!\n\n"
            f"🏭 **КУБ-1063 Multi-Tenant Control Bot**\n\n"
        )
        
        # Добавляем информацию об организациях
        if organizations:
            welcome_text += f"🏢 **Ваши организации:**\n"
            for org in organizations:
                welcome_text += f"• {org['name']} ({org['role']})\n"
            welcome_text += "\n"
        
        # Добавляем краткую информацию об устройствах
        welcome_text += f"📦 **Доступных устройств:** {len(devices)}\n\n"
        welcome_text += "Выберите действие в меню ниже ⬇️"
        
        menu = self._build_multitenant_main_menu(user.id)
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=menu,
            parse_mode="Markdown"
        )
        
        self.bot_db.log_user_command(user.id, "start", None, True)
    
    async def cmd_devices(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /devices - список доступных устройств"""
        user = update.effective_user
        
        await send_typing_action(update, context)
        
        devices = self.mt_manager.get_user_devices(user.id)
        
        if not devices:
            await update.message.reply_text(
                error_message("У вас нет доступа к устройствам\n\nОбратитесь к администратору."),
                parse_mode="Markdown"
            )
            return
        
        # Группируем устройства по организациям
        devices_by_org = {}
        for device in devices:
            org_name = device.organization_name
            if org_name not in devices_by_org:
                devices_by_org[org_name] = []
            devices_by_org[org_name].append(device)
        
        text = f"🏭 **Ваши устройства ({len(devices)}):**\n\n"
        
        for org_name, org_devices in devices_by_org.items():
            text += f"🏢 **{org_name}**\n"
            for device in org_devices:
                access_icon = {"read": "👁️", "write": "✏️", "admin": "⚙️"}.get(device.access_level, "❓")
                text += f"  {access_icon} `{device.device_id}` - {device.device_name}\n"
                if device.location:
                    text += f"    📍 {device.location}\n"
            text += "\n"
        
        text += "💡 Используйте кнопки для быстрого доступа к устройствам."
        
        menu = self._build_device_selection_menu(devices)
        
        await update.message.reply_text(
            text,
            reply_markup=menu,
            parse_mode="Markdown"
        )
        
        self.bot_db.log_user_command(user.id, "devices", None, True)
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status с выбором устройства"""
        user = update.effective_user
        
        devices = self.mt_manager.get_user_devices(user.id)
        
        if not devices:
            await update.message.reply_text(
                error_message("У вас нет доступа к устройствам"),
                parse_mode="Markdown"
            )
            return
        
        if len(devices) == 1:
            # Если устройство одно - показываем его данные сразу
            await self._show_device_status(update, context, devices[0].device_id)
        else:
            # Если устройств несколько - показываем меню выбора
            text = "📊 **Выберите устройство для просмотра показаний:**"
            menu = self._build_device_selection_menu(devices, action_prefix="status_")
            
            await update.message.reply_text(
                text,
                reply_markup=menu,
                parse_mode="Markdown"
            )
    
    async def _show_device_status(self, update, context, device_id: str):
        """Показать статус конкретного устройства"""
        user = update.effective_user if hasattr(update, 'effective_user') else update.callback_query.from_user
        
        # Проверяем доступ
        if not self.mt_manager.check_device_access(user.id, device_id, "read"):
            text = error_message("У вас нет доступа к этому устройству")
            if hasattr(update, 'message'):
                await update.message.reply_text(text, parse_mode="Markdown")
            else:
                await update.callback_query.edit_message_text(text, parse_mode="Markdown")
            return
        
        await send_typing_action(update, context)
        
        # Получаем информацию об устройстве
        devices = self.mt_manager.get_user_devices(user.id)
        device = next((d for d in devices if d.device_id == device_id), None)
        
        if not device:
            text = error_message("Устройство не найдено")
            if hasattr(update, 'message'):
                await update.message.reply_text(text, parse_mode="Markdown")
            else:
                await update.callback_query.edit_message_text(text, parse_mode="Markdown")
            return
        
        try:
            # Получаем данные с устройства по Modbus Slave ID
            if not self.kub_system:
                text = error_message("Система КУБ-1063 не инициализирована")
            else:
                # Здесь нужно расширить UnifiedKUBSystem для поддержки конкретных slave_id
                # Пока используем общий метод
                raw_data = self.kub_system.get_current_data()
                
                if raw_data:
                    # Фильтруем и обогащаем данные через multi-tenant менеджер
                    filtered_data = self.mt_manager.filter_data_for_user(
                        user.id, device.modbus_slave_id, raw_data
                    )
                    
                    if filtered_data:
                        text = self._format_device_status(device, filtered_data)
                    else:
                        text = error_message("Нет данных с устройства")
                else:
                    text = error_message("Нет связи с устройством")
            
            menu = self._build_device_action_menu(device)
            
            if hasattr(update, 'message'):
                await update.message.reply_text(text, reply_markup=menu, parse_mode="Markdown")
            else:
                await update.callback_query.edit_message_text(text, reply_markup=menu, parse_mode="Markdown")
            
            self.bot_db.log_user_command(user.id, "read", device_id, True)
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса устройства {device_id}: {e}")
            text = error_message(f"Ошибка получения данных: {str(e)}")
            
            if hasattr(update, 'message'):
                await update.message.reply_text(text, parse_mode="Markdown")
            else:
                await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    
    def _format_device_status(self, device, data: Dict[str, Any]) -> str:
        """Форматирование статуса устройства с контекстом"""
        
        # Заголовок с информацией об устройстве
        header = (
            f"🏭 **{device.organization_name}**\n"
            f"📦 **{device.device_name}** (`{device.device_id}`)\n"
        )
        
        if device.location:
            header += f"📍 {device.location}\n"
        
        header += f"🔗 Modbus ID: `{device.modbus_slave_id}`\n\n"
        
        # Используем существующую функцию форматирования данных
        formatted_data = format_sensor_data(data)
        
        return header + formatted_data
    
    # =======================================================================
    # ОБРАБОТЧИКИ CALLBACK QUERY (MULTI-TENANT)
    # =======================================================================
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик inline кнопок с multi-tenant поддержкой"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        try:
            await send_typing_action(query, context)
            
            if data.startswith("device_"):
                device_id = data.replace("device_", "")
                await self._show_device_status(query, context, device_id)
            
            elif data.startswith("status_"):
                device_id = data.replace("status_", "")
                await self._show_device_status(query, context, device_id)
            
            elif data.startswith("refresh_"):
                device_id = data.replace("refresh_", "")
                await self._show_device_status(query, context, device_id)
            
            elif data.startswith("reset_alarms_"):
                device_id = data.replace("reset_alarms_", "")
                await self._handle_reset_alarms_for_device(query, context, device_id)
            
            elif data.startswith("confirm_reset_"):
                device_id = data.replace("confirm_reset_", "")
                await self._confirm_reset_alarms_for_device(query, context, device_id)
            
            elif data == "show_devices":
                await self._handle_show_devices(query, context)
            
            elif data == "main_menu":
                await self._handle_main_menu(query, context)
            
            elif data == "show_organizations":
                await self._handle_show_organizations(query, context)
            
            else:
                await query.edit_message_text(
                    error_message("Неизвестная команда"),
                    parse_mode="Markdown"
                )
        
        except Exception as e:
            logger.error(f"❌ Ошибка обработки callback {data}: {e}")
            await query.edit_message_text(
                error_message(f"Ошибка выполнения команды: {str(e)}"),
                parse_mode="Markdown"
            )
    
    async def _handle_reset_alarms_for_device(self, query, context, device_id: str):
        """Сброс аварий для конкретного устройства"""
        user = query.from_user
        
        if not self.mt_manager.check_device_access(user.id, device_id, "write"):
            await query.edit_message_text(
                error_message("У вас нет прав для сброса аварий на этом устройстве"),
                parse_mode="Markdown"
            )
            return
        
        # Получаем информацию об устройстве
        devices = self.mt_manager.get_user_devices(user.id)
        device = next((d for d in devices if d.device_id == device_id), None)
        
        if not device:
            await query.edit_message_text(
                error_message("Устройство не найдено"),
                parse_mode="Markdown"
            )
            return
        
        confirmation_text = (
            f"⚠️ **СБРОС АВАРИЙ**\n\n"
            f"🏭 **{device.organization_name}**\n"
            f"📦 **{device.device_name}**\n"
            f"📍 {device.location or 'Не указано'}\n\n"
            f"Вы уверены, что хотите сбросить все аварии на этом устройстве?\n\n"
            f"⚠️ Это действие нельзя отменить!"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_reset_{device_id}")],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"device_{device_id}")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            confirmation_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    # =======================================================================
    # УТИЛИТЫ ПОСТРОЕНИЯ МЕНЮ
    # =======================================================================
    
    def _build_multitenant_main_menu(self, telegram_id: int) -> InlineKeyboardMarkup:
        """Построение главного меню с учетом доступных устройств"""
        devices = self.mt_manager.get_user_devices(telegram_id)
        
        buttons = []
        
        if devices:
            if len(devices) == 1:
                # Если устройство одно - прямая кнопка к нему
                device = devices[0]
                buttons.append([InlineKeyboardButton(
                    f"📊 {device.device_name}", 
                    callback_data=f"device_{device.device_id}"
                )])
            else:
                # Если устройств несколько - кнопка выбора
                buttons.append([InlineKeyboardButton("📦 Мои устройства", callback_data="show_devices")])
            
            buttons.append([InlineKeyboardButton("🔄 Обновить данные", callback_data="show_devices")])
            buttons.append([InlineKeyboardButton("🏢 Мои организации", callback_data="show_organizations")])
        
        buttons.append([InlineKeyboardButton("ℹ️ Помощь", callback_data="show_help")])
        
        return InlineKeyboardMarkup(buttons)
    
    def _build_device_selection_menu(self, devices: List, action_prefix: str = "device_") -> InlineKeyboardMarkup:
        """Построение меню выбора устройства"""
        buttons = []
        
        # Группируем устройства по организациям для лучшего UX
        devices_by_org = {}
        for device in devices:
            org_name = device.organization_name
            if org_name not in devices_by_org:
                devices_by_org[org_name] = []
            devices_by_org[org_name].append(device)
        
        for org_name, org_devices in devices_by_org.items():
            # Если в организации больше одного устройства, показываем название организации
            if len(devices_by_org) > 1 or len(org_devices) > 1:
                for device in org_devices:
                    button_text = f"{device.device_name}"
                    if len(devices_by_org) > 1:
                        button_text = f"{org_name}: {device.device_name}"
                    
                    buttons.append([InlineKeyboardButton(
                        button_text,
                        callback_data=f"{action_prefix}{device.device_id}"
                    )])
            else:
                # Если устройство одно, показываем без префикса организации
                device = org_devices[0]
                buttons.append([InlineKeyboardButton(
                    device.device_name,
                    callback_data=f"{action_prefix}{device.device_id}"
                )])
        
        buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        
        return InlineKeyboardMarkup(buttons)
    
    def _build_device_action_menu(self, device) -> InlineKeyboardMarkup:
        """Построение меню действий для конкретного устройства"""
        buttons = [
            [InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_{device.device_id}")],
        ]
        
        # Добавляем кнопки в зависимости от уровня доступа
        if device.access_level in ("write", "admin"):
            buttons.append([InlineKeyboardButton("🚨 Сброс аварий", callback_data=f"reset_alarms_{device.device_id}")])
        
        if device.access_level == "admin":
            buttons.append([InlineKeyboardButton("⚙️ Настройки", callback_data=f"settings_{device.device_id}")])
        
        buttons.extend([
            [InlineKeyboardButton("📦 Другие устройства", callback_data="show_devices")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ])
        
        return InlineKeyboardMarkup(buttons)
    
    # =======================================================================
    # ДОПОЛНИТЕЛЬНЫЕ ОБРАБОТЧИКИ
    # =======================================================================
    
    async def _handle_show_devices(self, query, context):
        """Показать список устройств"""
        user = query.from_user
        devices = self.mt_manager.get_user_devices(user.id)
        
        if not devices:
            await query.edit_message_text(
                error_message("У вас нет доступа к устройствам"),
                parse_mode="Markdown"
            )
            return
        
        text = f"📦 **Выберите устройство ({len(devices)}):**"
        menu = self._build_device_selection_menu(devices)
        
        await query.edit_message_text(
            text,
            reply_markup=menu,
            parse_mode="Markdown"
        )
    
    async def _handle_show_organizations(self, query, context):
        """Показать организации пользователя"""
        user = query.from_user
        organizations = self.mt_manager.get_user_organizations(user.id)
        
        if not organizations:
            await query.edit_message_text(
                error_message("Вы не состоите ни в одной организации"),
                parse_mode="Markdown"
            )
            return
        
        text = f"🏢 **Ваши организации ({len(organizations)}):**\n\n"
        
        for org in organizations:
            role_icon = {"owner": "👑", "admin": "⚙️", "operator": "🔧", "viewer": "👁️"}.get(org['role'], "❓")
            text += f"{role_icon} **{org['name']}** ({org['role']})\n"
            if org['description']:
                text += f"   ℹ️ {org['description']}\n"
            text += "\n"
        
        menu = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Мои устройства", callback_data="show_devices")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ])
        
        await query.edit_message_text(
            text,
            reply_markup=menu,
            parse_mode="Markdown"
        )
    
    async def _handle_main_menu(self, query, context):
        """Показать главное меню"""
        user = query.from_user
        
        text = "🏠 **Главное меню**\n\nВыберите действие:"
        menu = self._build_multitenant_main_menu(user.id)
        
        await query.edit_message_text(
            text,
            reply_markup=menu,
            parse_mode="Markdown"
        )
    
    # =======================================================================
    # ЗАПУСК И ОСТАНОВКА БОТА
    # =======================================================================
    
    async def start_bot(self):
        """Запуск Multi-Tenant Telegram Bot"""
        try:
            if not await self.initialize_system():
                logger.error("❌ Не удалось инициализировать систему")
                return False

            self.application = Application.builder().token(self.token).build()

            # Регистрируем обработчики команд
            self.application.add_handler(CommandHandler("start", self.cmd_start))
            self.application.add_handler(CommandHandler("devices", self.cmd_devices))
            self.application.add_handler(CommandHandler("status", self.cmd_status))
            self.application.add_handler(CommandHandler("help", self.cmd_help))

            # Обработчик inline кнопок
            self.application.add_handler(CallbackQueryHandler(self.handle_callback))

            logger.info("🚀 Запуск Multi-Tenant Telegram Bot...")

            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(drop_pending_updates=True)
            await self.application.updater.idle()

        except Exception as e:
            logger.error(f"❌ Ошибка запуска бота: {e}")
            raise
    
    async def stop_bot(self):
        """Остановка бота"""
        try:
            logger.info("🛑 Остановка Multi-Tenant Telegram Bot...")

            if self.application:
                if hasattr(self.application, 'updater') and self.application.updater.running:
                    await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()

            if self.kub_system:
                self.kub_system.stop()

            logger.info("🛑 Multi-Tenant Telegram Bot остановлен")

        except Exception as e:
            logger.error(f"❌ Ошибка остановки: {e}")

# =============================================================================
# АДМИНИСТРАТИВНЫЕ ФУНКЦИИ
# =============================================================================

class MultiTenantAdmin:
    """Административные функции для управления multi-tenant системой"""
    
    def __init__(self):
        self.mt_manager = MultiTenantManager()
    
    def add_user_to_farm(self, telegram_id: int, organization_code: str, role: str = "operator"):
        """Добавить пользователя на ферму"""
        success = self.mt_manager.add_user_to_organization(telegram_id, organization_code, role)
        if success:
            print(f"✅ Пользователь {telegram_id} добавлен в {organization_code} с ролью {role}")
        else:
            print(f"❌ Ошибка добавления пользователя {telegram_id} в {organization_code}")
        return success
    
    def list_users_access(self):
        """Показать всех пользователей и их доступы"""
        # Здесь будет код для показа всех пользователей
        pass

# =============================================================================
# ОСНОВНАЯ ФУНКЦИЯ
# =============================================================================

async def main():
    """Основная функция запуска"""
    try:
        from secure_config import SecureConfig
        config = SecureConfig()
        token = config.get_bot_token()
    except ImportError:
        token = os.getenv('TELEGRAM_BOT_TOKEN')

    if not token:
        print("❌ Не найден TELEGRAM_BOT_TOKEN")
        return

    bot = MultiTenantKUBTelegramBot(token)

    try:
        await bot.start_bot()
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки...")
        await bot.stop_bot()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        await bot.stop_bot()

if __name__ == "__main__":
    print("🏭 MULTI-TENANT TELEGRAM BOT ДЛЯ КУБ-1063")
    print("=" * 60)
    asyncio.run(main())