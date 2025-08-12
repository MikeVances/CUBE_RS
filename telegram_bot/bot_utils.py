#!/usr/bin/env python3
"""
Вспомогательные функции для Telegram Bot
Форматирование данных, утилиты и константы
"""

from datetime import datetime
from typing import Dict, Any

# --- ДОБАВЛЕНО: Импорт для меню ---
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

# Эмодзи для различных состояний
EMOJI = {
    'temperature': '🌡️',
    'humidity': '💧',
    'co2': '🫁',
    'pressure': '🌀',
    'alarm': '🚨',
    'warning': '⚠️',
    'ok': '✅',
    'error': '❌',
    'info': 'ℹ️',
    'clock': '🕐',
    'statistics': '📊',
    'system': '⚙️',
    'connection': '🔗',
    'offline': '📴'
}

def format_sensor_data(data: Dict[str, Any]) -> str:
    """Форматирование данных с датчиков для отображения"""
    
    if not data:
        return f"{EMOJI['error']} **Нет данных от системы**"
    
    # Проверяем статус подключения
    connection_status = data.get('connection_status', 'unknown')
    if connection_status != 'connected':
        return f"{EMOJI['offline']} **Система КУБ-1063 недоступна**\n\nСтатус: `{connection_status}`"
    
    # Основные показания
    temp_inside = data.get('temp_inside')
    humidity = data.get('humidity')
    co2 = data.get('co2')
    pressure = data.get('pressure')
    
    # Время обновления
    timestamp = data.get('timestamp')
    if timestamp:
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            time_str = dt.strftime('%H:%M:%S')
            date_str = dt.strftime('%d.%m.%Y')
        except:
            time_str = "неизвестно"
            date_str = "неизвестно"
    else:
        time_str = "неизвестно"
        date_str = "неизвестно"
    
    # Формируем сообщение
    text = f"📊 **ПОКАЗАНИЯ КУБ-1063**\n"
    text += f"{EMOJI['clock']} Обновлено: `{time_str}` ({date_str})\n\n"
    
    # Основные параметры
    text += "**🌡️ КЛИМАТ:**\n"
    
    if temp_inside is not None:
        temp_status = _get_temperature_status(temp_inside)
        text += f"• Температура: `{temp_inside:.1f}°C` {temp_status}\n"
    else:
        text += f"• Температура: `нет данных` {EMOJI['error']}\n"
    
    if humidity is not None:
        humidity_status = _get_humidity_status(humidity)
        text += f"• Влажность: `{humidity:.1f}%` {humidity_status}\n"
    else:
        text += f"• Влажность: `нет данных` {EMOJI['error']}\n"
    
    # Качество воздуха
    text += "\n**🫁 КАЧЕСТВО ВОЗДУХА:**\n"
    
    if co2 is not None:
        co2_status = _get_co2_status(co2)
        text += f"• CO₂: `{co2} ppm` {co2_status}\n"
    else:
        text += f"• CO₂: `нет данных` {EMOJI['error']}\n"
    
    if pressure is not None:
        text += f"• Давление: `{pressure:.1f} Па`\n"
    
    return text


def build_main_menu(access_level: str = "user") -> InlineKeyboardMarkup:
    """Возвращает главное меню с inline-кнопками по уровню доступа"""
    buttons = [
        [InlineKeyboardButton("📊 Показания", callback_data="show_stats")],
        [InlineKeyboardButton("📈 Статистика", callback_data="show_history")],
    ]
    if access_level in ("operator", "admin"):
        buttons.append([InlineKeyboardButton("🔄 Сброс аварий", callback_data="reset_alarms")])
    if access_level == "admin":
        buttons.append([InlineKeyboardButton("⚙️ Настройки", callback_data="settings")])
    buttons.append([InlineKeyboardButton("ℹ️ Помощь", callback_data="show_help")])
    return InlineKeyboardMarkup(buttons)    

def format_system_stats(stats: Dict[str, Any]) -> str:
    """Форматирование статистики системы"""
    
    if not stats:
        return f"{EMOJI['error']} **Статистика недоступна**"
    
    system_stats = stats.get('system', {})
    reader_stats = stats.get('reader', {})
    writer_stats = stats.get('writer', {})
    
    text = f"📈 **СТАТИСТИКА СИСТЕМЫ КУБ-1063**\n\n"
    
    # Время работы системы
    uptime_seconds = system_stats.get('uptime_seconds', 0)
    uptime_str = _format_uptime(uptime_seconds)
    text += f"**⚙️ СИСТЕМА:**\n"
    text += f"• Время работы: `{uptime_str}`\n"
    
    # Статистика чтения
    text += f"\n**📖 ЧТЕНИЕ ДАННЫХ:**\n"
    text += f"• Активен: {'✅' if reader_stats.get('enabled') else '❌'}\n"
    text += f"• Циклов чтения: `{reader_stats.get('total_cycles', 0)}`\n"
    
    last_read = reader_stats.get('last_read')
    if last_read:
        try:
            dt = datetime.fromisoformat(str(last_read))
            last_read_str = dt.strftime('%H:%M:%S')
        except:
            last_read_str = "неизвестно"
    else:
        last_read_str = "никогда"
    
    text += f"• Последнее чтение: `{last_read_str}`\n"
    
    # Статистика записи
    text += f"\n**✍️ ЗАПИСЬ КОМАНД:**\n"
    text += f"• Активен: {'✅' if writer_stats.get('enabled') else '❌'}\n"
    text += f"• Всего команд: `{writer_stats.get('commands_total', 0)}`\n"
    text += f"• Успешных: `{writer_stats.get('commands_success', 0)}`\n"
    text += f"• Неудачных: `{writer_stats.get('commands_failed', 0)}`\n"
    text += f"• В очереди: `{writer_stats.get('commands_pending', 0)}`\n"
    
    return text

# --- UX ДОПОЛНЕНИЯ ---

async def send_typing_action(update, context):
    """Отправляет в чат анимацию 'печатает...' для UX"""
    if hasattr(update, "message") and update.message:
        await context.bot.send_chat_action(chat_id=update.message.chat_id, action="typing")
    elif hasattr(update, "callback_query") and update.callback_query:
        await context.bot.send_chat_action(chat_id=update.callback_query.message.chat_id, action="typing")

def error_message(text: str) -> str:
    """Форматированное сообщение об ошибке для пользователя"""
    return f"{EMOJI['error']} <b>Ошибка</b>:\n{text}"

# --- /UX ДОПОЛНЕНИЯ ---


def _get_temperature_status(temp: float) -> str:
    """Статус температуры по значению"""
    if temp < 15:
        return f"{EMOJI['info']} холодно"
    elif temp < 20:
        return f"{EMOJI['ok']} прохладно" 
    elif temp < 25:
        return f"{EMOJI['ok']} комфортно"
    elif temp < 30:
        return f"{EMOJI['warning']} тепло"
    else:
        return f"{EMOJI['alarm']} жарко"

def _get_humidity_status(humidity: float) -> str:
    """Статус влажности по значению"""
    if humidity < 30:
        return f"{EMOJI['warning']} сухо"
    elif humidity < 60:
        return f"{EMOJI['ok']} нормально"
    elif humidity < 80:
        return f"{EMOJI['warning']} влажно"
    else:
        return f"{EMOJI['alarm']} очень влажно"

def _get_co2_status(co2: int) -> str:
    """Статус CO2 по значению"""
    if co2 < 600:
        return f"{EMOJI['ok']} отлично"
    elif co2 < 1000:
        return f"{EMOJI['ok']} хорошо"
    elif co2 < 1500:
        return f"{EMOJI['warning']} удовлетворительно"
    else:
        return f"{EMOJI['alarm']} плохо"

def _format_uptime(seconds: int) -> str:
    """Форматирование времени работы системы"""
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} мин"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}ч {minutes}м"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}д {hours}ч"