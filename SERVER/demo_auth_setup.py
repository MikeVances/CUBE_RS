#!/usr/bin/env python3
"""
Демонстрация настройки системы аутентификации
Автоматическое создание администратора, пользователей и EDGE устройств
"""

import sys
from auth_system import AuthenticationManager, UserRole

def setup_demo_auth():
    """Настройка демонстрационной среды аутентификации"""
    
    print("🔐 Setting up EDGE SERVER Authentication Demo")
    print("=" * 50)
    
    # Инициализируем менеджер аутентификации
    auth = AuthenticationManager('demo_auth.db')
    
    # 1. Создаем администратора
    print("\n1️⃣ Creating system administrator...")
    try:
        admin_id = auth.create_user(
            username="admin",
            password="admin123456",  # В продакшене - сложный пароль!
            role=UserRole.ADMIN,
            email="admin@cube-rs.com",
            permissions=["*"]
        )
        print(f"   ✅ Admin created: {admin_id}")
        print(f"   Username: admin")
        print(f"   Password: admin123456")
    except Exception as e:
        print(f"   ⚠️ Admin may already exist: {e}")
    
    # 2. Создаем владельца фермы
    print("\n2️⃣ Creating farm owner...")
    try:
        farmer_id = auth.create_user(
            username="farmer1",
            password="farmer123456",
            role=UserRole.FARM_OWNER,
            email="farmer@cube-rs.com",
            permissions=["farm:view", "farm:manage", "device:view", "device:manage"]
        )
        print(f"   ✅ Farm owner created: {farmer_id}")
        print(f"   Username: farmer1")
        print(f"   Password: farmer123456")
    except Exception as e:
        print(f"   ⚠️ Farm owner may already exist: {e}")
        # Получаем существующего пользователя
        farmer_id = "user_farmer1"  # Примерное значение
    
    # 3. Создаем пользователя-наблюдателя
    print("\n3️⃣ Creating viewer user...")
    try:
        viewer_id = auth.create_user(
            username="viewer1",
            password="viewer123456",
            role=UserRole.VIEWER,
            email="viewer@cube-rs.com",
            permissions=["farm:view", "device:view"]
        )
        print(f"   ✅ Viewer created: {viewer_id}")
        print(f"   Username: viewer1")
        print(f"   Password: viewer123456")
    except Exception as e:
        print(f"   ⚠️ Viewer may already exist: {e}")
    
    # 4. Регистрируем EDGE устройства
    print("\n4️⃣ Registering EDGE devices...")
    
    # Устройство 1: КУБ-1063 (вентиляция)
    try:
        device1_id, api_key1 = auth.register_edge_device(
            farm_id="farm_greenhouse_01",
            device_name="EDGE-Теплица-Вент",
            owner_id=farmer_id,
            device_type="EDGE",
            capabilities=["kub1063", "temperature", "humidity", "ventilation"]
        )
        print(f"   ✅ EDGE Device 1 registered: {device1_id}")
        print(f"      Farm: farm_greenhouse_01")
        print(f"      Type: Ventilation Control (KUB-1063)")
        print(f"      API Key: {api_key1}")
    except Exception as e:
        print(f"   ❌ Device 1 registration failed: {e}")
    
    # Устройство 2: КУБ-1112 (отопление)
    try:
        device2_id, api_key2 = auth.register_edge_device(
            farm_id="farm_greenhouse_02",
            device_name="EDGE-Теплица-Тепло",
            owner_id=farmer_id,
            device_type="EDGE", 
            capabilities=["kub1112", "heating", "gas_control", "flame_level"]
        )
        print(f"   ✅ EDGE Device 2 registered: {device2_id}")
        print(f"      Farm: farm_greenhouse_02")
        print(f"      Type: Heating Control (KUB-1112)")
        print(f"      API Key: {api_key2}")
    except Exception as e:
        print(f"   ❌ Device 2 registration failed: {e}")
    
    # 5. Показываем статистику
    print("\n5️⃣ System Statistics:")
    try:
        devices = auth.list_edge_devices()
        print(f"   📱 Total EDGE devices: {len(devices)}")
        
        for device in devices:
            status_icon = {'online': '🟢', 'offline': '🔴', 'unknown': '⚪'}.get(device['status'], '⚪')
            print(f"   {status_icon} {device['device_name']} ({device['device_id'][:12]}...)")
    except Exception as e:
        print(f"   ❌ Statistics error: {e}")
    
    # 6. Демо команды
    print("\n📋 Demo Environment Ready!")
    print("=" * 50)
    print("\n🔑 Authentication Details:")
    print("   Admin:      admin / admin123456")  
    print("   Farm Owner: farmer1 / farmer123456")
    print("   Viewer:     viewer1 / viewer123456")
    
    print("\n💻 CLI Commands to try:")
    print("   python3 admin_cli.py list-users")
    print("   python3 admin_cli.py list-devices") 
    print("   python3 admin_cli.py connection-stats")
    
    print("\n📱 Environment variables for EDGE devices:")
    if 'device1_id' in locals() and 'api_key1' in locals():
        print(f"   # Device 1 (Ventilation)")
        print(f'   export EDGE_API_KEY="{api_key1}"')
        print(f'   export EDGE_DEVICE_ID="{device1_id}"')
        print(f'   export EDGE_FARM_ID="farm_greenhouse_01"')
        print(f'   export TUNNEL_BROKER_URL="https://your-server.com:8080"')
    
    if 'device2_id' in locals() and 'api_key2' in locals():
        print(f"\n   # Device 2 (Heating)")
        print(f'   export EDGE_API_KEY="{api_key2}"')
        print(f'   export EDGE_DEVICE_ID="{device2_id}"')
        print(f'   export EDGE_FARM_ID="farm_greenhouse_02"')
        print(f'   export TUNNEL_BROKER_URL="https://your-server.com:8080"')
    
    print(f"\n🗄️ Database location: demo_auth.db")
    print("🎉 Demo setup complete!")

if __name__ == "__main__":
    setup_demo_auth()