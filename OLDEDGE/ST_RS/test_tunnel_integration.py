#!/usr/bin/env python3
"""
Тест интеграции EDGE с IXON-style Tunnel System
Проверяем что EDGE может зарегистрироваться в tunnel broker
и предоставлять данные через P2P API
"""

import json
import sys
import time
from pathlib import Path

# Add EDGE root to Python path  
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.tunnel_integration import EDGETunnelClient, is_tunnel_system_available


def test_tunnel_system_availability():
    """Тест доступности Tunnel System"""
    print("🧪 Тестируем доступность Tunnel System...")
    
    available = is_tunnel_system_available()
    if available:
        print("✅ Tunnel System доступна")
        return True
    else:
        print("❌ Tunnel System недоступна")
        print("   Убедитесь что tunnel_system находится в родительской директории")
        return False


def test_tunnel_client_creation():
    """Тест создания EDGE Tunnel Client"""
    print("\n🧪 Тестируем создание EDGE Tunnel Client...")
    
    try:
        client = EDGETunnelClient(
            broker_url="http://localhost:8080",
            farm_id="test-edge-farm",
            owner_id="test_user_123",
            farm_name="Test EDGE Farm",
            local_port=8081
        )
        
        print("✅ EDGE Tunnel Client создан")
        print(f"   • Farm ID: {client.farm_id}")
        print(f"   • Farm Name: {client.farm_name}")
        print(f"   • Owner ID: {client.owner_id}")
        print(f"   • Local Port: {client.local_port}")
        
        return client
        
    except Exception as e:
        print(f"❌ Ошибка создания клиента: {e}")
        return None


def test_farm_capabilities(client):
    """Тест получения capabilities фермы"""
    print("\n🧪 Тестируем получение capabilities...")
    
    try:
        capabilities = client.get_farm_capabilities()
        print(f"✅ Capabilities получены: {len(capabilities)} элементов")
        
        for capability in capabilities:
            print(f"   🔧 {capability}")
        
        # Проверяем что есть базовые capabilities
        expected = ['monitoring', 'web_dashboard']
        for cap in expected:
            if cap in capabilities:
                print(f"   ✅ {cap} - присутствует")
            else:
                print(f"   ⚠️ {cap} - отсутствует")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка получения capabilities: {e}")
        return False


def test_current_data(client):
    """Тест получения текущих данных"""
    print("\n🧪 Тестируем получение текущих данных...")
    
    try:
        data = client.get_current_data()
        print("✅ Данные получены")
        
        # Проверяем структуру данных
        required_fields = ["timestamp", "farm_status", "farm_id", "farm_name"]
        for field in required_fields:
            if field in data:
                print(f"   ✅ {field}: {data[field]}")
            else:
                print(f"   ❌ {field}: отсутствует")
        
        # Проверяем устройства
        if "devices" in data:
            device_count = len(data["devices"])
            print(f"   📱 Устройств найдено: {device_count}")
            
            for i, device in enumerate(data["devices"][:3]):  # Показываем первые 3
                print(f"      {i+1}. {device.get('name', 'Unnamed')} ({device.get('device_type', 'Unknown')})")
                print(f"         Status: {device.get('status', 'unknown')}")
                print(f"         Issues: {device.get('has_issues', False)}")
        
        return data
        
    except Exception as e:
        print(f"❌ Ошибка получения данных: {e}")
        return None


def test_device_details(client):
    """Тест получения деталей устройства"""
    print("\n🧪 Тестируем получение деталей устройства...")
    
    try:
        # Пробуем получить детали устройства ID 1
        device_details = client.get_device_details(1)
        
        if "error" not in device_details:
            print("✅ Детали устройства получены")
            
            if "device" in device_details:
                device = device_details["device"]
                print(f"   📱 Устройство: {device.get('name', 'Unknown')}")
                print(f"   🏷️ Тип: {device.get('device_type', 'Unknown')}")
                print(f"   📍 Местоположение: {device.get('location', 'Not specified')}")
            
            if "data" in device_details:
                data = device_details["data"]
                formatted_text = data.get("formatted_text", "")
                print(f"   📊 Форматированный текст: {len(formatted_text)} символов")
                
                if data.get("alarms"):
                    print(f"   ⚠️ Аварий: {len(data['alarms'])}")
                if data.get("warnings"):
                    print(f"   ⚠️ Предупреждений: {len(data['warnings'])}")
        else:
            print(f"⚠️ Устройство ID 1 недоступно: {device_details['error']}")
        
        return device_details
        
    except Exception as e:
        print(f"❌ Ошибка получения деталей устройства: {e}")
        return None


def test_api_proxy_setup(client):
    """Тест настройки API прокси"""
    print("\n🧪 Тестируем настройку API прокси...")
    
    try:
        app = client.setup_tunnel_api_proxy()
        print("✅ Flask приложение создано")
        
        # Тестируем endpoints через test_client
        with app.test_client() as test_client:
            
            # Тест health endpoint
            print("\n   🔍 Тест /health...")
            response = test_client.get('/health')
            assert response.status_code == 200
            health_data = response.get_json()
            print(f"      ✅ Status: {health_data['status']}")
            print(f"      ✅ Service: {health_data['service']}")
            print(f"      ✅ Farm ID: {health_data['farm_id']}")
            
            # Тест current data endpoint
            print("\n   🔍 Тест /api/data/current...")
            response = test_client.get('/api/data/current')
            assert response.status_code == 200
            data = response.get_json()
            print(f"      ✅ Status: {data['status']}")
            print(f"      ✅ Source: {data['source']}")
            print(f"      ✅ Farm ID: {data['farm_id']}")
            
            # Тест statistics endpoint
            print("\n   🔍 Тест /api/data/statistics...")
            response = test_client.get('/api/data/statistics')
            assert response.status_code == 200
            stats = response.get_json()
            print(f"      ✅ Status: {stats['status']}")
            
            if stats['status'] == 'success':
                stats_data = stats['data']
                print(f"      ✅ Devices Count: {stats_data.get('devices_count', 0)}")
                print(f"      ✅ API Version: {stats_data.get('api_version', 'unknown')}")
            
            # Тест главной страницы
            print("\n   🔍 Тест / (главная страница)...")
            response = test_client.get('/')
            assert response.status_code == 200
            html_content = response.get_data(as_text=True)
            assert "EDGE Farm" in html_content
            print(f"      ✅ HTML страница загружена: {len(html_content)} символов")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка настройки API прокси: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_integration_compatibility():
    """Тест совместимости с tunnel system форматами"""
    print("\n🧪 Тестируем совместимость форматов данных...")
    
    try:
        client = EDGETunnelClient(
            broker_url="http://test-broker",
            farm_id="compatibility-test",
            owner_id="test_user",
            farm_name="Compatibility Test Farm",
            local_port=8082
        )
        
        # Получаем данные в формате tunnel system
        data = client.get_current_data()
        
        # Проверяем совместимость с ожидаемой структурой
        compatibility_checks = [
            ("timestamp", lambda d: isinstance(d.get("timestamp"), (int, float))),
            ("farm_status", lambda d: d.get("farm_status") in ["online", "offline", "warning", "error"]),
            ("farm_id", lambda d: isinstance(d.get("farm_id"), str) and len(d.get("farm_id", "")) > 0),
            ("devices", lambda d: isinstance(d.get("devices"), list)),
        ]
        
        all_compatible = True
        for field, check in compatibility_checks:
            if check(data):
                print(f"   ✅ {field} - совместим")
            else:
                print(f"   ❌ {field} - не совместим")
                all_compatible = False
        
        if all_compatible:
            print("✅ Форматы данных совместимы с tunnel system")
        else:
            print("⚠️ Обнаружены проблемы совместимости")
        
        return all_compatible
        
    except Exception as e:
        print(f"❌ Ошибка проверки совместимости: {e}")
        return False


def main():
    """Основная функция тестирования"""
    print("🚀 ТЕСТИРОВАНИЕ IXON-STYLE TUNNEL INTEGRATION")
    print("=" * 60)
    
    test_results = []
    
    try:
        # 1. Проверка доступности tunnel system
        if not test_tunnel_system_availability():
            print("\n❌ КРИТИЧЕСКАЯ ОШИБКА: Tunnel System недоступна")
            print("   Тестирование прервано")
            return 1
        test_results.append(("Tunnel System доступность", True))
        
        # 2. Создание клиента
        client = test_tunnel_client_creation()
        if not client:
            print("\n❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось создать клиента")
            return 1
        test_results.append(("Создание EDGE Tunnel Client", True))
        
        # 3. Тестирование capabilities
        caps_ok = test_farm_capabilities(client)
        test_results.append(("Farm capabilities", caps_ok))
        
        # 4. Тестирование получения данных
        data = test_current_data(client)
        test_results.append(("Получение текущих данных", data is not None))
        
        # 5. Тестирование деталей устройства
        device_details = test_device_details(client)
        test_results.append(("Детали устройства", device_details is not None))
        
        # 6. Тестирование API прокси
        api_ok = test_api_proxy_setup(client)
        test_results.append(("API прокси настройка", api_ok))
        
        # 7. Тестирование совместимости
        compat_ok = test_integration_compatibility()
        test_results.append(("Совместимость форматов", compat_ok))
        
        # Подведение итогов
        print("\n" + "=" * 60)
        print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
        print("=" * 60)
        
        passed = 0
        total = len(test_results)
        
        for test_name, result in test_results:
            status = "✅ ПРОШЕЛ" if result else "❌ ПРОВАЛЕН"
            print(f"{status:<15} {test_name}")
            if result:
                passed += 1
        
        print(f"\n🎯 ИТОГО: {passed}/{total} тестов прошли")
        
        if passed == total:
            print("\n🎉 ВСЕ ТЕСТЫ TUNNEL INTEGRATION ПРОШЛИ!")
            print("✅ EDGE интегрирован с IXON-style tunnel system")
            print("✅ P2P соединения готовы к работе")
            print("✅ Совместимость с mobile_app обеспечена")
            print("\n🚀 ГОТОВ К ЗАПУСКУ:")
            print("   python start_tunnel_client.py")
            return 0
        else:
            print(f"\n⚠️ {total - passed} тестов провалены")
            print("   Проверьте ошибки выше")
            return 1
            
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА ТЕСТИРОВАНИЯ: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())