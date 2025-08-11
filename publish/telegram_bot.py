#!/usr/bin/env python3
"""
Telegram Bot для КУБ-1063
Улучшенная версия с интеграцией dashboard_reader и дополнительными функциями
"""

import asyncio
import logging
import time
import sys
import os
import psutil
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# Добавляем путь к корневой директории
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import config
# Импорт ваших модулей
try:
    from modbus.dashboard_reader import get_dashboard_reader, get_statistics
    DASHBOARD_AVAILABLE = True
except ImportError:
    try:
        from modbus.reader import read_all
        DASHBOARD_AVAILABLE = False
        print("⚠️ dashboard_reader недоступен, используем прямое чтение")
    except ImportError:
        print("❌ Не найдены модули для чтения данных")
        sys.exit(1)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("telegram_bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация (замените на ваш токен)
TELEGRAM_BOT_TOKEN = config.TELEGRAM_BOT_TOKEN  # Замените на ваш токен

class TelegramBot:
    """Класс для работы с Telegram ботом"""
    
    def __init__(self):
        self.application = None
        self.is_running = False
        self.dashboard_reader = None
        self.alert_subscribers = set()  # Пользователи, подписанные на алерты
        self.last_alert_time = {}  # Время последнего алерта для каждого типа
        
        # Инициализируем reader
        if DASHBOARD_AVAILABLE:
            self.dashboard_reader = get_dashboard_reader()
    
    def format_value(self, value: Any, unit: str = "", default: str = "NON") -> str:
        """Форматирование значения с единицами измерения"""
        if value is None:
            return default
        if isinstance(value, (int, float)):
            if unit:
                return f"{value}{unit}"
            return str(value)
        return str(value)
    
    def get_data(self) -> Dict[str, Any]:
        """Получение данных с универсальной поддержкой модулей"""
        try:
            if DASHBOARD_AVAILABLE and self.dashboard_reader:
                data = self.dashboard_reader.read_all()
                if data and data.get('connection_status') == 'connected':
                    return data
            else:
                # Прямое чтение
                return read_all()
        except Exception as e:
            logger.error(f"Ошибка получения данных: {e}")
        
        return {}
    
    def check_alerts(self, data: Dict[str, Any]) -> list:
        """Проверка критических состояний"""
        alerts = []
        
        if not data or data.get('connection_status') != 'connected':
            return alerts
        
        # Проверяем температуру
        temp = data.get('temp_inside')
        if temp is not None:
            if temp > 35:
                alerts.append(f"🔥 Высокая температура: {temp}°C")
            elif temp < 15:
                alerts.append(f"🧊 Низкая температура: {temp}°C")
        
        # Проверяем влажность
        humidity = data.get('humidity')
        if humidity is not None:
            if humidity > 90:
                alerts.append(f"💧 Высокая влажность: {humidity}%")
            elif humidity < 30:
                alerts.append(f"🏜️ Низкая влажность: {humidity}%")
        
        # Проверяем CO2
        co2 = data.get('co2')
        if co2 is not None:
            if co2 > 1500:
                alerts.append(f"🫁 Высокий CO₂: {co2} ppm")
        
        # Проверяем NH3
        nh3 = data.get('nh3')
        if nh3 is not None:
            if nh3 > 25:
                alerts.append(f"☣️ Высокий NH₃: {nh3} ppm")
        
        return alerts
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        keyboard = [
            [InlineKeyboardButton("📊 Данные", callback_data='status')],
            [InlineKeyboardButton("📈 Статистика", callback_data='stats')],
            [InlineKeyboardButton("🔔 Алерты", callback_data='alerts')],
            [InlineKeyboardButton("ℹ️ Справка", callback_data='help')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🤖 *Привет! Я бот для мониторинга КУБ-1063*\n\n"
            "Выберите действие:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /status"""
        await self.send_status_with_buttons(update.message.reply_text)
    
    async def send_status(self, reply_func):
        """Отправка статуса (универсальная функция)"""
        try:
            # Получаем данные
            data = self.get_data()

            # Добавляем блок расчёта времени обновления
            ts = data.get('updated_at')
            message_time_info = ""
            if ts:
                try:
                    if isinstance(ts, str):
                        ts = datetime.fromisoformat(ts)
                    minutes_ago = int((datetime.now() - ts).total_seconds() // 60)
                    message_time_info = f"\n🕒 *Последние данные обновлены* {minutes_ago} мин назад"
                except Exception as e:
                    logger.warning(f"Ошибка при расчёте времени обновления: {e}")

            if not data:
                await reply_func("❌ *Нет данных с контроллера*", parse_mode='Markdown')
                return

            # Проверяем статус подключения
            connection_status = data.get('connection_status', 'unknown')

            if connection_status != 'connected':
                status_messages = {
                    'waiting': '⏳ *Ожидание данных...*',
                    'disconnected': '🔌 *Нет подключения к устройству*',
                    'error': f"❌ *Ошибка: {data.get('error', 'Неизвестная ошибка')}*"
                }
                message = status_messages.get(connection_status, '❓ *Неизвестный статус*')
                await reply_func(message, parse_mode='Markdown')
                return

            # Формируем сообщение с данными
            timestamp = data.get('timestamp', datetime.now())
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

            message = f"📊 *Данные КУБ-1063*\n"
            message += f"🕒 _{timestamp.strftime('%d.%m.%Y %H:%M:%S')}_\n\n"

            # Основные параметры
            temp_inside = self.format_value(data.get('temp_inside'), '°C')
            temp_target = self.format_value(data.get('temp_target'), '°C')
            humidity = self.format_value(data.get('humidity'), '%')
            co2 = self.format_value(data.get('co2'), ' ppm')

            message += f"🌡️ *Температура:* {temp_inside}"
            if temp_target != "NON":
                message += f" (цель: {temp_target})"
            message += "\n"

            message += f"💧 *Влажность:* {humidity}\n"
            message += f"🫁 *CO₂:* {co2}\n"

            # Вентиляция
            vent_level = self.format_value(data.get('ventilation_level'), '%')
            vent_target = self.format_value(data.get('ventilation_target'), '%')
            vent_scheme = self.format_value(data.get('ventilation_scheme'))

            message += f"🌀 *Вентиляция:* {vent_level}"
            if vent_target != "NON":
                message += f" (цель: {vent_target})"
            message += "\n"

            if vent_scheme != "NON":
                message += f"⚙️ *Схема:* {vent_scheme}\n"

            # Дополнительные параметры
            pressure = data.get('pressure')
            nh3 = data.get('nh3')

            if pressure is not None:
                message += f"📊 *Давление:* {self.format_value(pressure, ' Па')}\n"
            if nh3 is not None:
                message += f"☣️ *NH₃:* {self.format_value(nh3, ' ppm')}\n"

            # Информация о системе
            software_version = data.get('software_version')
            day_counter = data.get('day_counter')

            if software_version or day_counter:
                message += "\n📋 *Система:*\n"
                if software_version:
                    message += f"• ПО: {software_version}\n"
                if day_counter:
                    message += f"• День: {day_counter}\n"

            # Качество данных
            success_rate = data.get('success_rate')
            if success_rate is not None:
                quality = "отличное" if success_rate > 0.9 else "хорошее" if success_rate > 0.7 else "плохое"
                message += f"\n📈 *Качество данных:* {success_rate*100:.1f}% ({quality})"

            # Проверяем алерты
            alerts = self.check_alerts(data)
            if alerts:
                message += "\n\n🚨 *ВНИМАНИЕ:*\n"
                for alert in alerts:
                    message += f"• {alert}\n"

            # Добавляем информацию о времени обновления, если есть
            if message_time_info:
                message += message_time_info

            await reply_func(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Ошибка при получении данных: {e}")
            await reply_func("❌ *Ошибка при получении данных*", parse_mode='Markdown')
    
    async def send_status_with_buttons(self, reply_func):
        """Отправка статуса с кнопками"""
        try:
            # Получаем данные
            data = self.get_data()

            # Добавляем блок расчёта времени обновления
            ts = data.get('updated_at')
            message_time_info = ""
            if ts:
                try:
                    if isinstance(ts, str):
                        ts = datetime.fromisoformat(ts)
                    minutes_ago = int((datetime.now() - ts).total_seconds() // 60)
                    message_time_info = f"\n🕒 *Последние данные обновлены* {minutes_ago} мин назад"
                except Exception as e:
                    logger.warning(f"Ошибка при расчёте времени обновления: {e}")

            if not data:
                keyboard = [
                    [InlineKeyboardButton("📊 Данные", callback_data='status')],
                    [InlineKeyboardButton("📈 Статистика", callback_data='stats')],
                    [InlineKeyboardButton("🔔 Алерты", callback_data='alerts')],
                    [InlineKeyboardButton("ℹ️ Справка", callback_data='help')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await reply_func("❌ *Нет данных с контроллера*", parse_mode='Markdown', reply_markup=reply_markup)
                return

            # Проверяем статус подключения
            connection_status = data.get('connection_status', 'unknown')

            if connection_status != 'connected':
                status_messages = {
                    'waiting': '⏳ *Ожидание данных...*',
                    'disconnected': '🔌 *Нет подключения к устройству*',
                    'error': f"❌ *Ошибка: {data.get('error', 'Неизвестная ошибка')}*"
                }
                message = status_messages.get(connection_status, '❓ *Неизвестный статус*')
                
                keyboard = [
                    [InlineKeyboardButton("📊 Данные", callback_data='status')],
                    [InlineKeyboardButton("📈 Статистика", callback_data='stats')],
                    [InlineKeyboardButton("🔔 Алерты", callback_data='alerts')],
                    [InlineKeyboardButton("ℹ️ Справка", callback_data='help')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await reply_func(message, parse_mode='Markdown', reply_markup=reply_markup)
                return

            # Формируем сообщение с данными
            timestamp = data.get('timestamp', datetime.now())
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

            message = f"📊 *Данные КУБ-1063*\n"
            message += f"🕒 _{timestamp.strftime('%d.%m.%Y %H:%M:%S')}_\n\n"

            # Основные параметры
            temp_inside = self.format_value(data.get('temp_inside'), '°C')
            temp_target = self.format_value(data.get('temp_target'), '°C')
            humidity = self.format_value(data.get('humidity'), '%')
            co2 = self.format_value(data.get('co2'), ' ppm')

            message += f"🌡️ *Температура:* {temp_inside}"
            if temp_target != "NON":
                message += f" (цель: {temp_target})"
            message += "\n"

            message += f"💧 *Влажность:* {humidity}\n"
            message += f"🫁 *CO₂:* {co2}\n"

            # Вентиляция
            vent_level = self.format_value(data.get('ventilation_level'), '%')
            vent_target = self.format_value(data.get('ventilation_target'), '%')
            vent_scheme = self.format_value(data.get('ventilation_scheme'))

            message += f"🌀 *Вентиляция:* {vent_level}"
            if vent_target != "NON":
                message += f" (цель: {vent_target})"
            message += "\n"

            if vent_scheme != "NON":
                message += f"⚙️ *Схема:* {vent_scheme}\n"

            # Дополнительные параметры
            pressure = data.get('pressure')
            nh3 = data.get('nh3')

            if pressure is not None:
                message += f"📊 *Давление:* {self.format_value(pressure, ' Па')}\n"
            if nh3 is not None:
                message += f"☣️ *NH₃:* {self.format_value(nh3, ' ppm')}\n"

            # Проверяем алерты
            alerts = self.check_alerts(data)
            if alerts:
                message += "\n\n🚨 *ВНИМАНИЕ:*\n"
                for alert in alerts:
                    message += f"• {alert}\n"

            # Добавляем информацию о времени обновления
            message += message_time_info

            # Добавляем кнопки
            keyboard = [
                [InlineKeyboardButton("📊 Данные", callback_data='status')],
                [InlineKeyboardButton("📈 Статистика", callback_data='stats')],
                [InlineKeyboardButton("🔔 Алерты", callback_data='alerts')],
                [InlineKeyboardButton("ℹ️ Справка", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await reply_func(message, parse_mode='Markdown', reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Ошибка при получении данных: {e}")
            keyboard = [
                [InlineKeyboardButton("📊 Данные", callback_data='status')],
                [InlineKeyboardButton("📈 Статистика", callback_data='stats')],
                [InlineKeyboardButton("🔔 Алерты", callback_data='alerts')],
                [InlineKeyboardButton("ℹ️ Справка", callback_data='help')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await reply_func("❌ *Ошибка при получении данных*", parse_mode='Markdown', reply_markup=reply_markup)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stats"""
        try:
            if DASHBOARD_AVAILABLE:
                stats = get_statistics()
                if stats:
                    message = "📈 *Статистика работы:*\n\n"
                    message += f"✅ *Успешных чтений:* {stats.get('success_count', 0)}\n"
                    message += f"❌ *Ошибок:* {stats.get('error_count', 0)}\n"
                    message += f"📊 *Всего попыток:* {stats.get('success_count', 0) + stats.get('error_count', 0)}\n"
                    
                    success_rate = stats.get('success_rate', 0) * 100
                    message += f"📈 *Успешность:* {success_rate:.1f}%\n"
                    
                    if stats.get('is_running'):
                        message += f"🟢 *Статус:* Активен"
                    else:
                        message += f"🔴 *Статус:* Неактивен"
                    
                    if update.message:
                        await update.message.reply_text(message, parse_mode='Markdown')
                    elif update.callback_query:
                        await update.callback_query.message.reply_text(message, parse_mode='Markdown')
                else:
                    if update.message:
                        await update.message.reply_text("❌ *Статистика недоступна*", parse_mode='Markdown')
                    elif update.callback_query:
                        await update.callback_query.message.reply_text("❌ *Статистика недоступна*", parse_mode='Markdown')
            else:
                if update.message:
                    await update.message.reply_text("📊 *Статистика доступна только в dashboard режиме*", parse_mode='Markdown')
                elif update.callback_query:
                    await update.callback_query.message.reply_text("📊 *Статистика доступна только в dashboard режиме*", parse_mode='Markdown')
                
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            if update.message:
                await update.message.reply_text("❌ *Ошибка получения статистики*", parse_mode='Markdown')
            elif update.callback_query:
                await update.callback_query.message.reply_text("❌ *Ошибка получения статистики*", parse_mode='Markdown')
    
    async def alerts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /alerts"""
        user_id = update.effective_user.id
        
        keyboard = []
        if user_id in self.alert_subscribers:
            keyboard.append([InlineKeyboardButton("🔕 Отписаться", callback_data='unsubscribe_alerts')])
            message = "🔔 *Вы подписаны на алерты*\n\nВы будете получать уведомления при критических состояниях."
        else:
            keyboard.append([InlineKeyboardButton("🔔 Подписаться", callback_data='subscribe_alerts')])
            message = "🔕 *Вы не подписаны на алерты*\n\nПодпишитесь, чтобы получать уведомления при критических состояниях."
        
        keyboard.append([InlineKeyboardButton("📊 Проверить сейчас", callback_data='check_alerts')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = (
            "🤖 *КУБ-1063 Telegram Bot*\n\n"
            "*Команды:*\n"
            "/start - главное меню\n"
            "/status - текущие данные\n"
            "/help - эта справка\n\n"
            "*Доступные транспорты и сервисы:*\n"
            "• 🌐 Dashboard: http://<ip>:8501\n"
            "• 🧲 Modbus TCP: <ip>:5021 (для SCADA/ModScan)\n"
            "• 🔌 WebSocket: ws://<ip>:8765 (реальное время)\n"
            "• 📡 MQTT: <broker>:<port>\n\n"
            "*Инструкции:*\n"
            "- ModScan: Function 03, Address 0, Quantity 3\n"
            "- WebSocket: ws://<ip>:8765, команда {cmd: 'get'}\n"
            "*Функции:*\n"
            "• 📊 Мониторинг температуры, влажности, CO₂\n"
            "• 🔔 Алерты при критических состояниях\n"
            "• 📈 Статистика качества связи\n"
            "• 🌀 Контроль вентиляции\n\n"
            "_Вопросы и поддержка: Support_"
        )
        if update.message:
            await update.message.reply_text(help_text, parse_mode='Markdown')
        elif update.callback_query:
            await update.callback_query.message.reply_text(help_text, parse_mode='Markdown')
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий кнопок"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        
        if query.data == 'status':
            await self.send_status_with_buttons(query.message.reply_text)
        
        elif query.data == 'stats':
            await self.stats_command(update, context)
        
        elif query.data == 'alerts':
            await self.alerts_command(update, context)
        
        elif query.data == 'help':
            await self.help_command(update, context)
        
        elif query.data == 'subscribe_alerts':
            self.alert_subscribers.add(user_id)
            await query.message.reply_text("🔔 *Вы подписались на алерты!*", parse_mode='Markdown')
        
        elif query.data == 'unsubscribe_alerts':
            self.alert_subscribers.discard(user_id)
            await query.message.reply_text("🔕 *Вы отписались от алертов*", parse_mode='Markdown')
        
        elif query.data == 'check_alerts':
            data = self.get_data()
            alerts = self.check_alerts(data)
            
            if alerts:
                message = "🚨 *Обнаружены проблемы:*\n\n"
                for alert in alerts:
                    message += f"• {alert}\n"
            else:
                message = "✅ *Все параметры в норме*"
            
            await query.message.reply_text(message, parse_mode='Markdown')
    
    async def send_alert_to_subscribers(self, alert_message: str):
        """Отправка алерта всем подписчикам"""
        if not self.alert_subscribers:
            return
        
        for user_id in self.alert_subscribers.copy():
            try:
                await self.application.bot.send_message(
                    chat_id=user_id,
                    text=f"🚨 *АЛЕРТ КУБ-1063*\n\n{alert_message}",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Ошибка отправки алерта пользователю {user_id}: {e}")
                # Удаляем пользователя если бот заблокирован
                if "bot was blocked by the user" in str(e):
                    self.alert_subscribers.discard(user_id)
    
    async def periodic_alerts_check(self):
        """Периодическая проверка критических состояний"""
        while self.is_running:
            try:
                if self.alert_subscribers:
                    data = self.get_data()
                    alerts = self.check_alerts(data)
                    
                    for alert in alerts:
                        # Проверяем, не отправляли ли этот алерт недавно
                        alert_key = alert[:20]  # Первые 20 символов как ключ
                        last_time = self.last_alert_time.get(alert_key, datetime.min)
                        
                        if datetime.now() - last_time > timedelta(minutes=30):  # Не чаще раза в 30 минут
                            await self.send_alert_to_subscribers(alert)
                            self.last_alert_time[alert_key] = datetime.now()
                
                await asyncio.sleep(60)  # Проверяем каждую минуту
                
            except Exception as e:
                logger.error(f"Ошибка в periodic_alerts_check: {e}")
                await asyncio.sleep(60)
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик ошибок"""
        logger.error(f"Exception while handling an update: {context.error}")
        
        # Обработка конфликта ботов
        if "Conflict: terminated by other getUpdates request" in str(context.error):
            logger.warning("Обнаружен конфликт ботов, останавливаю текущий...")
            self.is_running = False
            if self.application:
                try:
                    await self.application.stop()
                except Exception as e:
                    logger.error(f"Ошибка при остановке приложения: {e}")
    
    def check_other_bot_instances(self):
        """Проверяет, не запущены ли другие экземпляры бота"""
        current_pid = os.getpid()
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.pid == current_pid:
                    continue
                    
                cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                
                # Ищем только активные процессы с telegram_bot
                if 'telegram_bot' in cmdline and proc.status() == psutil.STATUS_RUNNING:
                    logger.warning(f"Найден другой процесс бота: PID {proc.pid}")
                    return True
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return False
    
    def start_bot(self):
        """Запуск бота"""
        try:
            # Создаем приложение
            self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
            
            # Добавляем обработчики команд
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("stats", self.stats_command))
            self.application.add_handler(CommandHandler("alerts", self.alerts_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            
            # Добавляем обработчик кнопок
            self.application.add_handler(CallbackQueryHandler(self.button_handler))
            
            logger.info("🤖 Telegram бот запущен")
            self.is_running = True
            
        except Exception as e:
            logger.error(f"Ошибка запуска бота: {e}")
            self.is_running = False

def run_bot():
    """Функция для запуска бота в отдельном процессе"""
    logger.info("Запуск Telegram бота...")
    
    # Проверяем токен
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("❌ Не указан токен бота! Установите TELEGRAM_BOT_TOKEN")
        return
    
    try:
        # Создаем и запускаем бота
        bot = TelegramBot()
        bot.start_bot()  # Сначала инициализируем
        bot.application.run_polling(allowed_updates=Update.ALL_TYPES)  # Затем запускаем
        
    except Exception as e:
        logger.error(f"Ошибка запуска Telegram бота: {e}")

if __name__ == "__main__":
    run_bot()