#!/usr/bin/env python3
"""
Скрипт запуска Telegram Bot для КУБ-1063
Простой запуск: python start_bot.py
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

def check_requirements():
    """Проверка требований для запуска"""
    print("🔍 Проверка требований...")
    
    # Проверяем токен бота
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN не найден в переменных окружения")
        print("💡 Установите токен:")
        print("   export TELEGRAM_BOT_TOKEN='your_bot_token_here'")
        print("   или")
        print("   set TELEGRAM_BOT_TOKEN=your_bot_token_here  (Windows)")
        return False
    
    print(f"✅ Токен бота найден: {token[:10]}...{token[-5:]}")
    
    # Проверяем базу данных
    if not Path('kub_commands.db').exists():
        print("❌ База данных kub_commands.db не найдена")
        print("💡 Запустите сначала:")
        print("   python scripts/create_base_db.py")
        print("   python scripts/init_telegram_db.py")
        return False
    
    print("✅ База данных найдена")
    
    # Проверяем модули
    required_modules = [
        'telegram_bot/bot_main.py',
        'telegram_bot/bot_database.py', 
        'telegram_bot/bot_permissions.py',
        'telegram_bot/bot_utils.py'
    ]
    
    for module in required_modules:
        if not Path(module).exists():
            print(f"❌ Файл {module} не найден")
            return False
    
    print("✅ Все модули бота найдены")
    
    # Проверяем python-telegram-bot
    try:
        import telegram
        print(f"✅ python-telegram-bot установлен (версия {telegram.__version__})")
    except ImportError:
        print("❌ python-telegram-bot не установлен")
        print("💡 Установите: pip install python-telegram-bot")
        return False
    
    return True

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
    
    # Проверяем требования
    if not check_requirements():
        print("\n💥 Не все требования выполнены!")
        return
    
    # Проверяем систему
    if not check_system_health():
        print("\n💥 Система не готова к работе!")
        return
    
    print("\n🚀 Запуск Telegram Bot...")
    
    try:
        # Импортируем и запускаем бота
        from telegram_bot.bot_main import KUBTelegramBot
        
        token = os.getenv('TELEGRAM_BOT_TOKEN')
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
            check_requirements()
            check_system_health()
            sys.exit(0)
        elif sys.argv[1] == "--help":
            print("\nИспользование:")
            print("  python start_bot.py           # Запуск бота")
            print("  python start_bot.py --install # Установка зависимостей")
            print("  python start_bot.py --check   # Проверка системы")
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