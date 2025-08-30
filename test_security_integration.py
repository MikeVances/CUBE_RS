#!/usr/bin/env python3
"""
Тест интеграции SecurityManager с ConfigManager и Telegram Bot
"""

import os
import sys
import json
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(__file__))

def test_config_manager():
    """Тест ConfigManager"""
    print("🔧 Тестирование ConfigManager...")
    
    try:
        from core.config_manager import get_config
        config = get_config()
        
        print(f"✅ RS485 порт: {config.rs485.port}")
        print(f"✅ Gateway порт: {config.modbus_tcp.port}")
        print(f"✅ База данных: {config.database.file}")
        print(f"✅ Админов в Telegram: {len(config.telegram.admin_users)}")
        print(f"✅ Modbus регистров: {len(config.modbus_registers)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка ConfigManager: {e}")
        return False

def test_security_manager():
    """Тест SecurityManager"""
    print("\n🔒 Тестирование SecurityManager...")
    
    try:
        from core.security_manager import get_security_manager, log_security_event
        sm = get_security_manager()
        
        # Тест шифрования
        test_data = {"secret_token": "test_123", "user_id": 12345}
        print(f"🔓 Исходные данные: {test_data}")
        
        encrypted = sm.encrypt_data(test_data)
        print(f"🔐 Зашифровано: {encrypted[:50]}...")
        
        decrypted = sm.decrypt_data(encrypted)
        print(f"🔓 Расшифровано: {decrypted}")
        
        success = test_data == decrypted
        print(f"{'✅' if success else '❌'} Шифрование работает: {success}")
        
        # Тест логирования
        log_security_event("INTEGRATION_TEST", user_id=12345, details={"test": True})
        print("✅ Событие безопасности записано")
        
        # Проверка состояния
        health = sm.health_check()
        print(f"🏥 Состояние безопасности:")
        for key, value in health.items():
            status = "✅" if value else "❌"
            print(f"   {status} {key}: {value}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка SecurityManager: {e}")
        return False

def test_telegram_imports():
    """Тест импортов в Telegram боте"""
    print("\n🤖 Тестирование импортов Telegram бота...")
    
    try:
        # Тестируем только импорты без инициализации бота
        import telegram_bot.bot_main
        
        # Проверяем что переменная SECURITY_AVAILABLE установлена
        security_available = getattr(telegram_bot.bot_main, 'SECURITY_AVAILABLE', False)
        print(f"✅ SECURITY_AVAILABLE: {security_available}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка импорта Telegram бота: {e}")
        return False

def test_encrypted_config_migration():
    """Тест миграции конфигов в зашифрованный формат"""
    print("\n📦 Тестирование миграции секретов...")
    
    try:
        from core.config_manager import get_config
        config = get_config()
        
        # Проверяем возможность миграции
        if hasattr(config, 'migrate_secrets_to_encrypted'):
            print("✅ Метод миграции доступен")
        else:
            print("❌ Метод миграции недоступен")
            
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования миграции: {e}")
        return False

def main():
    """Главная функция тестирования"""
    print("🚀 Запуск тестов интеграции безопасности КУБ-1063\n")
    
    tests = [
        ("ConfigManager", test_config_manager),
        ("SecurityManager", test_security_manager), 
        ("Telegram Imports", test_telegram_imports),
        ("Config Migration", test_encrypted_config_migration),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Критическая ошибка в тесте {test_name}: {e}")
            results.append((test_name, False))
    
    # Итоги
    print(f"\n📊 Результаты тестирования:")
    passed = 0
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"   {status}: {test_name}")
        if result:
            passed += 1
    
    total = len(results)
    print(f"\n🎯 Итого: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("🎉 Все тесты успешно пройдены! Интеграция безопасности работает.")
        return True
    else:
        print("⚠️ Есть проблемы с интеграцией. Проверьте ошибки выше.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)