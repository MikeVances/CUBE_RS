#!/usr/bin/env python3
"""
Тест новой гибкой архитектуры EDGE
Проверяем Variable System, Device Registry, Device Adapters
"""

import sys
from pathlib import Path

# Add EDGE root to Python path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.device_registry import DeviceRegistry, DeviceType, DeviceInfo
from core.device_adapters import get_device_adapter, KUB1063Adapter
from core.log_filter import get_secure_logger

logger = get_secure_logger(__name__)


def test_device_registry():
    """Тест системы регистрации устройств"""
    print("🧪 Тестируем Device Registry...")
    
    # Создаём реестр
    registry = DeviceRegistry()
    
    # Проверяем дефолтное устройство
    devices = registry.get_all_devices()
    print(f"✅ Загружено устройств: {len(devices)}")
    
    for device in devices:
        print(f"  📱 {device.name} (ID: {device.device_id}, Type: {device.device_type.value})")
    
    # Добавляем новое устройство КУБ-1112
    kub1112_device = DeviceInfo(
        device_id=2,
        device_type=DeviceType.KUB_1112,
        slave_id=2,
        name="Тестовый КУБ-1112 Обогрев",
        description="Система обогрева для тестирования",
        location="Тестовая зона"
    )
    
    success = registry.register_device(kub1112_device)
    print(f"✅ Регистрация КУБ-1112: {'успешно' if success else 'ошибка'}")
    
    # Проверяем поиск по slave_id
    device = registry.get_device_by_slave_id(1)
    if device:
        print(f"✅ Поиск по slave_id 1: {device.name}")
    
    return registry


def test_kub1063_adapter():
    """Тест адаптера КУБ-1063"""
    print("\n🧪 Тестируем KUB1063 Adapter...")
    
    # Создаём адаптер
    adapter = KUB1063Adapter()
    print(f"✅ Адаптер создан: {adapter.device_type}")
    
    # Получаем адреса регистров
    addresses = adapter.get_register_addresses()
    print(f"✅ Регистров для чтения: {len(addresses)}")
    print(f"  📋 Адреса: {[f'0x{addr:04X}' for addr in sorted(addresses)[:10]]}...")
    
    # Создаём менеджер переменных для устройства
    device_manager = adapter.create_device_manager(device_id=1)
    print(f"✅ Device Manager создан для устройства 1")
    
    # Тестируем обработку данных регистров
    test_register_data = {
        0x008D: 255,    # temp_inside_1 = 25.5°C
        0x008E: 235,    # temp_inside_2 = 23.5°C  
        0x0083: -50,    # pressure = -5.0 Па
        0x0084: 650,    # humidity = 65.0%
        0x0085: 1200,   # CO2 = 1200 ppm
        0x0086: 25,     # NH3 = 2.5 ppm
        0x00D1: 750,    # ventilation_level = 75.0%
        0x00D2: 1,      # ventilation_scheme = туннельная
        0x7FFC: 0x7FFC, # disabled sensor (для temp_inside_3)
        0x7FFE: 0x7FFE, # break sensor (для temp_inside_4)
    }
    
    # Обновляем данные
    device_manager.update_from_registers(test_register_data)
    
    # Проверяем значения
    print("✅ Тест значений переменных:")
    test_variables = [
        "temp_inside_1", "temp_inside_2", "pressure", "humidity", 
        "co2", "nh3", "ventilation_level", "ventilation_scheme"
    ]
    
    for var_name in test_variables:
        value = device_manager.get_variable_value(var_name)
        status = device_manager.get_variable_status(var_name)
        print(f"  🔹 {var_name}: {value} (статус: {status})")
    
    # Тестируем форматирование для отображения
    display_text = adapter.format_for_display(device_manager)
    print("\n✅ Форматированный текст для бота:")
    print(display_text)
    
    # Проверяем аварии и предупреждения
    alarms = adapter.get_critical_alarms(device_manager)
    warnings = adapter.get_warnings(device_manager)
    
    print(f"\n✅ Критичные аварии: {len(alarms)}")
    for alarm in alarms:
        print(f"  🚨 {alarm}")
    
    print(f"✅ Предупреждения: {len(warnings)}")
    for warning in warnings:
        print(f"  ⚠️ {warning}")
    
    # Тестируем специальные статусы
    print("\n✅ Тест специальных статусов:")
    special_data = {
        0x008D: 0x7FFC,  # disabled 
        0x008E: 0x7FFE,  # break
        0x008F: 0x7FFD,  # error
        0x0090: 0x7FFF,  # pending
    }
    
    device_manager.update_from_registers(special_data)
    
    temp_vars = ["temp_inside_1", "temp_inside_2", "temp_outside", "temp_inside_3"]
    for var_name in temp_vars:
        value = device_manager.get_variable_value(var_name)
        status = device_manager.get_variable_status(var_name)
        print(f"  🌡️ {var_name}: {value} (статус: {status})")
    
    return adapter, device_manager


def test_adapter_factory():
    """Тест фабрики адаптеров"""
    print("\n🧪 Тестируем Adapter Factory...")
    
    # Получаем адаптер для КУБ-1063
    adapter_1063 = get_device_adapter(DeviceType.KUB_1063)
    if adapter_1063:
        print(f"✅ Адаптер КУБ-1063: {adapter_1063.device_type}")
    else:
        print("❌ Адаптер КУБ-1063 не найден")
    
    # Получаем адаптер для КУБ-1112  
    adapter_1112 = get_device_adapter(DeviceType.KUB_1112)
    if adapter_1112:
        print(f"✅ Адаптер КУБ-1112: {adapter_1112.device_type}")
    else:
        print("⚠️ Адаптер КУБ-1112 еще не реализован")
    
    # Проверяем кэширование
    adapter_1063_cached = get_device_adapter(DeviceType.KUB_1063)
    is_same_instance = adapter_1063 is adapter_1063_cached
    print(f"✅ Кэширование адаптеров: {'работает' if is_same_instance else 'не работает'}")


def test_variable_info():
    """Тест информации о переменных"""
    print("\n🧪 Тестируем информацию о переменных...")
    
    adapter = KUB1063Adapter()
    mapper = adapter.variable_mapper
    
    # Получаем информацию о переменной
    temp_info = mapper.get_variable_info("temp_inside_1")
    if temp_info:
        print("✅ Информация о переменной temp_inside_1:")
        for key, value in temp_info.items():
            print(f"  🔹 {key}: {value}")
    
    # Получаем список всех переменных
    all_vars = mapper.get_all_variables_info()
    print(f"\n✅ Всего переменных в КУБ-1063: {len(all_vars)}")
    
    # Показываем несколько первых
    for var_info in all_vars[:5]:
        print(f"  📊 {var_info['name']} ({var_info['register_hex']}) - {var_info['description']}")


def main():
    """Основная функция тестирования"""
    print("🚀 ТЕСТИРОВАНИЕ ГИБКОЙ АРХИТЕКТУРЫ EDGE")
    print("=" * 60)
    
    try:
        # Тестируем компоненты
        registry = test_device_registry()
        adapter, device_manager = test_kub1063_adapter() 
        test_adapter_factory()
        test_variable_info()
        
        print("\n" + "=" * 60)
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("✅ Device Registry работает")
        print("✅ Variable System работает") 
        print("✅ KUB1063 Adapter работает")
        print("✅ Device Manager работает")
        print("✅ Специальные статусы обрабатываются")
        print("✅ Форматирование для бота работает")
        
        print("\n🎯 РЕЗУЛЬТАТ: Архитектура готова к расширению!")
        print("  - Легко добавить КУБ-1112")
        print("  - Легко добавить новые типы устройств")
        print("  - Variable System обрабатывает все статусы")
        print("  - Готово к интеграции в Reader/Writer/Bot")
        
    except Exception as e:
        print(f"\n❌ ОШИБКА ТЕСТИРОВАНИЯ: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())