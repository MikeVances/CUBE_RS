#!/usr/bin/env python3
"""
SERVER: Создание основных баз данных для CUBE_RS SERVER
Создает базы данных для веб-приложения, RBAC системы и реестра устройств
"""

import logging
import os
import sys
import sqlite3
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_server_databases():
    """Создание основных баз данных SERVER"""

    print("🗄️ СОЗДАНИЕ БАЗ ДАННЫХ CUBE_RS SERVER")
    print("=" * 50)

    try:
        # Создаем директории если их нет
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        
        web_app_dir = Path("web_app")
        web_app_dir.mkdir(exist_ok=True)

        # 1. Создаем базу данных для RBAC системы
        logger.info("🔐 Создание RBAC системы...")
        create_rbac_database()
        logger.info("✅ RBAC база данных создана")

        # 2. Создаем базу данных реестра устройств
        logger.info("📱 Создание реестра устройств...")
        create_device_registry_database()
        logger.info("✅ База реестра устройств создана")

        # 3. Создаем базу данных для туннельного брокера
        logger.info("🔗 Создание базы туннельного брокера...")
        create_tunnel_broker_database()
        logger.info("✅ База туннельного брокера создана")

        # 4. Проверяем созданные файлы
        db_files = [
            "web_app/rbac_system.db",
            "web_app/device_registry.db", 
            "data/tunnel_broker.db"
        ]
        
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

        for db_file in db_files:
            with sqlite3.connect(db_file) as conn:
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                logger.info(f"   📊 {db_file}: {len(tables)} таблиц")

        print("\n🎉 ВСЕ БАЗЫ ДАННЫХ SERVER СОЗДАНЫ!")
        print("🚀 Теперь можно запускать веб-приложение")
        return True

    except Exception as e:
        logger.error(f"❌ Общая ошибка: {e}")
        return False


def create_rbac_database():
    """Создание базы данных для RBAC системы"""
    db_path = "web_app/rbac_system.db"
    
    with sqlite3.connect(db_path) as conn:
        # Создаем таблицы для RBAC
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role_id TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                failed_login_attempts INTEGER DEFAULT 0,
                locked_until TIMESTAMP,
                FOREIGN KEY (role_id) REFERENCES roles(role_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                role_id TEXT PRIMARY KEY,
                role_name TEXT UNIQUE NOT NULL,
                description TEXT,
                permissions TEXT,  -- JSON array of permissions
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                success BOOLEAN NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Создаем индексы
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON user_sessions(expires_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)")

        # Добавляем базовые роли
        roles = [
            ("admin", "Administrator", "Полный доступ к системе", '["device:view", "device:connect", "device:configure", "service:api", "service:modbus", "service:tunnel", "user:manage", "system:config"]'),
            ("farm_operator", "Farm Operator", "Управление фермами", '["device:view", "device:connect", "device:configure", "service:api", "service:modbus", "service:tunnel"]'),
            ("viewer", "Viewer", "Просмотр данных", '["device:view", "service:api"]'),
            ("mobile_user", "Mobile User", "Мобильный доступ", '["device:view", "device:connect", "service:tunnel"]')
        ]

        conn.executemany("""
            INSERT OR IGNORE INTO roles (role_id, role_name, description, permissions)
            VALUES (?, ?, ?, ?)
        """, roles)

        conn.commit()


def create_device_registry_database():
    """Создание базы данных реестра устройств"""
    db_path = "web_app/device_registry.db"
    
    with sqlite3.connect(db_path) as conn:
        # Основная таблица устройств
        conn.execute("""
            CREATE TABLE IF NOT EXISTS registered_devices (
                device_id TEXT PRIMARY KEY,
                hostname TEXT NOT NULL,
                tailscale_ip TEXT NOT NULL,
                auth_key_hash TEXT NOT NULL,
                registration_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',  -- pending, active, inactive, revoked
                device_type TEXT DEFAULT 'unknown',  -- farm, mobile, gateway, edge
                metadata TEXT,  -- JSON with additional device info
                created_by TEXT,
                notes TEXT
            )
        """)

        # Таблица валидных auth keys
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_keys (
                key_hash TEXT PRIMARY KEY,
                device_type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                is_used BOOLEAN DEFAULT FALSE,
                used_by_device TEXT,
                created_by TEXT,
                FOREIGN KEY (used_by_device) REFERENCES registered_devices(device_id)
            )
        """)

        # Таблица истории устройств
        conn.execute("""
            CREATE TABLE IF NOT EXISTS device_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                event_type TEXT NOT NULL,  -- registered, activated, deactivated, revoked
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT,
                FOREIGN KEY (device_id) REFERENCES registered_devices(device_id)
            )
        """)

        # Создаем индексы
        conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_hostname ON registered_devices(hostname)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_ip ON registered_devices(tailscale_ip)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_status ON registered_devices(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_type ON registered_devices(device_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_keys_type ON auth_keys(device_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_keys_expires ON auth_keys(expires_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_history_device ON device_history(device_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_history_timestamp ON device_history(timestamp)")

        conn.commit()


def create_tunnel_broker_database():
    """Создание базы данных для туннельного брокера"""
    db_path = "data/tunnel_broker.db"
    
    with sqlite3.connect(db_path) as conn:
        # Таблица активных соединений
        conn.execute("""
            CREATE TABLE IF NOT EXISTS active_connections (
                request_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                farm_id TEXT NOT NULL,
                status TEXT DEFAULT 'pending',  -- pending, establishing, connected, failed, expired
                created_at REAL NOT NULL,
                last_activity REAL NOT NULL,
                app_offer TEXT,  -- JSON
                farm_answer TEXT,  -- JSON
                connection_details TEXT  -- JSON
            )
        """)

        # Таблица статистики соединений
        conn.execute("""
            CREATE TABLE IF NOT EXISTS connection_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                farm_id TEXT NOT NULL,
                connection_duration REAL,
                bytes_transferred INTEGER DEFAULT 0,
                status TEXT NOT NULL,  -- completed, failed, timeout
                error_message TEXT,
                started_at REAL NOT NULL,
                ended_at REAL NOT NULL
            )
        """)

        # Таблица ферм и их статусов
        conn.execute("""
            CREATE TABLE IF NOT EXISTS farm_status (
                farm_id TEXT PRIMARY KEY,
                farm_name TEXT,
                last_seen REAL NOT NULL,
                status TEXT DEFAULT 'offline',  -- online, offline, error
                capabilities TEXT,  -- JSON array
                connection_info TEXT,  -- JSON
                last_error TEXT,
                error_count INTEGER DEFAULT 0
            )
        """)

        # Создаем индексы
        conn.execute("CREATE INDEX IF NOT EXISTS idx_connections_user ON active_connections(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_connections_farm ON active_connections(farm_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_connections_status ON active_connections(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_connections_activity ON active_connections(last_activity)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stats_user ON connection_stats(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stats_farm ON connection_stats(farm_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stats_started ON connection_stats(started_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_farm_status_seen ON farm_status(last_seen)")

        conn.commit()


def show_project_structure():
    """Показать структуру SERVER проекта"""
    logger.info("📁 Структура SERVER проекта:")

    important_paths = [
        "web_app/",
        "web_app/app.py",
        "web_app/rbac_system.py",
        "web_app/device_registry.py",
        "web_app/api_gateway.py",
        "data/",
        "tools/",
        "monitoring/",
        "security/",
        "web_app/rbac_system.db",
        "web_app/device_registry.db",
        "data/tunnel_broker.db"
    ]

    for path in important_paths:
        path_obj = Path(path)
        if path_obj.exists():
            if path_obj.is_dir():
                logger.info(f"   📁 {path}")
            else:
                size = path_obj.stat().st_size
                logger.info(f"   📄 {path} ({size} байт)")
        else:
            logger.info(f"   ❌ {path} - отсутствует")


def show_database_info(db_file: str):
    """Показать информацию о базе данных"""
    if not Path(db_file).exists():
        logger.warning(f"⚠️ База данных {db_file} не найдена")
        return

    try:
        with sqlite3.connect(db_file) as conn:
            logger.info(f"📊 ИНФОРМАЦИЯ О БАЗЕ {db_file}")
            
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = cursor.fetchall()

            for table in tables:
                table_name = table[0]
                count_cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = count_cursor.fetchone()[0]
                logger.info(f"   📋 {table_name}: {count} записей")

    except Exception as e:
        logger.error(f"❌ Ошибка получения информации: {e}")


if __name__ == "__main__":
    print("🏗️ Инициализация инфраструктуры CUBE_RS SERVER")

    # Показываем текущую структуру
    show_project_structure()

    # Создаём базы данных
    success = create_server_databases()

    if success:
        print("\n" + "=" * 50)
        print("✅ ГОТОВО! Следующие шаги:")
        print("1️⃣ python tools/start_all_services.py  # Запустить все сервисы")
        print("2️⃣ Открыть http://localhost:8080      # Веб-интерфейс")
        
        print("\n📊 Информация о созданных базах данных:")
        for db_file in ["web_app/rbac_system.db", "web_app/device_registry.db", "data/tunnel_broker.db"]:
            show_database_info(db_file)
    else:
        print("\n❌ Что-то пошло не так. Проверьте ошибки выше.")