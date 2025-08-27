#!/usr/bin/env python3
"""
Административный интерфейс для управления Multi-Tenant системой CUBE_RS
Управление пользователями, организациями и доступами к устройствам
"""

import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any
from multi_tenant_manager import MultiTenantManager

class MultiTenantAdmin:
    """Административный интерфейс для Multi-Tenant системы"""
    
    def __init__(self, db_file: str = "cube_multitenant.db"):
        self.mt_manager = MultiTenantManager(db_file)
        print(f"🔧 Multi-Tenant Admin инициализирован с базой {db_file}")
    
    # =======================================================================
    # УПРАВЛЕНИЕ ОРГАНИЗАЦИЯМИ
    # =======================================================================
    
    def create_organization(self, name: str, code: str, description: str = None, 
                          contact_person: str = None, phone: str = None, email: str = None):
        """Создать новую организацию"""
        try:
            import sqlite3
            with sqlite3.connect(self.mt_manager.db_file) as conn:
                conn.execute("""
                    INSERT INTO organizations (name, code, description, contact_person, phone, email)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (name, code, description, contact_person, phone, email))
                
                print(f"✅ Организация '{name}' ({code}) создана")
                return True
                
        except sqlite3.IntegrityError:
            print(f"❌ Организация с кодом '{code}' уже существует")
            return False
        except Exception as e:
            print(f"❌ Ошибка создания организации: {e}")
            return False
    
    def list_organizations(self):
        """Показать все организации"""
        try:
            import sqlite3
            with sqlite3.connect(self.mt_manager.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT o.*, COUNT(kd.id) as device_count, COUNT(DISTINCT uor.user_id) as user_count
                    FROM organizations o
                    LEFT JOIN kub_devices kd ON o.id = kd.organization_id AND kd.is_active = 1
                    LEFT JOIN user_organization_roles uor ON o.id = uor.organization_id AND uor.is_active = 1
                    WHERE o.is_active = 1
                    GROUP BY o.id
                    ORDER BY o.name
                """)
                
                organizations = cursor.fetchall()
                
                if not organizations:
                    print("📭 Организации не найдены")
                    return
                
                print("\n🏢 ОРГАНИЗАЦИИ:")
                print("=" * 80)
                print(f"{'ID':<5} {'Код':<15} {'Название':<25} {'Устройств':<10} {'Пользователей':<12} {'Контакт'}")
                print("=" * 80)
                
                for org in organizations:
                    print(f"{org['id']:<5} {org['code']:<15} {org['name']:<25} {org['device_count']:<10} {org['user_count']:<12} {org['contact_person'] or '-'}")
                
                print("=" * 80)
                
        except Exception as e:
            print(f"❌ Ошибка получения организаций: {e}")
    
    # =======================================================================
    # УПРАВЛЕНИЕ УСТРОЙСТВАМИ
    # =======================================================================
    
    def add_device(self, organization_code: str, device_id: str, device_name: str, 
                   modbus_slave_id: int, location: str = None, serial_number: str = None):
        """Добавить устройство в организацию"""
        try:
            import sqlite3
            with sqlite3.connect(self.mt_manager.db_file) as conn:
                # Получаем ID организации
                cursor = conn.execute("SELECT id FROM organizations WHERE code = ?", (organization_code,))
                org_result = cursor.fetchone()
                if not org_result:
                    print(f"❌ Организация '{organization_code}' не найдена")
                    return False
                
                org_id = org_result[0]
                
                conn.execute("""
                    INSERT INTO kub_devices (organization_id, device_id, device_name, modbus_slave_id, location, serial_number)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (org_id, device_id, device_name, modbus_slave_id, location, serial_number))
                
                print(f"✅ Устройство '{device_name}' ({device_id}) добавлено в '{organization_code}'")
                print(f"   Modbus Slave ID: {modbus_slave_id}")
                return True
                
        except sqlite3.IntegrityError as e:
            if "device_id" in str(e):
                print(f"❌ Устройство с ID '{device_id}' уже существует")
            elif "modbus_slave_id" in str(e):
                print(f"❌ Устройство с Modbus Slave ID {modbus_slave_id} уже существует")
            else:
                print(f"❌ Ошибка уникальности: {e}")
            return False
        except Exception as e:
            print(f"❌ Ошибка добавления устройства: {e}")
            return False
    
    def list_devices(self, organization_code: str = None):
        """Показать устройства (всех организаций или конкретной)"""
        try:
            import sqlite3
            with sqlite3.connect(self.mt_manager.db_file) as conn:
                conn.row_factory = sqlite3.Row
                
                if organization_code:
                    cursor = conn.execute("""
                        SELECT kd.*, o.name as org_name, o.code as org_code
                        FROM kub_devices kd
                        JOIN organizations o ON kd.organization_id = o.id
                        WHERE o.code = ? AND kd.is_active = 1
                        ORDER BY kd.device_name
                    """, (organization_code,))
                else:
                    cursor = conn.execute("""
                        SELECT kd.*, o.name as org_name, o.code as org_code
                        FROM kub_devices kd
                        JOIN organizations o ON kd.organization_id = o.id
                        WHERE kd.is_active = 1
                        ORDER BY o.name, kd.device_name
                    """)
                
                devices = cursor.fetchall()
                
                if not devices:
                    if organization_code:
                        print(f"📭 В организации '{organization_code}' нет устройств")
                    else:
                        print("📭 Устройства не найдены")
                    return
                
                title = f"УСТРОЙСТВА ОРГАНИЗАЦИИ '{organization_code}'" if organization_code else "ВСЕ УСТРОЙСТВА"
                print(f"\n📦 {title}:")
                print("=" * 100)
                print(f"{'ID':<15} {'Название':<20} {'Организация':<20} {'Slave ID':<8} {'Местоположение':<15} {'S/N'}")
                print("=" * 100)
                
                for device in devices:
                    print(f"{device['device_id']:<15} {device['device_name']:<20} {device['org_code']:<20} {device['modbus_slave_id']:<8} {device['location'] or '-':<15} {device['serial_number'] or '-'}")
                
                print("=" * 100)
                
        except Exception as e:
            print(f"❌ Ошибка получения устройств: {e}")
    
    # =======================================================================
    # УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ
    # =======================================================================
    
    def add_user_to_organization(self, telegram_id: int, organization_code: str, role: str = "operator"):
        """Добавить пользователя в организацию"""
        
        # Сначала регистрируем пользователя если его нет
        self.mt_manager.register_user(telegram_id)
        
        success = self.mt_manager.add_user_to_organization(telegram_id, organization_code, role)
        
        if success:
            print(f"✅ Пользователь {telegram_id} добавлен в '{organization_code}' с ролью '{role}'")
        else:
            print(f"❌ Ошибка добавления пользователя {telegram_id} в '{organization_code}'")
        
        return success
    
    def grant_device_access(self, telegram_id: int, device_id: str, access_level: str = "read"):
        """Предоставить пользователю доступ к конкретному устройству"""
        try:
            import sqlite3
            with sqlite3.connect(self.mt_manager.db_file) as conn:
                # Получаем ID пользователя и устройства
                cursor = conn.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
                user_result = cursor.fetchone()
                if not user_result:
                    print(f"❌ Пользователь {telegram_id} не найден")
                    return False
                
                cursor = conn.execute("SELECT id FROM kub_devices WHERE device_id = ?", (device_id,))
                device_result = cursor.fetchone()
                if not device_result:
                    print(f"❌ Устройство '{device_id}' не найдено")
                    return False
                
                conn.execute("""
                    INSERT OR REPLACE INTO user_device_access (user_id, device_id, access_level)
                    VALUES (?, ?, ?)
                """, (user_result[0], device_result[0], access_level))
                
                print(f"✅ Пользователю {telegram_id} предоставлен доступ '{access_level}' к устройству '{device_id}'")
                return True
                
        except Exception as e:
            print(f"❌ Ошибка предоставления доступа: {e}")
            return False
    
    def list_user_access(self, telegram_id: int = None):
        """Показать доступы пользователей"""
        try:
            import sqlite3
            with sqlite3.connect(self.mt_manager.db_file) as conn:
                conn.row_factory = sqlite3.Row
                
                if telegram_id:
                    # Показать доступы конкретного пользователя
                    cursor = conn.execute("""
                        SELECT u.telegram_id, u.username, u.first_name, u.last_name,
                               o.name as org_name, o.code as org_code, uor.role,
                               kd.device_id, kd.device_name, COALESCE(uda.access_level, 'read') as access_level
                        FROM users u
                        JOIN user_organization_roles uor ON u.id = uor.user_id
                        JOIN organizations o ON uor.organization_id = o.id
                        JOIN kub_devices kd ON o.id = kd.organization_id
                        LEFT JOIN user_device_access uda ON u.id = uda.user_id AND kd.id = uda.device_id AND uda.is_active = 1
                        WHERE u.telegram_id = ? AND u.is_active = 1 AND uor.is_active = 1 AND o.is_active = 1 AND kd.is_active = 1
                        ORDER BY o.name, kd.device_name
                    """, (telegram_id,))
                    
                    rows = cursor.fetchall()
                    
                    if not rows:
                        print(f"📭 Пользователь {telegram_id} не найден или не имеет доступов")
                        return
                    
                    user_info = rows[0]
                    print(f"\n👤 ДОСТУПЫ ПОЛЬЗОВАТЕЛЯ {telegram_id}:")
                    print(f"Имя: {user_info['first_name']} {user_info['last_name']} (@{user_info['username'] or 'не указан'})")
                    print("=" * 80)
                    print(f"{'Организация':<20} {'Роль':<10} {'Устройство':<20} {'Доступ':<10}")
                    print("=" * 80)
                    
                    for row in rows:
                        print(f"{row['org_code']:<20} {row['role']:<10} {row['device_id']:<20} {row['access_level']:<10}")
                    
                    print("=" * 80)
                    
                else:
                    # Показать всех пользователей
                    cursor = conn.execute("""
                        SELECT u.telegram_id, u.username, u.first_name, u.last_name,
                               COUNT(DISTINCT uor.organization_id) as org_count,
                               COUNT(DISTINCT kd.id) as device_count,
                               GROUP_CONCAT(DISTINCT o.code) as organizations
                        FROM users u
                        LEFT JOIN user_organization_roles uor ON u.id = uor.user_id AND uor.is_active = 1
                        LEFT JOIN organizations o ON uor.organization_id = o.id AND o.is_active = 1
                        LEFT JOIN kub_devices kd ON o.id = kd.organization_id AND kd.is_active = 1
                        WHERE u.is_active = 1
                        GROUP BY u.id
                        ORDER BY u.telegram_id
                    """)
                    
                    users = cursor.fetchall()
                    
                    if not users:
                        print("📭 Пользователи не найдены")
                        return
                    
                    print("\n👥 ВСЕ ПОЛЬЗОВАТЕЛИ:")
                    print("=" * 100)
                    print(f"{'Telegram ID':<12} {'Имя':<20} {'Username':<15} {'Орг-ций':<8} {'Устройств':<10} {'Организации'}")
                    print("=" * 100)
                    
                    for user in users:
                        full_name = f"{user['first_name'] or ''} {user['last_name'] or ''}".strip() or "Не указано"
                        username = f"@{user['username']}" if user['username'] else "-"
                        organizations = user['organizations'] or "Нет доступа"
                        
                        print(f"{user['telegram_id']:<12} {full_name[:19]:<20} {username[:14]:<15} {user['org_count']:<8} {user['device_count']:<10} {organizations}")
                    
                    print("=" * 100)
                
        except Exception as e:
            print(f"❌ Ошибка получения доступов: {e}")
    
    def revoke_access(self, telegram_id: int, organization_code: str = None, device_id: str = None):
        """Отозвать доступ пользователя"""
        try:
            import sqlite3
            with sqlite3.connect(self.mt_manager.db_file) as conn:
                if device_id:
                    # Отзываем доступ к конкретному устройству
                    cursor = conn.execute("""
                        UPDATE user_device_access 
                        SET is_active = 0 
                        WHERE user_id = (SELECT id FROM users WHERE telegram_id = ?)
                        AND device_id = (SELECT id FROM kub_devices WHERE device_id = ?)
                    """, (telegram_id, device_id))
                    
                    if cursor.rowcount > 0:
                        print(f"✅ Доступ пользователя {telegram_id} к устройству '{device_id}' отозван")
                    else:
                        print(f"❌ Доступ не найден")
                        
                elif organization_code:
                    # Отзываем доступ ко всей организации
                    cursor = conn.execute("""
                        UPDATE user_organization_roles 
                        SET is_active = 0 
                        WHERE user_id = (SELECT id FROM users WHERE telegram_id = ?)
                        AND organization_id = (SELECT id FROM organizations WHERE code = ?)
                    """, (telegram_id, organization_code))
                    
                    if cursor.rowcount > 0:
                        print(f"✅ Доступ пользователя {telegram_id} к организации '{organization_code}' отозван")
                    else:
                        print(f"❌ Доступ не найден")
                        
                else:
                    print("❌ Укажите organization_code или device_id для отзыва доступа")
                    return False
                
                return cursor.rowcount > 0
                
        except Exception as e:
            print(f"❌ Ошибка отзыва доступа: {e}")
            return False
    
    # =======================================================================
    # ОТЧЕТЫ И АНАЛИТИКА
    # =======================================================================
    
    def generate_access_report(self):
        """Сгенерировать отчет по доступам"""
        try:
            import sqlite3
            with sqlite3.connect(self.mt_manager.db_file) as conn:
                conn.row_factory = sqlite3.Row
                
                print("\n📊 ОТЧЕТ ПО ДОСТУПАМ")
                print("=" * 60)
                
                # Статистика по организациям
                cursor = conn.execute("""
                    SELECT o.name, o.code,
                           COUNT(DISTINCT kd.id) as device_count,
                           COUNT(DISTINCT uor.user_id) as user_count
                    FROM organizations o
                    LEFT JOIN kub_devices kd ON o.id = kd.organization_id AND kd.is_active = 1
                    LEFT JOIN user_organization_roles uor ON o.id = uor.organization_id AND uor.is_active = 1
                    WHERE o.is_active = 1
                    GROUP BY o.id
                    ORDER BY device_count DESC, user_count DESC
                """)
                
                orgs = cursor.fetchall()
                
                print("\n🏢 Статистика по организациям:")
                for org in orgs:
                    print(f"  • {org['name']} ({org['code']}): {org['device_count']} устройств, {org['user_count']} пользователей")
                
                # Статистика по пользователям
                cursor = conn.execute("""
                    SELECT COUNT(*) as total_users,
                           COUNT(CASE WHEN uor.id IS NOT NULL THEN 1 END) as users_with_access
                    FROM users u
                    LEFT JOIN user_organization_roles uor ON u.id = uor.user_id AND uor.is_active = 1
                    WHERE u.is_active = 1
                """)
                
                user_stats = cursor.fetchone()
                
                print(f"\n👥 Статистика по пользователям:")
                print(f"  • Всего пользователей: {user_stats['total_users']}")
                print(f"  • С доступом к организациям: {user_stats['users_with_access']}")
                print(f"  • Без доступа: {user_stats['total_users'] - user_stats['users_with_access']}")
                
                # Последние активности
                cursor = conn.execute("""
                    SELECT u.telegram_id, u.first_name, u.last_name, 
                           kd.device_id, dal.action, dal.timestamp, dal.success
                    FROM device_access_log dal
                    JOIN users u ON dal.user_id = u.id
                    JOIN kub_devices kd ON dal.device_id = kd.id
                    ORDER BY dal.timestamp DESC
                    LIMIT 10
                """)
                
                activities = cursor.fetchall()
                
                if activities:
                    print(f"\n📝 Последние активности:")
                    for activity in activities:
                        user_name = f"{activity['first_name']} {activity['last_name']}".strip() or str(activity['telegram_id'])
                        status = "✅" if activity['success'] else "❌"
                        print(f"  {status} {activity['timestamp'][:16]} - {user_name}: {activity['action']} на {activity['device_id']}")
                
                print("=" * 60)
                
        except Exception as e:
            print(f"❌ Ошибка генерации отчета: {e}")

# =============================================================================
# КОМАНДНАЯ СТРОКА
# =============================================================================

def main():
    """Основная функция командной строки"""
    parser = argparse.ArgumentParser(description="Multi-Tenant Admin для CUBE_RS")
    
    # Общие параметры
    parser.add_argument('--db', default='cube_multitenant.db', help='Путь к базе данных')
    
    subparsers = parser.add_subparsers(dest='command', help='Доступные команды')
    
    # Команды для организаций
    org_parser = subparsers.add_parser('org', help='Управление организациями')
    org_subparsers = org_parser.add_subparsers(dest='org_action')
    
    # org create
    create_org_parser = org_subparsers.add_parser('create', help='Создать организацию')
    create_org_parser.add_argument('name', help='Название организации')
    create_org_parser.add_argument('code', help='Код организации')
    create_org_parser.add_argument('--description', help='Описание')
    create_org_parser.add_argument('--contact', help='Контактное лицо')
    create_org_parser.add_argument('--phone', help='Телефон')
    create_org_parser.add_argument('--email', help='Email')
    
    # org list
    org_subparsers.add_parser('list', help='Показать организации')
    
    # Команды для устройств
    device_parser = subparsers.add_parser('device', help='Управление устройствами')
    device_subparsers = device_parser.add_subparsers(dest='device_action')
    
    # device add
    add_device_parser = device_subparsers.add_parser('add', help='Добавить устройство')
    add_device_parser.add_argument('org_code', help='Код организации')
    add_device_parser.add_argument('device_id', help='ID устройства')
    add_device_parser.add_argument('device_name', help='Название устройства')
    add_device_parser.add_argument('modbus_id', type=int, help='Modbus Slave ID')
    add_device_parser.add_argument('--location', help='Местоположение')
    add_device_parser.add_argument('--serial', help='Серийный номер')
    
    # device list
    list_device_parser = device_subparsers.add_parser('list', help='Показать устройства')
    list_device_parser.add_argument('--org', help='Код организации')
    
    # Команды для пользователей
    user_parser = subparsers.add_parser('user', help='Управление пользователями')
    user_subparsers = user_parser.add_subparsers(dest='user_action')
    
    # user add
    add_user_parser = user_subparsers.add_parser('add', help='Добавить пользователя в организацию')
    add_user_parser.add_argument('telegram_id', type=int, help='Telegram ID пользователя')
    add_user_parser.add_argument('org_code', help='Код организации')
    add_user_parser.add_argument('--role', default='operator', choices=['owner', 'admin', 'operator', 'viewer'], help='Роль')
    
    # user grant
    grant_parser = user_subparsers.add_parser('grant', help='Предоставить доступ к устройству')
    grant_parser.add_argument('telegram_id', type=int, help='Telegram ID пользователя')
    grant_parser.add_argument('device_id', help='ID устройства')
    grant_parser.add_argument('--level', default='read', choices=['read', 'write', 'admin'], help='Уровень доступа')
    
    # user list
    list_user_parser = user_subparsers.add_parser('list', help='Показать пользователей')
    list_user_parser.add_argument('--telegram-id', type=int, help='Показать конкретного пользователя')
    
    # user revoke
    revoke_parser = user_subparsers.add_parser('revoke', help='Отозвать доступ')
    revoke_parser.add_argument('telegram_id', type=int, help='Telegram ID пользователя')
    revoke_parser.add_argument('--org', help='Код организации')
    revoke_parser.add_argument('--device', help='ID устройства')
    
    # Отчеты
    subparsers.add_parser('report', help='Сгенерировать отчет')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    admin = MultiTenantAdmin(args.db)
    
    try:
        # Выполняем команды
        if args.command == 'org':
            if args.org_action == 'create':
                admin.create_organization(
                    args.name, args.code, args.description,
                    args.contact, args.phone, args.email
                )
            elif args.org_action == 'list':
                admin.list_organizations()
                
        elif args.command == 'device':
            if args.device_action == 'add':
                admin.add_device(
                    args.org_code, args.device_id, args.device_name,
                    args.modbus_id, args.location, args.serial
                )
            elif args.device_action == 'list':
                admin.list_devices(args.org)
                
        elif args.command == 'user':
            if args.user_action == 'add':
                admin.add_user_to_organization(args.telegram_id, args.org_code, args.role)
            elif args.user_action == 'grant':
                admin.grant_device_access(args.telegram_id, args.device_id, args.level)
            elif args.user_action == 'list':
                admin.list_user_access(args.telegram_id)
            elif args.user_action == 'revoke':
                admin.revoke_access(args.telegram_id, args.org, args.device)
                
        elif args.command == 'report':
            admin.generate_access_report()
            
    except KeyboardInterrupt:
        print("\n❌ Операция отменена")
    except Exception as e:
        print(f"❌ Ошибка выполнения команды: {e}")

if __name__ == "__main__":
    main()