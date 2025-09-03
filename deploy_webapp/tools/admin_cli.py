#!/usr/bin/env python3
"""
CLI утилита для администрирования CUBE_RS
Управление пользователями, устройствами и ключами авторизации
"""
import sys
import os
import argparse
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from web_app.rbac_system import get_rbac_system, Permission
from web_app.device_registry import get_device_registry

def create_user(args):
    """Создание нового пользователя"""
    rbac = get_rbac_system()
    
    # Получаем роль по имени
    role_obj = rbac.get_role_by_name(args.role) if args.role else None
    roles = [role_obj.role_id] if role_obj else []
    
    try:
        user_id = rbac.create_user(
            username=args.username,
            email=args.email,
            full_name=args.full_name,
            password=args.password,
            roles=roles,
            is_admin=args.admin
        )
        print(f"✅ Пользователь создан успешно!")
        print(f"   ID: {user_id}")
        print(f"   Username: {args.username}")
        print(f"   Email: {args.email}")
        print(f"   Роль: {args.role or 'Нет'}")
        print(f"   Администратор: {'Да' if args.admin else 'Нет'}")
        
    except Exception as e:
        print(f"❌ Ошибка создания пользователя: {e}")
        return False
    
    return True

def list_users(args):
    """Список пользователей"""
    rbac = get_rbac_system()
    
    try:
        stats = rbac.get_rbac_stats()
        print(f"👥 Пользователи системы:")
        print(f"   Всего активных: {stats.get('active_users', 0)}")
        print(f"   Администраторов: {stats.get('admin_users', 0)}")
        print(f"   Ролей в системе: {stats.get('total_roles', 0)}")
        
    except Exception as e:
        print(f"❌ Ошибка получения пользователей: {e}")
        return False
    
    return True

def create_device_key(args):
    """Создание ключа для регистрации устройства"""
    registry = get_device_registry()
    
    try:
        auth_key = registry.generate_auth_key(
            expires_hours=args.expires,
            max_usage=args.max_usage,
            is_reusable=args.reusable,
            is_ephemeral=args.ephemeral,
            tags=args.tags,
            created_by=args.created_by
        )
        
        print(f"🔑 Ключ авторизации создан успешно!")
        print(f"   Ключ: {auth_key}")
        print(f"   Срок действия: {args.expires} часов")
        print(f"   Максимальное использование: {args.max_usage if args.max_usage > 0 else 'Неограниченно'}")
        print(f"   Переиспользуемый: {'Да' if args.reusable else 'Нет'}")
        print(f"   Теги: {', '.join(args.tags)}")
        print()
        print("📋 Инструкция для устройства:")
        print(f"   Используйте этот ключ для регистрации устройства в системе")
        print(f"   tailscale up --authkey={auth_key}")
        
    except Exception as e:
        print(f"❌ Ошибка создания ключа: {e}")
        return False
    
    return True

def list_pending_registrations(args):
    """Список ожидающих одобрения регистраций"""
    registry = get_device_registry()
    
    try:
        requests = registry.get_pending_registration_requests()
        
        if not requests:
            print("📝 Нет ожидающих одобрения запросов регистрации")
            return True
        
        print(f"📝 Ожидающие одобрения запросы ({len(requests)}):")
        print()
        
        for req in requests:
            print(f"🔸 Request ID: {req.request_id}")
            print(f"   Hostname: {req.device_hostname}")
            print(f"   Тип устройства: {req.device_type}")
            print(f"   Tailscale IP: {req.tailscale_ip or 'Не указан'}")
            print(f"   Время запроса: {req.requested_time}")
            print(f"   Информация: {req.device_info}")
            print()
        
        print(f"💡 Для одобрения используйте:")
        print(f"   python tools/admin_cli.py approve-registration --request-id <ID>")
        
    except Exception as e:
        print(f"❌ Ошибка получения запросов: {e}")
        return False
    
    return True

def approve_registration(args):
    """Одобрение запроса на регистрацию устройства"""
    registry = get_device_registry()
    
    try:
        success = registry.approve_registration_request(
            request_id=args.request_id,
            approved_by=args.approved_by
        )
        
        if success:
            print(f"✅ Запрос регистрации {args.request_id} одобрен!")
            print(f"   Одобрил: {args.approved_by}")
            print(f"   Устройство получило доступ к системе")
        else:
            print(f"❌ Не удалось одобрить запрос {args.request_id}")
            print(f"   Возможно, запрос не найден или уже обработан")
            
    except Exception as e:
        print(f"❌ Ошибка одобрения регистрации: {e}")
        return False
    
    return True

def list_devices(args):
    """Список зарегистрированных устройств"""
    registry = get_device_registry()
    
    try:
        devices = registry.get_registered_devices(
            device_type=args.type,
            status=args.status
        )
        
        if not devices:
            print("📱 Нет зарегистрированных устройств")
            return True
        
        print(f"📱 Зарегистрированные устройства ({len(devices)}):")
        print()
        
        for device in devices:
            status_emoji = {
                'active': '🟢',
                'pending': '🟡', 
                'inactive': '🔴',
                'revoked': '❌'
            }.get(device.status, '❓')
            
            print(f"{status_emoji} {device.hostname} ({device.device_type})")
            print(f"   ID: {device.device_id}")
            print(f"   Tailscale IP: {device.tailscale_ip}")
            print(f"   Статус: {device.status}")
            print(f"   Регистрация: {device.registration_time}")
            print(f"   Последняя активность: {device.last_seen}")
            print(f"   Теги: {', '.join(device.tags)}")
            print()
        
    except Exception as e:
        print(f"❌ Ошибка получения устройств: {e}")
        return False
    
    return True

def show_system_status(args):
    """Показать статус системы"""
    rbac = get_rbac_system()
    registry = get_device_registry()
    
    try:
        rbac_stats = rbac.get_rbac_stats()
        device_stats = registry.get_device_stats()
        
        print("🏥 СТАТУС СИСТЕМЫ CUBE_RS")
        print("=" * 50)
        
        print("\n👥 ПОЛЬЗОВАТЕЛИ:")
        print(f"   Активные пользователи: {rbac_stats.get('active_users', 0)}")
        print(f"   Администраторы: {rbac_stats.get('admin_users', 0)}")
        print(f"   Всего ролей: {rbac_stats.get('total_roles', 0)}")
        print(f"   Системные роли: {rbac_stats.get('system_roles', 0)}")
        
        print("\n📱 УСТРОЙСТВА:")
        print(f"   Всего устройств: {device_stats.get('total_devices', 0)}")
        print(f"   Активные устройства: {device_stats.get('active_devices', 0)}")
        print(f"   Ожидающие одобрения: {device_stats.get('pending_requests', 0)}")
        print(f"   Активные ключи: {device_stats.get('active_auth_keys', 0)}")
        
        devices_by_type = device_stats.get('devices_by_type', {})
        if devices_by_type:
            print("\n📊 УСТРОЙСТВА ПО ТИПАМ:")
            for device_type, count in devices_by_type.items():
                print(f"   {device_type}: {count}")
        
        print(f"\n⏰ Обновлено: {rbac_stats.get('timestamp', 'Неизвестно')}")
        
    except Exception as e:
        print(f"❌ Ошибка получения статуса: {e}")
        return False
    
    return True

def main():
    parser = argparse.ArgumentParser(description="CLI администрирование CUBE_RS")
    subparsers = parser.add_subparsers(dest='command', help='Доступные команды')
    
    # Создание пользователя
    user_parser = subparsers.add_parser('create-user', help='Создать пользователя')
    user_parser.add_argument('--username', required=True, help='Имя пользователя')
    user_parser.add_argument('--email', required=True, help='Email пользователя')
    user_parser.add_argument('--full-name', required=True, help='Полное имя')
    user_parser.add_argument('--password', required=True, help='Пароль')
    user_parser.add_argument('--role', help='Роль пользователя')
    user_parser.add_argument('--admin', action='store_true', help='Сделать администратором')
    
    # Список пользователей
    subparsers.add_parser('list-users', help='Список пользователей')
    
    # Создание ключа устройства
    key_parser = subparsers.add_parser('create-device-key', help='Создать ключ для устройства')
    key_parser.add_argument('--expires', type=int, default=24, help='Срок действия (часы)')
    key_parser.add_argument('--max-usage', type=int, default=-1, help='Максимальное использование')
    key_parser.add_argument('--reusable', action='store_true', default=True, help='Переиспользуемый ключ')
    key_parser.add_argument('--ephemeral', action='store_true', help='Эфемерный ключ')
    key_parser.add_argument('--tags', nargs='+', default=['farm'], help='Теги устройства')
    key_parser.add_argument('--created-by', default='admin', help='Кто создал ключ')
    
    # Список ожидающих регистраций
    subparsers.add_parser('list-pending', help='Ожидающие одобрения регистрации')
    
    # Одобрение регистрации
    approve_parser = subparsers.add_parser('approve-registration', help='Одобрить регистрацию')
    approve_parser.add_argument('--request-id', required=True, help='ID запроса регистрации')
    approve_parser.add_argument('--approved-by', default='admin', help='Кто одобряет')
    
    # Список устройств
    devices_parser = subparsers.add_parser('list-devices', help='Список устройств')
    devices_parser.add_argument('--type', help='Фильтр по типу устройства')
    devices_parser.add_argument('--status', help='Фильтр по статусу')
    
    # Статус системы
    subparsers.add_parser('status', help='Статус системы')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    print("🚀 CUBE_RS Admin CLI")
    print("-" * 30)
    
    commands = {
        'create-user': create_user,
        'list-users': list_users,
        'create-device-key': create_device_key,
        'list-pending': list_pending_registrations,
        'approve-registration': approve_registration,
        'list-devices': list_devices,
        'status': show_system_status
    }
    
    command_func = commands.get(args.command)
    if command_func:
        success = command_func(args)
        if not success:
            sys.exit(1)
    else:
        print(f"❌ Неизвестная команда: {args.command}")
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()