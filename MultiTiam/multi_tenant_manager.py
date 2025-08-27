#!/usr/bin/env python3
"""
Multi-Tenant Manager для CUBE_RS
Управление доступом пользователей к конкретному оборудованию
Интеграция с существующей архитектурой системы
"""

import sqlite3
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

class Device:
    """Представление КУБ-устройства в системе"""
    
    def __init__(self, device_id: str, device_name: str, modbus_slave_id: int, 
                 organization_name: str, location: str = None, access_level: str = "read"):
        self.device_id = device_id
        self.device_name = device_name
        self.modbus_slave_id = modbus_slave_id
        self.organization_name = organization_name
        self.location = location
        self.access_level = access_level
    
    def __str__(self):
        location_str = f" ({self.location})" if self.location else ""
        return f"{self.device_name}{location_str} - {self.organization_name}"

class MultiTenantManager:
    """
    Менеджер для управления многопользовательским доступом к КУБ-устройствам
    
    Основные функции:
    - Проверка прав доступа пользователей к устройствам
    - Фильтрация данных по принадлежности оборудования
    - Управление организациями и ролями
    - Аудит доступа к устройствам
    """
    
    def __init__(self, db_file: str = "cube_multitenant.db"):
        self.db_file = db_file
        self._ensure_database_exists()
        logger.info(f"🏢 MultiTenantManager инициализирован с базой {db_file}")
    
    def _ensure_database_exists(self):
        """Создание базы данных если не существует"""
        if not Path(self.db_file).exists():
            logger.info("🏗️ Создание multi-tenant базы данных...")
            self._create_database()
    
    def _create_database(self):
        """Создание таблиц multi-tenant системы"""
        # Здесь будет SQL из предыдущего артефакта
        # Для краткости показываю основные таблицы
        
        sql_commands = [
            # Организации
            """CREATE TABLE IF NOT EXISTS organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT UNIQUE NOT NULL,
                description TEXT,
                contact_person TEXT,
                phone TEXT,
                email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )""",
            
            # КУБ-устройства
            """CREATE TABLE IF NOT EXISTS kub_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                device_id TEXT UNIQUE NOT NULL,
                device_name TEXT NOT NULL,
                modbus_slave_id INTEGER NOT NULL,
                location TEXT,
                serial_number TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (organization_id) REFERENCES organizations (id)
            )""",
            
            # Пользователи
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )""",
            
            # Роли пользователей в организациях
            """CREATE TABLE IF NOT EXISTS user_organization_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                organization_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (organization_id) REFERENCES organizations (id),
                UNIQUE(user_id, organization_id, role)
            )""",
            
            # Доступ к устройствам
            """CREATE TABLE IF NOT EXISTS user_device_access (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                device_id INTEGER NOT NULL,
                access_level TEXT NOT NULL,
                granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (device_id) REFERENCES kub_devices (id)
            )""",
            
            # Аудит доступа
            """CREATE TABLE IF NOT EXISTS device_access_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                device_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                success INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (device_id) REFERENCES kub_devices (id)
            )""",
            
            # Представление для удобного доступа
            """CREATE VIEW IF NOT EXISTS user_device_permissions AS
            SELECT DISTINCT
                u.telegram_id,
                kd.device_id,
                kd.device_name,
                kd.modbus_slave_id,
                kd.location,
                o.name as organization_name,
                COALESCE(uda.access_level, 'read') as access_level
            FROM users u
            JOIN user_organization_roles uor ON u.id = uor.user_id
            JOIN organizations o ON uor.organization_id = o.id
            JOIN kub_devices kd ON o.id = kd.organization_id
            LEFT JOIN user_device_access uda ON u.id = uda.user_id AND kd.id = uda.device_id AND uda.is_active = 1
            WHERE u.is_active = 1 AND uor.is_active = 1 AND o.is_active = 1 AND kd.is_active = 1"""
        ]
        
        try:
            with sqlite3.connect(self.db_file) as conn:
                for sql in sql_commands:
                    conn.execute(sql)
                
                # Добавляем демо-данные
                self._insert_demo_data(conn)
                
                logger.info("✅ Multi-tenant база данных создана")
                
        except Exception as e:
            logger.error(f"❌ Ошибка создания базы данных: {e}")
            raise
    
    def _insert_demo_data(self, conn):
        """Вставка демонстрационных данных"""
        try:
            # Организации
            conn.executemany("""
                INSERT OR IGNORE INTO organizations (name, code, description, contact_person, phone) VALUES (?, ?, ?, ?, ?)
            """, [
                ('Ферма Иванова', 'IVANOV_FARM', 'Птицеводческое хозяйство', 'Иванов И.И.', '+7-900-123-45-67'),
                ('Агрохолдинг Сибирь', 'AGRO_SIBERIA', 'Крупное агропредприятие', 'Петров П.П.', '+7-900-234-56-78'),
                ('Тепличный комплекс Юг', 'GREENHOUSE_SOUTH', 'Тепличное хозяйство', 'Сидорова С.С.', '+7-900-345-67-89')
            ])
            
            # Устройства
            conn.executemany("""
                INSERT OR IGNORE INTO kub_devices (organization_id, device_id, device_name, modbus_slave_id, location, serial_number) VALUES (?, ?, ?, ?, ?, ?)
            """, [
                (1, 'IVANOV_KUB_01', 'Птичник №1', 1, 'Основной корпус', 'KUB1063-2024-001'),
                (1, 'IVANOV_KUB_02', 'Птичник №2', 2, 'Дополнительный корпус', 'KUB1063-2024-002'),
                (2, 'AGRO_KUB_A1', 'Инкубатор А1', 3, 'Цех А', 'KUB1063-2024-003'),
                (2, 'AGRO_KUB_A2', 'Инкубатор А2', 4, 'Цех А', 'KUB1063-2024-004'),
                (3, 'GREEN_KUB_01', 'Теплица №1', 5, 'Блок 1', 'KUB1063-2024-005')
            ])
            
            logger.info("✅ Демонстрационные данные добавлены")
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка добавления демо-данных: {e}")
    
    # =======================================================================
    # ОСНОВНЫЕ МЕТОДЫ ДОСТУПА
    # =======================================================================
    
    def get_user_devices(self, telegram_id: int) -> List[Device]:
        """Получить все устройства, доступные пользователю"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT device_id, device_name, modbus_slave_id, location, organization_name, access_level
                    FROM user_device_permissions 
                    WHERE telegram_id = ?
                    ORDER BY organization_name, device_name
                """, (telegram_id,))
                
                devices = []
                for row in cursor.fetchall():
                    devices.append(Device(
                        device_id=row['device_id'],
                        device_name=row['device_name'],
                        modbus_slave_id=row['modbus_slave_id'],
                        organization_name=row['organization_name'],
                        location=row['location'],
                        access_level=row['access_level']
                    ))
                
                return devices
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения устройств пользователя {telegram_id}: {e}")
            return []
    
    def check_device_access(self, telegram_id: int, device_id: str, required_access: str = "read") -> bool:
        """Проверить доступ пользователя к конкретному устройству"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.execute("""
                    SELECT access_level 
                    FROM user_device_permissions 
                    WHERE telegram_id = ? AND device_id = ?
                """, (telegram_id, device_id))
                
                result = cursor.fetchone()
                if not result:
                    return False
                
                user_access = result[0]
                
                # Иерархия доступа: admin > write > read
                access_hierarchy = {'read': 1, 'write': 2, 'admin': 3}
                
                user_level = access_hierarchy.get(user_access, 0)
                required_level = access_hierarchy.get(required_access, 0)
                
                return user_level >= required_level
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки доступа {telegram_id} к {device_id}: {e}")
            return False
    
    def get_device_by_slave_id(self, modbus_slave_id: int) -> Optional[Dict[str, Any]]:
        """Получить информацию об устройстве по Modbus Slave ID"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT kd.*, o.name as organization_name 
                    FROM kub_devices kd
                    JOIN organizations o ON kd.organization_id = o.id
                    WHERE kd.modbus_slave_id = ? AND kd.is_active = 1
                """, (modbus_slave_id,))
                
                result = cursor.fetchone()
                return dict(result) if result else None
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения устройства по Slave ID {modbus_slave_id}: {e}")
            return None
    
    def log_device_access(self, telegram_id: int, device_id: str, action: str, 
                         success: bool, details: str = None):
        """Логирование доступа к устройству"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                # Получаем user_id и device_internal_id
                cursor = conn.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
                user_result = cursor.fetchone()
                if not user_result:
                    return
                
                cursor = conn.execute("SELECT id FROM kub_devices WHERE device_id = ?", (device_id,))
                device_result = cursor.fetchone()
                if not device_result:
                    return
                
                conn.execute("""
                    INSERT INTO device_access_log (user_id, device_id, action, details, success)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_result[0], device_result[0], action, details, success))
                
        except Exception as e:
            logger.error(f"❌ Ошибка логирования доступа: {e}")
    
    # =======================================================================
    # МЕТОДЫ УПРАВЛЕНИЯ ОРГАНИЗАЦИЯМИ И ПОЛЬЗОВАТЕЛЯМИ
    # =======================================================================
    
    def register_user(self, telegram_id: int, username: str = None, 
                     first_name: str = None, last_name: str = None) -> bool:
        """Регистрация пользователя в multi-tenant системе"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO users (telegram_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                """, (telegram_id, username, first_name, last_name))
                
                logger.info(f"👤 Пользователь {telegram_id} зарегистрирован в multi-tenant системе")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка регистрации пользователя {telegram_id}: {e}")
            return False
    
    def add_user_to_organization(self, telegram_id: int, organization_code: str, 
                                role: str = "operator") -> bool:
        """Добавить пользователя в организацию"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                # Получаем ID пользователя и организации
                cursor = conn.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
                user_result = cursor.fetchone()
                if not user_result:
                    return False
                
                cursor = conn.execute("SELECT id FROM organizations WHERE code = ?", (organization_code,))
                org_result = cursor.fetchone()
                if not org_result:
                    return False
                
                conn.execute("""
                    INSERT OR REPLACE INTO user_organization_roles (user_id, organization_id, role)
                    VALUES (?, ?, ?)
                """, (user_result[0], org_result[0], role))
                
                logger.info(f"🏢 Пользователь {telegram_id} добавлен в {organization_code} с ролью {role}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка добавления пользователя в организацию: {e}")
            return False
    
    def get_user_organizations(self, telegram_id: int) -> List[Dict[str, Any]]:
        """Получить организации пользователя"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT o.name, o.code, o.description, uor.role
                    FROM organizations o
                    JOIN user_organization_roles uor ON o.id = uor.organization_id
                    JOIN users u ON uor.user_id = u.id
                    WHERE u.telegram_id = ? AND uor.is_active = 1 AND o.is_active = 1
                    ORDER BY o.name
                """, (telegram_id,))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения организаций пользователя {telegram_id}: {e}")
            return []
    
    # =======================================================================
    # ИНТЕГРАЦИЯ С СУЩЕСТВУЮЩЕЙ СИСТЕМОЙ
    # =======================================================================
    
    def filter_data_for_user(self, telegram_id: int, modbus_slave_id: int, 
                            data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Фильтрация данных по правам доступа пользователя"""
        
        # Проверяем доступ к устройству по Modbus Slave ID
        device = self.get_device_by_slave_id(modbus_slave_id)
        if not device:
            logger.warning(f"⚠️ Устройство с Slave ID {modbus_slave_id} не найдено")
            return None
        
        device_id = device['device_id']
        
        if not self.check_device_access(telegram_id, device_id, "read"):
            logger.warning(f"⚠️ Пользователь {telegram_id} не имеет доступа к устройству {device_id}")
            return None
        
        # Логируем доступ
        self.log_device_access(telegram_id, device_id, "read_data", True)
        
        # Добавляем метаданные устройства к данным
        enhanced_data = data.copy()
        enhanced_data.update({
            'device_id': device_id,
            'device_name': device['device_name'],
            'organization_name': device['organization_name'],
            'location': device['location']
        })
        
        return enhanced_data
    
    def validate_write_command(self, telegram_id: int, modbus_slave_id: int, 
                             register: int, value: Any) -> Tuple[bool, str]:
        """Валидация команды записи по правам доступа"""
        
        device = self.get_device_by_slave_id(modbus_slave_id)
        if not device:
            return False, f"Устройство с Slave ID {modbus_slave_id} не найдено"
        
        device_id = device['device_id']
        
        if not self.check_device_access(telegram_id, device_id, "write"):
            return False, f"У вас нет прав записи для устройства {device['device_name']}"
        
        # Логируем попытку записи
        details = json.dumps({"register": register, "value": value})
        self.log_device_access(telegram_id, device_id, "write_register", True, details)
        
        return True, "Доступ разрешен"

# =============================================================================
# ИНТЕГРАЦИЯ С TELEGRAM BOT
# =============================================================================

class MultiTenantTelegramMixin:
    """Mixin для интеграции multi-tenant функций в Telegram Bot"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mt_manager = MultiTenantManager()
    
    def get_user_device_list_text(self, telegram_id: int) -> str:
        """Форматированный список устройств пользователя для Telegram"""
        devices = self.mt_manager.get_user_devices(telegram_id)
        
        if not devices:
            return "❌ **У вас нет доступа к устройствам**\n\nОбратитесь к администратору для получения доступа."
        
        text = f"🏭 **Ваши устройства ({len(devices)}):**\n\n"
        
        current_org = None
        for device in devices:
            if device.organization_name != current_org:
                current_org = device.organization_name
                text += f"🏢 **{current_org}**\n"
            
            access_icon = {"read": "👁️", "write": "✏️", "admin": "⚙️"}.get(device.access_level, "❓")
            text += f"  {access_icon} `{device.device_id}` - {device.device_name}\n"
            if device.location:
                text += f"    📍 {device.location}\n"
            text += "\n"
        
        return text
    
    def format_device_data_with_context(self, telegram_id: int, modbus_slave_id: int, 
                                       data: Dict[str, Any]) -> str:
        """Форматирование данных с контекстом устройства"""
        
        filtered_data = self.mt_manager.filter_data_for_user(telegram_id, modbus_slave_id, data)
        if not filtered_data:
            return "❌ **Нет доступа к данным устройства**"
        
        # Используем существующую функцию форматирования, но с дополнительным контекстом
        from bot_utils import format_sensor_data
        
        formatted = format_sensor_data(filtered_data)
        
        # Добавляем информацию об устройстве
        device_info = (
            f"🏭 **{filtered_data['organization_name']}**\n"
            f"📦 **{filtered_data['device_name']}**"
        )
        
        if filtered_data.get('location'):
            device_info += f"\n📍 {filtered_data['location']}"
        
        return f"{device_info}\n\n{formatted}"

# =============================================================================
# ТЕСТИРОВАНИЕ МОДУЛЯ
# =============================================================================

def test_multi_tenant_system():
    """Тест multi-tenant системы"""
    print("🧪 Тестирование Multi-Tenant системы")
    print("=" * 50)
    
    try:
        # Создаем тестовую базу
        test_db = "test_multitenant.db"
        if Path(test_db).exists():
            Path(test_db).unlink()
        
        mt = MultiTenantManager(test_db)
        
        # Тест 1: Регистрация пользователя
        print("1. Тест регистрации пользователя...")
        success = mt.register_user(123456789, "test_farmer", "Тест", "Фермер")
        print(f"   Регистрация: {'✅' if success else '❌'}")
        
        # Тест 2: Добавление в организацию
        print("2. Тест добавления в организацию...")
        success = mt.add_user_to_organization(123456789, "IVANOV_FARM", "owner")
        print(f"   Добавление в организацию: {'✅' if success else '❌'}")
        
        # Тест 3: Получение устройств
        print("3. Тест получения устройств...")
        devices = mt.get_user_devices(123456789)
        print(f"   Устройств доступно: {len(devices)}")
        for device in devices:
            print(f"     - {device}")
        
        # Тест 4: Проверка доступа
        print("4. Тест проверки доступа...")
        has_access = mt.check_device_access(123456789, "IVANOV_KUB_01", "read")
        print(f"   Доступ к IVANOV_KUB_01: {'✅' if has_access else '❌'}")
        
        # Тест 5: Проверка чужого устройства
        print("5. Тест доступа к чужому устройству...")
        no_access = mt.check_device_access(123456789, "AGRO_KUB_A1", "read")
        print(f"   Доступ к чужому устройству: {'❌' if not no_access else '⚠️ Неожиданный доступ!'}")
        
        print("\n✅ Все тесты multi-tenant системы пройдены!")
        
        # Удаляем тестовую базу
        Path(test_db).unlink()
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        return False

if __name__ == "__main__":
    test_multi_tenant_system()