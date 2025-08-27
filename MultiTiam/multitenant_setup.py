#!/usr/bin/env python3
"""
Скрипт настройки Multi-Tenant системы CUBE_RS
Автоматическая инициализация базы данных и демонстрационных данных
"""

import os
import sys
import json
import argparse
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from multi_tenant_manager import MultiTenantManager

class MultiTenantSetup:
    """Класс для настройки Multi-Tenant системы"""
    
    def __init__(self, db_file: str = "cube_multitenant.db"):
        self.db_file = db_file
        print(f"🔧 Multi-Tenant Setup для базы: {db_file}")
    
    def setup_demo_farm_scenario(self):
        """Настройка демонстрационного сценария: несколько ферм"""
        print("\n🌾 Настройка демонстрационного сценария ферм...")
        
        # Удаляем существующую базу для чистого старта
        if Path(self.db_file).exists():
            Path(self.db_file).unlink()
            print("🗑️ Старая база данных удалена")
        
        # Создаем менеджер (автоматически создаст базу)
        mt = MultiTenantManager(self.db_file)
        
        # Создаем дополнительные организации
        additional_orgs = [
            {
                "name": "Птицефабрика Север",
                "code": "POULTRY_NORTH", 
                "description": "Крупная птицефабрика на севере региона",
                "contact": "Северов С.С.",
                "phone": "+7-900-111-22-33",
                "email": "admin@poultry-north.ru"
            },
            {
                "name": "Свинокомплекс Восток", 
                "code": "PIG_FARM_EAST",
                "description": "Современный свинокомплекс",
                "contact": "Восточный В.В.",
                "phone": "+7-900-222-33-44", 
                "email": "info@pig-east.ru"
            },
            {
                "name": "Молочная ферма Запад",
                "code": "DAIRY_WEST",
                "description": "Семейная молочная ферма",
                "contact": "Западная З.З.",
                "phone": "+7-900-333-44-55",
                "email": "contact@dairy-west.ru"
            }
        ]
        
        import sqlite3
        with sqlite3.connect(self.db_file) as conn:
            for org in additional_orgs:
                conn.execute("""
                    INSERT INTO organizations (name, code, description, contact_person, phone, email)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (org["name"], org["code"], org["description"], org["contact"], org["phone"], org["email"]))
        
        # Добавляем устройства
        devices = [
            # Птицефабрика Север
            (4, "NORTH_KUB_01", "Инкубаторий №1", 7, "Главный корпус", "KUB1063-2024-007"),
            (4, "NORTH_KUB_02", "Инкубаторий №2", 8, "Главный корпус", "KUB1063-2024-008"), 
            (4, "NORTH_KUB_03", "Брудер №1", 9, "Корпус А", "KUB1063-2024-009"),
            (4, "NORTH_KUB_04", "Брудер №2", 10, "Корпус А", "KUB1063-2024-010"),
            (4, "NORTH_KUB_05", "Откормочник №1", 11, "Корпус Б", "KUB1063-2024-011"),
            
            # Свинокомплекс Восток
            (5, "PIG_KUB_01", "Опорос №1", 12, "Свинарник 1", "KUB1063-2024-012"),
            (5, "PIG_KUB_02", "Опорос №2", 13, "Свинарник 1", "KUB1063-2024-013"),
            (5, "PIG_KUB_03", "Откорм №1", 14, "Свинарник 2", "KUB1063-2024-014"),
            
            # Молочная ферма Запад  
            (6, "DAIRY_KUB_01", "Коровник №1", 15, "Основное здание", "KUB1063-2024-015"),
            (6, "DAIRY_KUB_02", "Телятник", 16, "Дополнительное здание", "KUB1063-2024-016")
        ]
        
        with sqlite3.connect(self.db_file) as conn:
            conn.executemany("""
                INSERT INTO kub_devices (organization_id, device_id, device_name, modbus_slave_id, location, serial_number)
                VALUES (?, ?, ?, ?, ?, ?)
            """, devices)
        
        print(f"✅ Создано {len(additional_orgs)} дополнительных организаций")
        print(f"✅ Добавлено {len(devices)} устройств")
        
        # Создаем тестовых пользователей-фермеров
        test_users = [
            {
                "telegram_id": 111111111,
                "username": "farmer_north", 
                "first_name": "Сергей",
                "last_name": "Северов",
                "email": "sergey@poultry-north.ru",
                "org_code": "POULTRY_NORTH",
                "role": "admin"
            },
            {
                "telegram_id": 222222222,
                "username": "pig_farmer_east",
                "first_name": "Владимир", 
                "last_name": "Восточный",
                "email": "vladimir@pig-east.ru",
                "org_code": "PIG_FARM_EAST", 
                "role": "owner"
            },
            {
                "telegram_id": 333333333,
                "username": "dairy_west",
                "first_name": "Зоя",
                "last_name": "Западная", 
                "email": "zoya@dairy-west.ru",
                "org_code": "DAIRY_WEST",
                "role": "owner"
            },
            {
                "telegram_id": 444444444,
                "username": "operator_north",
                "first_name": "Иван",
                "last_name": "Помощников",
                "email": "ivan@poultry-north.ru", 
                "org_code": "POULTRY_NORTH",
                "role": "operator"
            }
        ]
        
        for user in test_users:
            mt.register_user(
                user["telegram_id"], user["username"],
                user["first_name"], user["last_name"]
            )
            mt.add_user_to_organization(
                user["telegram_id"], user["org_code"], user["role"]
            )
        
        print(f"✅ Создано {len(test_users)} тестовых пользователей")
        
        print("\n📋 ДЕМО-СЦЕНАРИЙ ГОТОВ!")
        self._print_demo_info()
    
    def setup_enterprise_scenario(self):
        """Настройка корпоративного сценария: холдинг с филиалами"""
        print("\n🏢 Настройка корпоративного сценария...")
        
        if Path(self.db_file).exists():
            Path(self.db_file).unlink()
        
        mt = MultiTenantManager(self.db_file)
        
        # Создаем структуру холдинга
        holdings = [
            {
                "name": "АгроХолдинг Центр - Головной офис",
                "code": "AGRO_CENTER_HQ",
                "description": "Управляющая компания холдинга",
                "contact": "Директоров Д.Д.",
                "phone": "+7-495-123-45-67",
                "email": "director@agro-center.ru"
            },
            {
                "name": "АгроХолдинг Центр - Филиал Москва",
                "code": "AGRO_CENTER_MSK", 
                "description": "Московский филиал",
                "contact": "Московский М.М.",
                "phone": "+7-495-234-56-78",
                "email": "moscow@agro-center.ru"
            },
            {
                "name": "АгроХолдинг Центр - Филиал СПб",
                "code": "AGRO_CENTER_SPB",
                "description": "Санкт-Петербургский филиал", 
                "contact": "Петербургский П.П.",
                "phone": "+7-812-345-67-89",
                "email": "spb@agro-center.ru"
            },
            {
                "name": "АгроХолдинг Центр - Филиал Казань",
                "code": "AGRO_CENTER_KZN",
                "description": "Казанский филиал",
                "contact": "Казанский К.К.", 
                "phone": "+7-843-456-78-90",
                "email": "kazan@agro-center.ru"
            }
        ]
        
        import sqlite3
        with sqlite3.connect(self.db_file) as conn:
            for org in holdings:
                conn.execute("""
                    INSERT INTO organizations (name, code, description, contact_person, phone, email)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (org["name"], org["code"], org["description"], org["contact"], org["phone"], org["email"]))
        
        # Добавляем много устройств по филиалам
        devices = []
        device_counter = 1
        
        # Головной офис - системы мониторинга
        for i in range(1, 4):
            devices.append((1, f"HQ_MONITOR_{i:02d}", f"Система мониторинга №{i}", device_counter, "Центр управления", f"KUB1063-2024-{device_counter:03d}"))
            device_counter += 1
        
        # Москва - 15 устройств
        for i in range(1, 16):
            location = f"Корпус {(i-1)//5 + 1}"
            devices.append((2, f"MSK_KUB_{i:02d}", f"Московский КУБ №{i}", device_counter, location, f"KUB1063-2024-{device_counter:03d}"))
            device_counter += 1
        
        # СПб - 12 устройств
        for i in range(1, 13):
            location = f"Здание {(i-1)//4 + 1}"
            devices.append((3, f"SPB_KUB_{i:02d}", f"Питерский КУБ №{i}", device_counter, location, f"KUB1063-2024-{device_counter:03d}"))
            device_counter += 1
        
        # Казань - 8 устройств
        for i in range(1, 9):
            location = f"Цех {(i-1)//3 + 1}"
            devices.append((4, f"KZN_KUB_{i:02d}", f"Казанский КУБ №{i}", device_counter, location, f"KUB1063-2024-{device_counter:03d}"))
            device_counter += 1
        
        with sqlite3.connect(self.db_file) as conn:
            conn.executemany("""
                INSERT INTO kub_devices (organization_id, device_id, device_name, modbus_slave_id, location, serial_number)
                VALUES (?, ?, ?, ?, ?, ?)
            """, devices)
        
        # Создаем корпоративных пользователей
        corporate_users = [
            # Руководство
            (555000001, "ceo_center", "Владимир", "Главный", "AGRO_CENTER_HQ", "owner"),
            (555000002, "cto_center", "Технический", "Директор", "AGRO_CENTER_HQ", "admin"),
            
            # Москва
            (555100001, "director_msk", "Михаил", "Московский", "AGRO_CENTER_MSK", "admin"),
            (555100002, "engineer_msk", "Инженер", "Московский", "AGRO_CENTER_MSK", "operator"), 
            (555100003, "operator_msk_1", "Оператор1", "Московский", "AGRO_CENTER_MSK", "operator"),
            (555100004, "operator_msk_2", "Оператор2", "Московский", "AGRO_CENTER_MSK", "operator"),
            
            # СПб
            (555200001, "director_spb", "Петр", "Петербургский", "AGRO_CENTER_SPB", "admin"),
            (555200002, "engineer_spb", "Инженер", "Питерский", "AGRO_CENTER_SPB", "operator"),
            (555200003, "operator_spb", "Оператор", "Питерский", "AGRO_CENTER_SPB", "operator"),
            
            # Казань
            (555300001, "director_kzn", "Казбек", "Казанский", "AGRO_CENTER_KZN", "admin"),
            (555300002, "operator_kzn", "Оператор", "Казанский", "AGRO_CENTER_KZN", "operator")
        ]
        
        for telegram_id, username, first_name, last_name, org_code, role in corporate_users:
            mt.register_user(telegram_id, username, first_name, last_name)
            mt.add_user_to_organization(telegram_id, org_code, role)
        
        # Добавляем cross-филиальный доступ для руководства
        # CEO видит все
        mt.add_user_to_organization(555000001, "AGRO_CENTER_MSK", "admin")
        mt.add_user_to_organization(555000001, "AGRO_CENTER_SPB", "admin") 
        mt.add_user_to_organization(555000001, "AGRO_CENTER_KZN", "admin")
        
        # CTO тоже видит все
        mt.add_user_to_organization(555000002, "AGRO_CENTER_MSK", "operator")
        mt.add_user_to_organization(555000002, "AGRO_CENTER_SPB", "operator")
        mt.add_user_to_organization(555000002, "AGRO_CENTER_KZN", "operator")
        
        print(f"✅ Создан холдинг с {len(holdings)} филиалами")
        print(f"✅ Добавлено {len(devices)} устройств")
        print(f"✅ Создано {len(corporate_users)} корпоративных пользователей")
        
        print("\n📋 КОРПОРАТИВНЫЙ СЦЕНАРИЙ ГОТОВ!")
        self._print_enterprise_info()
    
    def _print_demo_info(self):
        """Вывод информации о демо-сценарии"""
        print("\n" + "="*60)
        print("🌾 ДЕМОНСТРАЦИОННЫЕ ФЕРМЫ")
        print("="*60)
        print("🏢 Организации:")
        print("  • Ферма Иванова (IVANOV_FARM) - 2 устройства")
        print("  • Агрохолдинг Сибирь (AGRO_SIBERIA) - 3 устройства") 
        print("  • Тепличный комплекс Юг (GREENHOUSE_SOUTH) - 1 устройство")
        print("  • Птицефабрика Север (POULTRY_NORTH) - 5 устройств")
        print("  • Свинокомплекс Восток (PIG_FARM_EAST) - 3 устройства")
        print("  • Молочная ферма Запад (DAIRY_WEST) - 2 устройства")
        print()
        print("👥 Тестовые пользователи:")
        print("  • 111111111 - Сергей Северов (admin в POULTRY_NORTH)")
        print("  • 222222222 - Владимир Восточный (owner в PIG_FARM_EAST)")  
        print("  • 333333333 - Зоя Западная (owner в DAIRY_WEST)")
        print("  • 444444444 - Иван Помощников (operator в POULTRY_NORTH)")
        print()
        print("🔧 Для тестирования используйте:")
        print("  python multitenant_admin.py user list")
        print("  python multitenant_admin.py device list")
        print("="*60)
    
    def _print_enterprise_info(self):
        """Вывод информации о корпоративном сценарии"""
        print("\n" + "="*60)
        print("🏢 КОРПОРАТИВНЫЙ ХОЛДИНГ")
        print("="*60)
        print("🏢 Структура холдинга:")
        print("  • Головной офис (AGRO_CENTER_HQ) - 3 устройства")
        print("  • Филиал Москва (AGRO_CENTER_MSK) - 15 устройств")
        print("  • Филиал СПб (AGRO_CENTER_SPB) - 12 устройств") 
        print("  • Филиал Казань (AGRO_CENTER_KZN) - 8 устройств")
        print()
        print("👥 Корпоративные пользователи:")
        print("  • 555000001 - CEO (доступ ко всем филиалам)")
        print("  • 555000002 - CTO (техническое управление)")
        print("  • 555100001 - Директор Москвы") 
        print("  • 555200001 - Директор СПб")
        print("  • 555300001 - Директор Казани")
        print("  • + операторы по филиалам")
        print()
        print("🔧 Всего устройств: 38")
        print("🔧 Всего пользователей: 11")
        print("="*60)
    
    def create_production_config(self):
        """Создание продакшн конфигурации"""
        print("\n🏭 Создание продакшн конфигурации...")
        
        config = {
            "multitenant": {
                "enabled": True,
                "database": "cube_multitenant.db",
                "audit_enabled": True,
                "session_timeout": 3600,
                "max_devices_per_org": 50,
                "max_users_per_org": 20
            },
            "security": {
                "require_device_access_approval": True,
                "log_all_operations": True,
                "rate_limiting": {
                    "enabled": True,
                    "requests_per_hour": 100
                }
            },
            "notifications": {
                "new_user_registration": True,
                "device_access_requests": True,
                "critical_alarms": True
            }
        }
        
        config_file = "config/multitenant_production.json"
        os.makedirs("config", exist_ok=True)
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Продакшн конфигурация создана: {config_file}")

def main():
    """Основная функция настройки"""
    parser = argparse.ArgumentParser(description="Multi-Tenant Setup для CUBE_RS")
    
    parser.add_argument('--db', default='cube_multitenant.db', help='Путь к базе данных')
    parser.add_argument('--scenario', choices=['demo', 'enterprise', 'custom'], 
                       default='demo', help='Сценарий настройки')
    parser.add_argument('--config', action='store_true', help='Создать продакшн конфигурацию')
    
    args = parser.parse_args()
    
    setup = MultiTenantSetup(args.db)
    
    try:
        if args.config:
            setup.create_production_config()
        
        if args.scenario == 'demo':
            setup.setup_demo_farm_scenario()
        elif args.scenario == 'enterprise':
            setup.setup_enterprise_scenario()
        elif args.scenario == 'custom':
            print("📝 Для custom сценария используйте multitenant_admin.py")
            print("   Пример: python multitenant_admin.py org create 'Моя Ферма' MY_FARM")
        
        print("\n🎉 Настройка завершена!")
        print("\n📖 Следующие шаги:")
        print("  1. Проверьте настройки: python multitenant_admin.py report")
        print("  2. Запустите Telegram Bot: python multitenant_telegram_bot.py")
        print("  3. Протестируйте доступ пользователей")
        
    except KeyboardInterrupt:
        print("\n❌ Настройка отменена")
    except Exception as e:
        print(f"❌ Ошибка настройки: {e}")

if __name__ == "__main__":
    main()