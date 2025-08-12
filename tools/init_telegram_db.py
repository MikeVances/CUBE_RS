#!/usr/bin/env python3
"""
Инициализация таблиц для Telegram Bot
Запуск: python init_telegram_db.py
"""

import sqlite3
import logging
from pathlib import Path

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def init_telegram_tables(db_file: str = "kub_commands.db"):
    """Создание таблиц для Telegram Bot"""
    
    # Проверяем существование файла базы
    if not Path(db_file).exists():
        logger.error(f"❌ База данных {db_file} не найдена!")
        logger.info("💡 Сначала запустите UnifiedKUBSystem для создания основных таблиц")
        return False
    
    try:
        with sqlite3.connect(db_file) as conn:
            logger.info(f"📂 Подключение к базе {db_file}")
            
            # 1. Таблица пользователей Telegram
            logger.info("📋 Создание таблицы telegram_users...")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telegram_users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    access_level TEXT DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    total_commands INTEGER DEFAULT 0,
                    last_command_at TIMESTAMP
                )
            """)
            
            # 2. Индексы для быстрого поиска
            logger.info("🔍 Создание индексов...")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telegram_access ON telegram_users(access_level)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telegram_active ON telegram_users(is_active)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telegram_last_active ON telegram_users(last_active)")
            
            # 3. Таблица настроек доступа
            logger.info("⚙️ Создание таблицы access_config...")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS access_config (
                    access_level TEXT PRIMARY KEY,
                    allowed_registers TEXT,      -- JSON массив регистров
                    can_read BOOLEAN DEFAULT TRUE,
                    can_write BOOLEAN DEFAULT FALSE,
                    can_reset_alarms BOOLEAN DEFAULT FALSE,
                    max_commands_per_hour INTEGER DEFAULT 10,
                    description TEXT
                )
            """)
            
            # 4. Заполняем базовые уровни доступа
            logger.info("🔐 Настройка уровней доступа...")
            access_levels = [
                ('user', '[]', True, False, False, 5, 'Только чтение данных'),
                ('operator', '["0x0020"]', True, True, True, 20, 'Сброс аварий'),
                ('admin', '["0x0020", "0x003F"]', True, True, True, 50, 'Управление и настройки'),
                ('engineer', '["0x0020", "0x003F", "0x0100-0x010F", "0x0110-0x0117"]', True, True, True, 100, 'Полный доступ')
            ]
            
            conn.executemany("""
                INSERT OR REPLACE INTO access_config 
                (access_level, allowed_registers, can_read, can_write, can_reset_alarms, max_commands_per_hour, description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, access_levels)
            
            # 5. Таблица истории команд пользователей (для лимитов)
            logger.info("📊 Создание таблицы user_command_history...")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_command_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER,
                    command_type TEXT,           -- 'read', 'write', 'status'
                    register_address TEXT,       -- '0x0020' или NULL для read/status
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    success BOOLEAN,
                    FOREIGN KEY (telegram_id) REFERENCES telegram_users(telegram_id)
                )
            """)
            
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_history_time ON user_command_history(telegram_id, timestamp)")
            
            # 6. Проверяем что всё создалось
            logger.info("✅ Проверка созданных таблиц...")
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%telegram%' OR name LIKE '%access%'")
            tables = cursor.fetchall()
            
            logger.info("📋 Созданные таблицы:")
            for table in tables:
                logger.info(f"   • {table[0]}")
            
            # 7. Показываем статистику базы
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            all_tables = cursor.fetchall()
            logger.info(f"📊 Всего таблиц в базе: {len(all_tables)}")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации таблиц: {e}")
        return False

def show_database_info(db_file: str = "kub_commands.db"):
    """Показать информацию о базе данных"""
    
    if not Path(db_file).exists():
        logger.warning(f"⚠️ База данных {db_file} не найдена")
        return
    
    try:
        with sqlite3.connect(db_file) as conn:
            logger.info(f"📊 ИНФОРМАЦИЯ О БАЗЕ {db_file}")
            logger.info("=" * 50)
            
            # Список всех таблиц
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = cursor.fetchall()
            
            for table in tables:
                table_name = table[0]
                
                # Считаем записи в таблице
                count_cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = count_cursor.fetchone()[0]
                
                logger.info(f"📋 {table_name}: {count} записей")
                
                # Для новых таблиц показываем структуру
                if 'telegram' in table_name or 'access' in table_name:
                    schema_cursor = conn.execute(f"PRAGMA table_info({table_name})")
                    columns = schema_cursor.fetchall()
                    logger.info(f"   Поля: {', '.join([col[1] for col in columns])}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка получения информации: {e}")

def main():
    """Основная функция"""
    print("🤖 ИНИЦИАЛИЗАЦИЯ ТАБЛИЦ ДЛЯ TELEGRAM BOT")
    print("=" * 50)
    
    # Показываем текущее состояние
    show_database_info()
    
    # Создаём таблицы
    success = init_telegram_tables()
    
    if success:
        print("\n✅ ТАБЛИЦЫ СОЗДАНЫ УСПЕШНО!")
        print("🚀 Теперь можно создавать Telegram Bot")
        
        # Показываем обновленную информацию
        print("\n" + "=" * 50)
        show_database_info()
        
    else:
        print("\n❌ ОШИБКА СОЗДАНИЯ ТАБЛИЦ")
        print("💡 Проверьте логи выше")

if __name__ == "__main__":
    main()
