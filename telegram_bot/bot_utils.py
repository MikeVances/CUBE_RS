#!/usr/bin/env python3
"""
Вспомогательные функции для Telegram Bot
Форматирование данных, утилиты и константы
ВКЛЮЧЕНЫ ВСЕ UX УЛУЧШЕНИЯ!
"""

from datetime import datetime
from typing import Dict, Any
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
    'offline': '📴',
    'home': '🏠',
    'refresh': '🔄'
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
    temp_target = data.get('temp_target')
    humidity = data.get('humidity')
    co2 = data.get('co2')
    pressure = data.get('pressure')
    nh3 = data.get('nh3')
    
    # Время обновления
    timestamp = data.get('updated_at') or data.get('timestamp')
    if timestamp:
        try:
            if isinstance(timestamp, str):
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                dt = timestamp
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
        temp_status = _get_temperature_status(temp_inside, temp_target)
        text += f"• Температура: `{temp_inside:.1f}°C` {temp_status}\n"
    else:
        text += f"• Температура: `нет данных` {EMOJI['error']}\n"
    
    if temp_target is not None:
        text += f"• Целевая T°: `{temp_target:.1f}°C`\n"
    
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
    
    if nh3 is not None:
        nh3_status = _get_nh3_status(nh3)
        text += f"• NH₃: `{nh3:.1f} ppm` {nh3_status}\n"
    
    if pressure is not None:
        text += f"• Давление: `{pressure:.1f} Па`\n"
    
    # Система управления
    text += "\n**⚙️ СИСТЕМА:**\n"
    
    ventilation_level = data.get('ventilation_level')
    ventilation_target = data.get('ventilation_target')
    
    if ventilation_level is not None:
        text += f"• Вентиляция: `{ventilation_level:.1f}%`"
        if ventilation_target is not None:
            text += f" (цель: {ventilation_target:.1f}%)"
        text += "\n"
    
    # Аварии и предупреждения
    active_alarms = data.get('active_alarms', 0)
    active_warnings = data.get('active_warnings', 0)
    
    if active_alarms > 0:
        text += f"\n🚨 **АВАРИИ: {active_alarms}**\n"
    
    if active_warnings > 0:
        text += f"⚠️ **ПРЕДУПРЕЖДЕНИЯ: {active_warnings}**\n"
    
    if active_alarms == 0 and active_warnings == 0:
        text += f"\n{EMOJI['ok']} **Система в норме**\n"
    
    return text

def _get_temperature_status(temp_inside: float, temp_target: float = None) -> str:
    """Статус температуры"""
    if temp_target:
        diff = abs(temp_inside - temp_target)
        if diff <= 1.0:
            return EMOJI['ok']
        elif diff <= 3.0:
            return EMOJI['warning']
        else:
            return EMOJI['error']
    else:
        # Общие диапазоны для птицеводства
        if 18 <= temp_inside <= 25:
            return EMOJI['ok']
        elif 15 <= temp_inside <= 30:
            return EMOJI['warning']
        else:
            return EMOJI['error']

def _get_humidity_status(humidity: float) -> str:
    """Статус влажности"""
    if 50 <= humidity <= 70:
        return EMOJI['ok']
    elif 40 <= humidity <= 80:
        return EMOJI['warning']
    else:
        return EMOJI['error']

def _get_co2_status(co2: int) -> str:
    """Статус CO2"""
    if co2 <= 3000:
        return EMOJI['ok']
    elif co2 <= 5000:
        return EMOJI['warning']
    else:
        return EMOJI['error']

def _get_nh3_status(nh3: float) -> str:
    """Статус NH3 (аммиак)"""
    if nh3 <= 10:
        return EMOJI['ok']
    elif nh3 <= 25:
        return EMOJI['warning']
    else:
        return EMOJI['error']

# ========================================================================
# UX УЛУЧШЕНИЯ: МЕНЮ И КНОПКИ
# ========================================================================

def build_main_menu(access_level: str = "user") -> InlineKeyboardMarkup:
    """
    🎯 ОСНОВНОЕ МЕНЮ с кнопками по уровню доступа
    Возвращает главное меню с inline-кнопками
    """
    buttons = [
        [InlineKeyboardButton("📊 Показания", callback_data="show_status")],
        [InlineKeyboardButton(f"{EMOJI['refresh']} Обновить", callback_data="refresh_status")],
    ]
    
    # Добавляем кнопки по уровню доступа
    if access_level in ("operator", "admin", "engineer"):
        buttons.append([InlineKeyboardButton("🚨 Сброс аварий", callback_data="reset_alarms")])
    
    if access_level in ("admin", "engineer"):
        buttons.append([InlineKeyboardButton("⚙️ Настройки", callback_data="settings")])
    
    # Общие кнопки
    buttons.append([InlineKeyboardButton("📈 Статистика", callback_data="show_stats")])
    buttons.append([InlineKeyboardButton("ℹ️ Помощь", callback_data="show_help")])
    
    return InlineKeyboardMarkup(buttons)

def build_confirmation_menu(confirm_action: str, cancel_action: str = "main_menu") -> InlineKeyboardMarkup:
    """
    🎯 МЕНЮ ПОДТВЕРЖДЕНИЯ для критических действий
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить", callback_data=confirm_action)],
        [InlineKeyboardButton("❌ Отмена", callback_data=cancel_action)],
        [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
    ])

def build_back_menu(access_level: str = "user") -> InlineKeyboardMarkup:
    """
    🎯 МЕНЮ С КНОПКОЙ НАЗАД для любых экранов
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{EMOJI['refresh']} Обновить", callback_data="refresh_status")],
        [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
    ])

def build_stats_menu(access_level: str = "user") -> InlineKeyboardMarkup:
    """
    🎯 МЕНЮ ДЛЯ СТАТИСТИКИ с кнопкой обновления
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{EMOJI['refresh']} Обновить статистику", callback_data="refresh_stats")],
        [InlineKeyboardButton("📊 Показания", callback_data="show_status")],
        [InlineKeyboardButton(f"{EMOJI['home']} Главное меню", callback_data="main_menu")]
    ])

def format_system_stats(stats: Dict[str, Any]) -> str:
    """Форматирование статистики системы"""
    
    if not stats:
        return f"{EMOJI['error']} **Статистика недоступна**"
    
    text = f"📈 **СТАТИСТИКА СИСТЕМЫ**\n\n"
    
    # Статистика чтения данных
    success_count = stats.get('success_count', 0)
    error_count = stats.get('error_count', 0)
    success_rate = stats.get('success_rate', 0)
    
    text += f"**📊 ОБМЕН ДАННЫМИ:**\n"
    text += f"• Успешных чтений: `{success_count}`\n"
    text += f"• Ошибок: `{error_count}`\n"
    text += f"• Успешность: `{success_rate:.1f}%`\n\n"
    
    # Время последнего обновления
    last_success = stats.get('last_success')
    if last_success:
        try:
            dt = datetime.fromisoformat(last_success.replace('Z', '+00:00'))
            time_str = dt.strftime('%H:%M:%S %d.%m.%Y')
            text += f"• Последнее чтение: `{time_str}`\n"
        except:
            text += f"• Последнее чтение: `{last_success}`\n"
    
    # Статус подключения
    is_running = stats.get('is_running', False)
    status = "🟢 Работает" if is_running else "🔴 Остановлен"
    text += f"• Статус системы: `{status}`\n"
    
    return text

# ========================================================================
# UX УЛУЧШЕНИЯ: ЭМУЛЯЦИЯ ПЕЧАТАНИЯ И ДЕЙСТВИЯ
# ========================================================================

async def send_typing_action(update, context):
    """
    🎯 UX: Отправляет 'печатает...' пока идет обработка
    Работает и для сообщений, и для callback'ов
    """
    try:
        chat_id = None
        
        # Определяем chat_id из разных типов update
        if hasattr(update, 'message') and update.message:
            chat_id = update.message.chat_id
        elif hasattr(update, 'callback_query') and update.callback_query:
            chat_id = update.callback_query.message.chat_id
        elif hasattr(update, 'effective_chat'):
            chat_id = update.effective_chat.id
        
        if chat_id:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            
    except Exception as e:
        # Игнорируем ошибки typing action - это не критично
        pass

async def send_upload_action(update, context):
    """
    🎯 UX: Отправляет 'загружает файл...' для длительных операций
    """
    try:
        chat_id = None
        
        if hasattr(update, 'message') and update.message:
            chat_id = update.message.chat_id
        elif hasattr(update, 'callback_query') and update.callback_query:
            chat_id = update.callback_query.message.chat_id
        
        if chat_id:
            await context.bot.send_chat_action(chat_id=chat_id, action="upload_document")
            
    except Exception:
        pass

# ========================================================================
# UX УЛУЧШЕНИЯ: ФОРМАТИРОВАНИЕ СООБЩЕНИЙ
# ========================================================================

def error_message(text: str) -> str:
    """🎯 UX: Форматирование сообщения об ошибке"""
    return f"❌ **Ошибка**\n\n{text}"

def success_message(text: str) -> str:
    """🎯 UX: Форматирование сообщения об успехе"""
    return f"✅ **Успех**\n\n{text}"

def info_message(text: str) -> str:
    """🎯 UX: Форматирование информационного сообщения"""
    return f"ℹ️ **Информация**\n\n{text}"

def warning_message(text: str) -> str:
    """🎯 UX: Форматирование предупреждения"""
    return f"⚠️ **Внимание**\n\n{text}"

def loading_message(text: str) -> str:
    """🎯 UX: Сообщение о загрузке"""
    return f"⏳ **Обработка...**\n\n{text}"

# ========================================================================
# UX УЛУЧШЕНИЯ: ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ========================================================================

def truncate_text(text: str, max_length: int = 4000) -> str:
    """Обрезка текста для Telegram (лимит 4096 символов)"""
    if len(text) <= max_length:
        return text
    
    return text[:max_length-3] + "..."

def format_uptime(seconds: int) -> str:
    """Форматирование времени работы"""
    if seconds < 60:
        return f"{seconds}с"
    elif seconds < 3600:
        return f"{seconds//60}м {seconds%60}с"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}ч {minutes}м"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}д {hours}ч"

# =============================================================================
# ТЕСТИРОВАНИЕ МОДУЛЯ
# =============================================================================

def test_bot_utils():
    """Тест функций утилит"""
    print("🧪 Тестирование bot_utils (с UX улучшениями)")
    print("=" * 50)
    
    # Тестовые данные
    test_data = {
        'temp_inside': 23.5,
        'temp_target': 24.0,
        'humidity': 65.0,
        'co2': 2500,
        'nh3': 8.5,
        'pressure': 101.3,
        'ventilation_level': 45.5,
        'ventilation_target': 50.0,
        'active_alarms': 0,
        'active_warnings': 1,
        'connection_status': 'connected',
        'timestamp': datetime.now().isoformat()
    }
    
    # Тест форматирования данных
    print("1. Тест форматирования данных датчиков...")
    formatted = format_sensor_data(test_data)
    print("   ✅ Данные отформатированы")
    
    # Тест создания основного меню
    print("2. Тест создания основного меню...")
    menu = build_main_menu("admin")
    print(f"   ✅ Основное меню: {len(menu.inline_keyboard)} рядов кнопок")
    
    # Тест меню подтверждения
    print("3. Тест меню подтверждения...")
    confirm_menu = build_confirmation_menu("test_confirm", "test_cancel")
    print(f"   ✅ Меню подтверждения: {len(confirm_menu.inline_keyboard)} рядов кнопок")
    
    # Тест меню статистики
    print("4. Тест меню статистики...")
    stats_menu = build_stats_menu("operator")
    print(f"   ✅ Меню статистики: {len(stats_menu.inline_keyboard)} рядов кнопок")
    
    # Тест сообщений
    print("5. Тест форматирования сообщений...")
    error_msg = error_message("Тест ошибки")
    success_msg = success_message("Тест успеха")
    info_msg = info_message("Тест информации")
    
    print(f"   ✅ Сообщения: error={len(error_msg)}, success={len(success_msg)}, info={len(info_msg)} символов")
    
    # Тест статистики
    print("6. Тест форматирования статистики...")
    test_stats = {
        'success_count': 150,
        'error_count': 5,
        'success_rate': 96.8,
        'is_running': True,
        'last_success': datetime.now().isoformat()
    }
    stats_formatted = format_system_stats(test_stats)
    print("   ✅ Статистика отформатирована")
    
    print("\n✅ Все тесты утилит с UX улучшениями пройдены!")
    print("🎯 Включено:")
    print("   • Эмуляция печатания")
    print("   • Кнопки главного меню")
    print("   • Меню подтверждений")
    print("   • Улучшенное форматирование")

if __name__ == "__main__":
    test_bot_utils()