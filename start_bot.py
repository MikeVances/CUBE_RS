#!/usr/bin/env python3
"""
Исправленный скрипт запуска Telegram Bot для КУБ-1063
Использует SecureConfig для безопасной работы с токенами
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Добавляем пути к модулям
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))
sys.path.insert(0, str(script_dir / 'telegram_bot'))

def setup_logging():
    """Настройка логирования"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('telegram_bot.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

def check_basic_requirements():
    """Проверка базовых требований (без токена)"""
    print("🔍 Проверка базовых требований...")
    
    # Проверяем python-telegram-bot
    try:
        import telegram
        print(f"✅ python-telegram-bot установлен (версия {telegram.__version__})")
    except ImportError:
        print("❌ python-telegram-bot не установлен")
        print("💡 Установите: pip install python-telegram-bot")
        return False
    
    # Проверяем базу данных
    if not Path('kub_commands.db').exists():
        print("❌ База данных kub_commands.db не найдена")
        print("💡 Запустите сначала:")
        print("   python scripts/create_base_db.py")
        print("   python scripts/init_telegram_db.py")
        return False
    
    print("✅ База данных найдена")
    
    # Проверяем модули бота
    required_modules = [
        'telegram_bot/bot_main.py',
        'telegram_bot/bot_database.py', 
        'telegram_bot/bot_permissions.py',
        'telegram_bot/bot_utils.py',
        'telegram_bot/secure_config.py'
    ]
    
    for module in required_modules:
        if not Path(module).exists():
            print(f"❌ Файл {module} не найден")
            return False
    
    print("✅ Все модули бота найдены")
    return True

def check_token_specifically():
    """Отдельная проверка токена (для --check команды)"""
    print("\n🔑 Проверка токена...")
    
    try:
        from telegram_bot.secure_config import SecureConfig
        config = SecureConfig()
        
        # Проверяем только файл, не запрашиваем интерактивно
        token = config._load_token_from_file()
        
        if token:
            print(f"✅ Токен найден в config/bot_secrets.json: {token[:10]}...{token[-5:]}")
            return True
        else:
            print("⚠️ Токен не найден в config/bot_secrets.json")
            print("💡 При запуске бота система запросит токен интерактивно")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка проверки токена: {e}")
        return False

def show_bot_info():
    """Показать информацию о боте"""
    print("\n" + "=" * 60)
    print("🤖 TELEGRAM BOT ДЛЯ КУБ-1063")
    print("=" * 60)
    print("📝 Функции:")
    print("   • Чтение показаний датчиков")
    print("   • Статистика работы системы")
    print("   • Сброс аварий (для операторов)")
    print("   • Управление регистрами (для инженеров)")
    print("   • Система прав доступа")
    print("")
    print("🔧 Компоненты:")
    print("   • UnifiedKUBSystem - основная система")
    print("   • SQLite база данных")
    print("   • Система аудита команд")
    print("   • Многоуровневые права доступа")
    print("")
    print("📊 Уровни доступа:")
    print("   • user     - только чтение")
    print("   • operator - чтение + сброс аварий")
    print("   • admin    - управление + настройки")
    print("   • engineer - полный доступ")
    print("=" * 60)

def check_system_health():
    """Проверка работоспособности системы"""
    print("\n🏥 Проверка работоспособности системы...")
    
    try:
        # Проверяем подключение к базе
        from telegram_bot.bot_database import TelegramBotDB
        db = TelegramBotDB()
        
        # Проверяем таблицы
        users = db.get_all_users()
        print(f"✅ База данных: {len(users)} пользователей")
        
        # Проверяем UnifiedKUBSystem
        from modbus.unified_system import UnifiedKUBSystem
        system = UnifiedKUBSystem()
        print("✅ UnifiedKUBSystem инициализирован")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка проверки системы: {e}")
        return False

async def main():
    """Главная функция"""
    # Настройка логирования
    setup_logging()
    
    # Показываем информацию
    show_bot_info()
    
    # Проверяем базовые требования
    if not check_basic_requirements():
        print("\n💥 Не все базовые требования выполнены!")
        return
    
    # Проверяем систему
    if not check_system_health():
        print("\n💥 Система не готова к работе!")
        return
    
    print("\n🚀 Запуск Telegram Bot...")
    print("🔑 Токен будет запрошен безопасным способом...")
    
    try:
        # Импортируем и запускаем бота
        from telegram_bot.bot_main import KUBTelegramBot
        from telegram_bot.secure_config import SecureConfig
        
        # Получаем токен безопасным способом (интерактивно если нужно)
        config = SecureConfig()
        token = config.get_bot_token()
        
        if not token:
            print("❌ Не удалось получить токен бота")
            print("💡 Проверьте настройки или создайте нового бота у @BotFather")
            return
        
        bot = KUBTelegramBot(token)
        
        print("✅ Бот создан, начинаем работу...")
        print("⚠️  Нажмите Ctrl+C для остановки")
        print("")
        
        # Запускаем
        await bot.start_bot()
        
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки...")
        try:
            await bot.stop_bot()
        except:
            pass
        print("✅ Бот остановлен")
        
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        logging.exception("Критическая ошибка")

def install_requirements():
    """Установка требований"""
    print("📦 Установка python-telegram-bot...")
    
    import subprocess
    
    try:
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install', 
            'python-telegram-bot[all]'
        ])
        print("✅ python-telegram-bot установлен")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка установки: {e}")
        return False

if __name__ == "__main__":
    print("🎯 ЗАПУСК TELEGRAM BOT ДЛЯ КУБ-1063")
    
    # Проверяем аргументы командной строки
    if len(sys.argv) > 1:
        if sys.argv[1] == "--install":
            install_requirements()
            sys.exit(0)
        elif sys.argv[1] == "--check":
            print("🔍 ПОЛНАЯ ПРОВЕРКА СИСТЕМЫ")
            print("=" * 40)
            
            # Проверяем всё включая токен
            basic_ok = check_basic_requirements()
            token_ok = check_token_specifically()
            system_ok = check_system_health()
            
            if basic_ok and system_ok:
                print("\n✅ Система готова к запуску!")
                if token_ok:
                    print("🔑 Токен настроен корректно")
                else:
                    print("⚠️ Токен будет запрошен при запуске")
            else:
                print("\n❌ Система не готова")
            sys.exit(0)
            
        elif sys.argv[1] == "--help":
            print("\nИспользование:")
            print("  python start_bot.py           # Запуск бота")
            print("  python start_bot.py --install # Установка зависимостей")
            print("  python start_bot.py --check   # Полная проверка системы")
            print("  python start_bot.py --help    # Эта справка")
            sys.exit(0)
    
    # Запускаем основную функцию
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
    except Exception as e:
        print(f"\n💥 Неожиданная ошибка: {e}")
        logging.exception("Неожиданная ошибка при запуске")