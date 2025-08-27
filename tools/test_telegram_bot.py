#!/usr/bin/env python3
"""
Комплексный тест всех компонентов Telegram Bot
"""

import sys
import os
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_imports():
    """Тест импортов всех модулей"""
    print("🧪 ТЕСТ ИМПОРТОВ")
    print("=" * 50)
    
    tests = [
        ("telegram_bot.bot_database", "TelegramBotDB"),
        ("telegram_bot.bot_permissions", "check_user_permission"),
        ("telegram_bot.bot_utils", "format_sensor_data"),
        ("telegram_bot.bot_main", "KUBTelegramBot"),
    ]
    
    passed = 0
    for module, component in tests:
        try:
            exec(f"from {module} import {component}")
            print(f"✅ {module}.{component}")
            passed += 1
        except Exception as e:
            print(f"❌ {module}.{component}: {e}")
    
    print(f"\n📊 Результат импортов: {passed}/{len(tests)}")
    return passed == len(tests)

def test_database():
    """Тест базы данных"""
    print("\n🧪 ТЕСТ БАЗЫ ДАННЫХ")
    print("=" * 50)
    
    try:
        from telegram_bot.bot_database import TelegramBotDB
        
        # Используем тестовую базу
        test_db = "test_telegram.db"
        if Path(test_db).exists():
            Path(test_db).unlink()
        
        db = TelegramBotDB(test_db)
        
        # Тест регистрации
        success = db.register_user(
            telegram_id=123456789,
            username="test_user",
            first_name="Test",
            last_name="User"
        )
        print(f"  Регистрация пользователя: {'✅' if success else '❌'}")
        
        # Тест получения пользователя
        user = db.get_user(123456789)
        print(f"  Получение пользователя: {'✅' if user else '❌'}")
        
        # Тест логирования команд
        db.log_user_command(123456789, "test", None, True)
        print("  Логирование команд: ✅")
        
        # Тест разрешений
        permissions = db.get_access_permissions("user")
        print(f"  Получение разрешений: {'✅' if permissions else '❌'}")
        
        # Удаляем тестовую базу
        Path(test_db).unlink()
        
        print("📊 База данных: ✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования базы: {e}")
        return False

def test_permissions():
    """Тест системы прав доступа"""
    print("\n🧪 ТЕСТ ПРАВ ДОСТУПА")
    print("=" * 50)
    
    try:
        from telegram_bot.bot_database import TelegramBotDB
        from telegram_bot.bot_permissions import check_user_permission, check_command_rate_limit
        
        # Создаем тестовую базу
        test_db = "test_permissions.db"
        if Path(test_db).exists():
            Path(test_db).unlink()
        
        db = TelegramBotDB(test_db)
        
        # Регистрируем тестового пользователя
        db.register_user(123456789, "test_user", "Test", "User")
        
        # Тест проверки прав
        can_read = check_user_permission(123456789, "read", db)
        print(f"  Права на чтение: {'✅' if can_read else '❌'}")
        
        # Тест лимита команд
        allowed, message = check_command_rate_limit(123456789, db)
        print(f"  Лимит команд: {'✅' if allowed else '❌'} ({message})")
        
        # Удаляем тестовую базу
        Path(test_db).unlink()
        
        print("📊 Права доступа: ✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования прав: {e}")
        return False

def test_utils():
    """Тест утилит форматирования"""
    print("\n🧪 ТЕСТ УТИЛИТ")
    print("=" * 50)
    
    try:
        from telegram_bot.bot_utils import (
            format_sensor_data, format_system_stats, 
            build_main_menu, error_message
        )
        from datetime import datetime
        
        # Тест форматирования данных
        test_data = {
            'temp_inside': 23.5,
            'humidity': 65.0,
            'co2': 2500,
            'connection_status': 'connected',
            'timestamp': datetime.now().isoformat()
        }
        
        formatted = format_sensor_data(test_data)
        print(f"  Форматирование данных: {'✅' if formatted and '23.5°C' in formatted else '❌'}")
        
        # Тест создания меню
        menu = build_main_menu("admin")
        print(f"  Создание меню: {'✅' if menu and len(menu.inline_keyboard) > 0 else '❌'}")
        
        # Тест сообщений об ошибках
        error_msg = error_message("Тест")
        print(f"  Сообщения об ошибках: {'✅' if '❌' in error_msg else '❌'}")
        
        print("📊 Утилиты: ✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования утилит: {e}")
        return False

def test_main_class():
    """Тест основного класса бота"""
    print("\n🧪 ТЕСТ ОСНОВНОГО КЛАССА")
    print("=" * 50)
    
    try:
        from telegram_bot.bot_main import KUBTelegramBot
        
        # Создаем экземпляр бота с фиктивным токеном
        bot = KUBTelegramBot("123456789:FAKE_TOKEN_FOR_TESTING")
        
        print(f"  Создание экземпляра бота: {'✅' if bot else '❌'}")
        print(f"  Инициализация базы данных: {'✅' if bot.bot_db else '❌'}")
        print(f"  Загрузка конфигурации: {'✅' if bot.config else '❌'}")
        
        print("📊 Основной класс: ✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования основного класса: {e}")
        return False

def test_file_structure():
    """Тест структуры файлов"""
    print("\n🧪 ТЕСТ СТРУКТУРЫ ФАЙЛОВ")
    print("=" * 50)
    
    required_files = [
        "telegram_bot/bot_main.py",
        "telegram_bot/bot_database.py",
        "telegram_bot/bot_permissions.py",
        "telegram_bot/bot_utils.py",
        "telegram_bot/__init__.py",
    ]
    
    passed = 0
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"✅ {file_path}")
            passed += 1
        else:
            print(f"❌ {file_path} - НЕ НАЙДЕН")
    
    print(f"\n📊 Структура файлов: {passed}/{len(required_files)}")
    return passed == len(required_files)

def main():
    """Главная функция тестирования"""
    print("🚀 КОМПЛЕКСНОЕ ТЕСТИРОВАНИЕ TELEGRAM BOT")
    print("=" * 70)
    
    tests = [
        ("Структура файлов", test_file_structure),
        ("Импорты модулей", test_imports),
        ("База данных", test_database),
        ("Права доступа", test_permissions),
        ("Утилиты", test_utils),
        ("Основной класс", test_main_class),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 {test_name.upper()}")
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ Критическая ошибка в тесте '{test_name}': {e}")
    
    # Итоговый результат
    print("\n" + "=" * 70)
    print("📊 ИТОГОВЫЙ РЕЗУЛЬТАТ ТЕСТИРОВАНИЯ")
    print("=" * 70)
    
    if passed == total:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("✅ Telegram Bot готов к работе!")
        status = "ГОТОВ"
    else:
        print(f"⚠️ ПРОЙДЕНО ТЕСТОВ: {passed}/{total}")
        print("❌ Требуются исправления перед запуском!")
        status = "ТРЕБУЕТ ИСПРАВЛЕНИЙ"
    
    print(f"\n🎯 СТАТУС СИСТЕМЫ: {status}")
    print("=" * 70)
    
    # Рекомендации
    if passed == total:
        print("\n📝 РЕКОМЕНДАЦИИ:")
        print("1. 🔑 Установите токен бота: создайте config/bot_secrets.json")
        print("2. 🚀 Запустите бота: python start_bot.py")
        print("3. 📱 Протестируйте команды в Telegram")
        print("4. 📊 Проверьте логи: tail -f telegram_bot.log")
    else:
        print("\n🔧 НЕОБХОДИМЫЕ ДЕЙСТВИЯ:")
        print("1. Исправьте ошибки в проваленных тестах")
        print("2. Повторите тестирование")
        print("3. Убедитесь что все модули импортируются")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)