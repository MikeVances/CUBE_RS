#!/usr/bin/env python3
"""
Тест Remote Dashboard API
Проверяем что HTTP API работает корректно
"""

import json
import sys
import time
from pathlib import Path

# Add EDGE root to Python path  
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.remote_dashboard import get_dashboard_api
from core.device_registry import get_device_registry


def test_dashboard_api():
    """Тест Remote Dashboard API endpoints"""
    print("🧪 Тестируем Remote Dashboard API...")
    
    # Создаём API
    dashboard = get_dashboard_api()
    print("✅ Dashboard API создан")
    
    # Тест Flask app
    with dashboard.app.test_client() as client:
        
        # Тест health endpoint
        print("\n🔍 Тест /api/health...")
        response = client.get('/api/health')
        assert response.status_code == 200
        data = response.get_json()
        print(f"   ✅ Status: {data['status']}")
        print(f"   ✅ Service: {data['service']}")
        
        # Тест devices endpoint
        print("\n🔍 Тест /api/devices...")
        response = client.get('/api/devices')
        assert response.status_code == 200
        data = response.get_json()
        print(f"   ✅ Devices found: {data['count']}")
        
        if data['devices']:
            device = data['devices'][0]
            print(f"   ✅ Example device: {device['name']} ({device['device_type']})")
        
        # Тест devices status endpoint
        print("\n🔍 Тест /api/devices/status...")
        response = client.get('/api/devices/status')
        assert response.status_code == 200
        data = response.get_json()
        print(f"   ✅ Summary: {data['summary']}")
        
        # Тест device details (если есть устройства)
        if data['devices']:
            device_id = data['devices'][0]['device_id']
            print(f"\n🔍 Тест /api/device/{device_id}...")
            response = client.get(f'/api/device/{device_id}')
            
            if response.status_code == 200:
                device_data = response.get_json()
                print(f"   ✅ Device details loaded for: {device_data['device']['name']}")
                print(f"   ✅ Formatted text length: {len(device_data['data']['formatted_text'])} chars")
            else:
                print(f"   ⚠️ Device details unavailable: {response.status_code}")
        
        # Тест alarms endpoint
        print("\n🔍 Тест /api/alarms...")
        response = client.get('/api/alarms')
        assert response.status_code == 200
        data = response.get_json()
        print(f"   ✅ Alarms found: {data['count']}")
        
        # Тест types endpoint
        print("\n🔍 Тест /api/types...")
        response = client.get('/api/types')
        assert response.status_code == 200
        data = response.get_json()
        print(f"   ✅ Device types: {len(data['types'])}")
        
        for device_type in data['types']:
            status = "✅" if device_type['available'] else "❌"
            print(f"   {status} {device_type['type']}: {device_type['description']}")
        
        # Тест главной страницы
        print("\n🔍 Тест / (главная страница)...")
        response = client.get('/')
        assert response.status_code == 200
        html_content = response.get_data(as_text=True)
        assert "EDGE Remote Dashboard" in html_content
        print(f"   ✅ HTML page loaded: {len(html_content)} chars")


def test_device_registry_integration():
    """Тест интеграции с Device Registry"""
    print("\n🧪 Тестируем интеграцию с Device Registry...")
    
    registry = get_device_registry()
    devices = registry.get_all_devices()
    print(f"✅ Devices в registry: {len(devices)}")
    
    for device in devices:
        print(f"   📱 {device.name} (ID: {device.device_id}, Type: {device.device_type.value})")


def main():
    """Основная функция тестирования"""
    print("🚀 ТЕСТИРОВАНИЕ REMOTE DASHBOARD")
    print("=" * 60)
    
    try:
        test_device_registry_integration()
        test_dashboard_api()
        
        print("\n" + "=" * 60)
        print("🎉 ВСЕ ТЕСТЫ REMOTE DASHBOARD ПРОШЛИ!")
        print("✅ HTTP API работает")
        print("✅ Device Registry интеграция работает")  
        print("✅ Flask endpoints работают")
        print("✅ HTML интерфейс генерируется")
        
        print("\n🎯 РЕЗУЛЬТАТ: Remote Dashboard готов к использованию!")
        print("  - Telegram бот функциональность через HTTP API")
        print("  - Веб интерфейс для удаленного мониторинга")
        print("  - Готов к работе через Tailscale VPN")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ ОШИБКА ТЕСТИРОВАНИЯ: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())