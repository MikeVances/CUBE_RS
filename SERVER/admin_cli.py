#!/usr/bin/env python3
"""
CLI для администрирования EDGE SERVER системы
Управление пользователями, EDGE устройствами и API ключами
"""

import argparse
import getpass
import json
import sys
import time
from typing import List, Dict
from tabulate import tabulate

from auth_system import AuthenticationManager, UserRole


def create_admin(auth: AuthenticationManager, args):
    """Создание администратора"""
    username = args.username or input("Username: ")
    email = args.email or input("Email (optional): ") or None
    
    # Безопасный ввод пароля
    password = getpass.getpass("Password: ")
    confirm_password = getpass.getpass("Confirm password: ")
    
    if password != confirm_password:
        print("❌ Passwords don't match")
        return
    
    if len(password) < 8:
        print("❌ Password must be at least 8 characters")
        return
    
    try:
        user_id = auth.create_user(
            username=username,
            password=password,
            role=UserRole.ADMIN,
            email=email,
            permissions=["*"]
        )
        
        print(f"✅ Admin created successfully")
        print(f"   User ID: {user_id}")
        print(f"   Username: {username}")
        print(f"   Email: {email}")
        
    except Exception as e:
        print(f"❌ Failed to create admin: {e}")


def create_user(auth: AuthenticationManager, args):
    """Создание обычного пользователя"""
    username = args.username or input("Username: ")
    email = args.email or input("Email (optional): ") or None
    
    # Выбор роли
    role_map = {
        "1": UserRole.FARM_OWNER,
        "2": UserRole.VIEWER
    }
    
    print("Select user role:")
    print("1. Farm Owner (can manage own farms)")
    print("2. Viewer (read-only access)")
    
    role_choice = input("Choice (1-2): ")
    role = role_map.get(role_choice, UserRole.VIEWER)
    
    # Безопасный ввод пароля
    password = getpass.getpass("Password: ")
    confirm_password = getpass.getpass("Confirm password: ")
    
    if password != confirm_password:
        print("❌ Passwords don't match")
        return
    
    # Permissions по роли
    if role == UserRole.FARM_OWNER:
        permissions = ["farm:view", "farm:manage", "device:view", "device:manage"]
    else:
        permissions = ["farm:view", "device:view"]
    
    try:
        user_id = auth.create_user(
            username=username,
            password=password,
            role=role,
            email=email,
            permissions=permissions
        )
        
        print(f"✅ User created successfully")
        print(f"   User ID: {user_id}")
        print(f"   Username: {username}")
        print(f"   Role: {role.value}")
        print(f"   Permissions: {', '.join(permissions)}")
        
    except Exception as e:
        print(f"❌ Failed to create user: {e}")


def list_users(auth: AuthenticationManager, args):
    """Список всех пользователей"""
    try:
        import sqlite3
        with sqlite3.connect(auth.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, username, email, role, created_at, last_login, is_active
                FROM users 
                ORDER BY created_at DESC
            """)
            
            users = cursor.fetchall()
        
        if not users:
            print("No users found")
            return
        
        # Форматируем данные для таблицы
        table_data = []
        for user in users:
            user_id, username, email, role, created_at, last_login, is_active = user
            
            # Форматируем даты
            created = time.strftime('%Y-%m-%d %H:%M', time.localtime(created_at))
            last_login_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(last_login)) if last_login else "Never"
            status = "✅ Active" if is_active else "❌ Disabled"
            
            table_data.append([
                user_id[:12] + "...",
                username,
                email or "-",
                role,
                created,
                last_login_str,
                status
            ])
        
        headers = ["User ID", "Username", "Email", "Role", "Created", "Last Login", "Status"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        
    except Exception as e:
        print(f"❌ Failed to list users: {e}")


def register_edge_device(auth: AuthenticationManager, args):
    """Регистрация EDGE устройства"""
    # Получаем список пользователей для выбора владельца
    print("Available users:")
    list_users(auth, args)
    
    owner_id = args.owner_id or input("Owner ID: ")
    farm_id = args.farm_id or input("Farm ID: ")
    device_name = args.device_name or input("Device Name: ")
    device_type = args.device_type or "EDGE"
    
    # Capabilities
    capabilities_input = input("Capabilities (comma-separated, e.g., kub1063,kub1112): ")
    capabilities = [c.strip() for c in capabilities_input.split(",")] if capabilities_input else None
    
    try:
        device_id, api_key = auth.register_edge_device(
            farm_id=farm_id,
            device_name=device_name,
            owner_id=owner_id,
            device_type=device_type,
            capabilities=capabilities
        )
        
        print(f"✅ EDGE device registered successfully")
        print(f"   Device ID: {device_id}")
        print(f"   Farm ID: {farm_id}")
        print(f"   Device Name: {device_name}")
        print(f"   Owner ID: {owner_id}")
        print(f"   Capabilities: {capabilities}")
        print(f"\n🔑 API KEY (save this securely):")
        print(f"   {api_key}")
        print(f"\n📋 Environment variables for EDGE device:")
        print(f'   export EDGE_API_KEY="{api_key}"')
        print(f'   export EDGE_DEVICE_ID="{device_id}"')
        print(f'   export EDGE_FARM_ID="{farm_id}"')
        
    except Exception as e:
        print(f"❌ Failed to register device: {e}")


def list_edge_devices(auth: AuthenticationManager, args):
    """Список EDGE устройств"""
    try:
        devices = auth.list_edge_devices()
        
        if not devices:
            print("No EDGE devices found")
            return
        
        # Форматируем данные для таблицы
        table_data = []
        for device in devices:
            last_heartbeat = "Never"
            if device['last_heartbeat']:
                last_heartbeat = time.strftime('%Y-%m-%d %H:%M', time.localtime(device['last_heartbeat']))
            
            status_icon = {
                'online': '🟢',
                'offline': '🔴',
                'unknown': '⚪'
            }.get(device['status'], '⚪')
            
            table_data.append([
                device['device_id'][:12] + "...",
                device['farm_id'][:15] + "...",
                device['device_name'][:20],
                device['device_type'],
                f"{status_icon} {device['status']}",
                last_heartbeat,
                ', '.join(device['capabilities'][:3])  # Первые 3 capability
            ])
        
        headers = ["Device ID", "Farm ID", "Name", "Type", "Status", "Last Heartbeat", "Capabilities"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        
    except Exception as e:
        print(f"❌ Failed to list devices: {e}")


def list_api_keys(auth: AuthenticationManager, args):
    """Список API ключей пользователя"""
    user_id = args.user_id or input("User ID: ")
    
    try:
        keys = auth.list_user_api_keys(user_id)
        
        if not keys:
            print(f"No API keys found for user {user_id}")
            return
        
        # Форматируем данные для таблицы
        table_data = []
        for key in keys:
            created = time.strftime('%Y-%m-%d %H:%M', time.localtime(key['created_at']))
            
            expires = "Never"
            if key['expires_at']:
                expires = time.strftime('%Y-%m-%d %H:%M', time.localtime(key['expires_at']))
            
            last_used = "Never"
            if key['last_used']:
                last_used = time.strftime('%Y-%m-%d %H:%M', time.localtime(key['last_used']))
            
            status = "✅ Active" if key['is_active'] else "❌ Revoked"
            
            table_data.append([
                key['key_id'][:12] + "...",
                key['name'][:20],
                key['role'],
                created,
                expires,
                last_used,
                status
            ])
        
        headers = ["Key ID", "Name", "Role", "Created", "Expires", "Last Used", "Status"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        
    except Exception as e:
        print(f"❌ Failed to list API keys: {e}")


def revoke_api_key(auth: AuthenticationManager, args):
    """Отзыв API ключа"""
    key_id = args.key_id or input("Key ID to revoke: ")
    
    confirm = input(f"Are you sure you want to revoke key {key_id}? (yes/no): ")
    if confirm.lower() != 'yes':
        print("❌ Operation cancelled")
        return
    
    try:
        success = auth.revoke_api_key(key_id)
        if success:
            print(f"✅ API key {key_id} revoked successfully")
        else:
            print(f"❌ API key {key_id} not found")
            
    except Exception as e:
        print(f"❌ Failed to revoke API key: {e}")


def show_connection_stats(auth: AuthenticationManager, args):
    """Показать статистику соединений"""
    try:
        devices = auth.list_edge_devices()
        
        # Статистика
        total_devices = len(devices)
        online_devices = sum(1 for d in devices if d['status'] == 'online')
        offline_devices = total_devices - online_devices
        
        # Группировка по типам
        device_types = {}
        for device in devices:
            dtype = device['device_type']
            if dtype not in device_types:
                device_types[dtype] = {'total': 0, 'online': 0}
            device_types[dtype]['total'] += 1
            if device['status'] == 'online':
                device_types[dtype]['online'] += 1
        
        print("🔗 EDGE DEVICES CONNECTION STATISTICS")
        print("=" * 50)
        print(f"📱 Total Devices: {total_devices}")
        print(f"🟢 Online: {online_devices}")
        print(f"🔴 Offline: {offline_devices}")
        print(f"📊 Uptime: {(online_devices/total_devices*100):.1f}%" if total_devices > 0 else "0%")
        
        if device_types:
            print(f"\n📈 By Device Type:")
            for dtype, stats in device_types.items():
                print(f"   {dtype}: {stats['online']}/{stats['total']} online")
        
        # Последние активные устройства
        recent_devices = sorted(
            [d for d in devices if d['last_heartbeat']], 
            key=lambda x: x['last_heartbeat'], 
            reverse=True
        )[:5]
        
        if recent_devices:
            print(f"\n🕒 Recently Active Devices:")
            for device in recent_devices:
                last_seen = time.strftime('%Y-%m-%d %H:%M', time.localtime(device['last_heartbeat']))
                status_icon = '🟢' if device['status'] == 'online' else '🔴'
                print(f"   {status_icon} {device['device_name']} - {last_seen}")
        
    except Exception as e:
        print(f"❌ Failed to get connection stats: {e}")


def test_auth_system(auth: AuthenticationManager, args):
    """Тест системы аутентификации"""
    print("🧪 Testing Authentication System...")
    
    try:
        # Создаем тестового пользователя
        print("1️⃣ Creating test user...")
        user_id = auth.create_user(
            username=f"test_user_{int(time.time())}",
            password="test123456",
            role=UserRole.FARM_OWNER,
            permissions=["farm:view", "device:view"]
        )
        print(f"   ✅ User created: {user_id}")
        
        # Тестируем аутентификацию
        print("2️⃣ Testing user authentication...")
        token = auth.authenticate_user(f"test_user_{int(time.time())}", "test123456")
        if token:
            print(f"   ✅ User authenticated: {token.user_id}")
        else:
            print("   ❌ User authentication failed")
        
        # Создаем API ключ
        print("3️⃣ Creating API key...")
        key_id, api_key = auth.create_api_key(
            owner_id=user_id,
            name="Test Key",
            role=UserRole.EDGE_DEVICE,
            permissions=["device:heartbeat"]
        )
        print(f"   ✅ API key created: {key_id}")
        
        # Тестируем API ключ
        print("4️⃣ Testing API key authentication...")
        api_token = auth.authenticate_api_key(api_key)
        if api_token:
            print(f"   ✅ API key authenticated: {api_token.user_id}")
        else:
            print("   ❌ API key authentication failed")
        
        # Регистрируем тестовое устройство
        print("5️⃣ Registering test EDGE device...")
        device_id, device_api_key = auth.register_edge_device(
            farm_id="test_farm",
            device_name="Test EDGE Device",
            owner_id=user_id,
            capabilities=["test"]
        )
        print(f"   ✅ Device registered: {device_id}")
        
        print("\n🎉 All tests passed! Authentication system is working correctly.")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="EDGE SERVER Administration CLI")
    parser.add_argument("--db", default="auth.db", help="Database path")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Create admin
    admin_parser = subparsers.add_parser("create-admin", help="Create administrator")
    admin_parser.add_argument("--username", help="Admin username")
    admin_parser.add_argument("--email", help="Admin email")
    
    # Create user
    user_parser = subparsers.add_parser("create-user", help="Create user")
    user_parser.add_argument("--username", help="Username")
    user_parser.add_argument("--email", help="User email")
    
    # List users
    subparsers.add_parser("list-users", help="List all users")
    
    # Register EDGE device
    device_parser = subparsers.add_parser("register-device", help="Register EDGE device")
    device_parser.add_argument("--owner-id", help="Owner user ID")
    device_parser.add_argument("--farm-id", help="Farm ID")
    device_parser.add_argument("--device-name", help="Device name")
    device_parser.add_argument("--device-type", default="EDGE", help="Device type")
    
    # List devices
    subparsers.add_parser("list-devices", help="List EDGE devices")
    
    # List API keys
    keys_parser = subparsers.add_parser("list-keys", help="List user API keys")
    keys_parser.add_argument("--user-id", help="User ID")
    
    # Revoke API key
    revoke_parser = subparsers.add_parser("revoke-key", help="Revoke API key")
    revoke_parser.add_argument("--key-id", help="Key ID to revoke")
    
    # Connection stats
    subparsers.add_parser("connection-stats", help="Show connection statistics")
    
    # Test system
    subparsers.add_parser("test", help="Test authentication system")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Инициализируем менеджер аутентификации
    auth = AuthenticationManager(args.db)
    
    # Выполняем команду
    commands = {
        'create-admin': create_admin,
        'create-user': create_user,
        'list-users': list_users,
        'register-device': register_edge_device,
        'list-devices': list_edge_devices,
        'list-keys': list_api_keys,
        'revoke-key': revoke_api_key,
        'connection-stats': show_connection_stats,
        'test': test_auth_system
    }
    
    command_func = commands.get(args.command)
    if command_func:
        command_func(auth, args)
    else:
        print(f"❌ Unknown command: {args.command}")


if __name__ == "__main__":
    main()