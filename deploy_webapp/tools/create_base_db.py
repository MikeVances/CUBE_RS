#!/usr/bin/env python3
"""
Создание основной базы данных для CUBE_RS
Запуск: python scripts/create_base_db.py
"""

import sys
import os
import logging
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_base_databases():
    """Создание основных баз данных проекта"""
    
    print("🗄️ СОЗДАНИЕ ОСНОВНЫХ БАЗ ДАННЫХ CUBE_RS")
    print("=" * 50)
    
    try:
        # 1. Импортируем необходимые модули
        logger.info("📦 Импорт модулей...")
        from modbus.modbus_storage import init_db as init_data_db
        from modbus.writer import CommandStorage
        
        # 2. Создаём базу данных для данных КУБ
        logger.info("🗄️ Создание базы данных для данных КУБ...")
        init_data_db()
        logger.info("✅ База kub_data.db создана")
        
        # 3. Создаём базу данных для команд
        logger.info("📝 Создание базы данных для команд...")
        command_storage = CommandStorage("kub_commands.db")
        logger.info("✅ База kub_commands.db создана")
        
        # 4. Проверяем созданные файлы
        db_files = ["kub_data.db", "kub_commands.db"]
        logger.info("🔍 Проверка созданных баз данных:")
        
        for db_file in db_files:
            if Path(db_file).exists():
                size = Path(db_file).stat().st_size
                logger.info(f"   ✅ {db_file} - {size} байт")
            else:
                logger.error(f"   ❌ {db_file} - не создан!")
                return False
        
        # 5. Тестируем подключение к базам
        logger.info("🧪 Тестирование подключений...")
        
        import sqlite3
        
        # Тест базы данных
        with sqlite3.connect("kub_data.db") as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            logger.info(f"   📊 kub_data.db: {len(tables)} таблиц")
        
        # Тест базы команд
        with sqlite3.connect("kub_commands.db") as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            logger.info(f"   📝 kub_commands.db: {len(tables)} таблиц")
            
            # Показываем созданные таблицы
            logger.info("   📋 Таблицы в kub_commands.db:")
            for table in tables:
                logger.info(f"      • {table[0]}")
        
        print("\n🎉 ВСЕ ОСНОВНЫЕ БАЗЫ ДАННЫХ СОЗДАНЫ!")
        print("🚀 Теперь можно создавать таблицы для Telegram Bot")
        return True
        
    except ImportError as e:
        logger.error(f"❌ Ошибка импорта модулей: {e}")
        logger.error("💡 Убедитесь что находитесь в корне проекта CUBE_RS")
        return False
        
    except Exception as e:
        logger.error(f"❌ Общая ошибка: {e}")
        return False

def show_project_structure():
    """Показать структуру проекта"""
    logger.info("📁 Структура проекта:")
    
    important_paths = [
        "modbus/",
        "modbus/unified_system.py",
        "modbus/writer.py", 
        "modbus/modbus_storage.py",
        "scripts/",
        "telegram_bot/",
        "kub_data.db",
        "kub_commands.db"
    ]
    
    for path in important_paths:
        if Path(path).exists():
            if Path(path).is_dir():
                logger.info(f"   📁 {path}")
            else:
                size = Path(path).stat().st_size
                logger.info(f"   📄 {path} ({size} байт)")
        else:
            logger.info(f"   ❌ {path} - отсутствует")

if __name__ == "__main__":
    print("🏗️ Инициализация основной инфраструктуры CUBE_RS")
    
    # Показываем текущую структуру
    show_project_structure()
    
    # Создаём базы данных
    success = create_base_databases()
    
    if success:
        print("\n" + "=" * 50)
        print("✅ ГОТОВО! Следующие шаги:")
        print("1️⃣ python scripts/init_telegram_db.py  # Создать таблицы для бота")
        print("2️⃣ Создавать Telegram Bot в telegram_bot/")
    else:
        print("\n❌ Что-то пошло не так. Проверьте ошибки выше.")