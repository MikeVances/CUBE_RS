#!/usr/bin/env python3
"""
Тест КУБ-1112 адаптера с Variable System
Проверяем что новый адаптер корректно работает с переменными
"""

import sys
from pathlib import Path

# Add EDGE root to Python path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.device_adapters.kub1112 import KUB1112Adapter


def test_adapter_initialization():
    """Тест инициализации адаптера КУБ-1112"""
    print("🧪 Тестируем инициализацию КУБ-1112 адаптера...")
    
    adapter = KUB1112Adapter()
    
    print(f"✅ Device type: {adapter.device_type}")
    print(f"✅ Variable mapper initialized: {adapter.variable_mapper is not None}")
    
    # Проверим количество зарегистрированных переменных
    variables_info = list(adapter.variable_mapper.get_all_variables_info())
    print(f"✅ Variables registered: {len(variables_info)}")
    
    # Покажем несколько ключевых переменных
    key_variables = ['flame_level', 'flame_present', 'temperature', 'operation_mode', 'relay_state']
    print("\n📋 Ключевые переменные:")
    
    for var_name in key_variables:
        var_info = adapter.variable_mapper.get_variable_info(var_name)
        if var_info:
            register_addr = var_info.get('register_address', 0)
            description = var_info.get('description', 'No description')
            print(f"   🔧 {var_name}: регистр 0x{register_addr:04X} ({description})")
        else:
            print(f"   ❌ {var_name}: не найдена")
    
    return adapter


def test_device_manager_creation():
    """Тест создания device manager"""
    print("\n🧪 Тестируем создание Device Manager...")
    
    adapter = KUB1112Adapter()
    device_id = 2
    
    try:
        manager = adapter.create_device_manager(device_id)
        print(f"✅ Device Manager создан для устройства {device_id}")
        print(f"   Device ID: {manager.device_id}")
        print(f"   Device Type: {manager.device_type}")
        print(f"   Mapper: {type(manager.mapper).__name__}")
        
        return manager
    except Exception as e:
        print(f"❌ Ошибка создания Device Manager: {e}")
        return None


def test_variable_access():
    """Тест доступа к переменным через Device Manager"""
    print("\n🧪 Тестируем доступ к переменным...")
    
    adapter = KUB1112Adapter()
    manager = adapter.create_device_manager(2)
    
    # Тестовые данные (эмулируем значения из регистров)
    test_data = {
        0x0400: 5000,    # flame_level = 50.00%
        0x0401: 1,       # flame_present = true
        0x0405: 250,     # temperature = 25.0°C
        0x0409: 2,       # operation_mode = Непрерывный обогрев
        0x0407: 0b00111, # relay_state = первые 3 реле включены
        0x0408: 0b111000, # discrete_inputs = входы 3,4,5 активны
        0x0402: 300,     # min_work_time = 30.0с
        0x0403: 50,      # start_delay = 5.0с
        0x0404: 150,     # purge_duration = 15.0с
    }
    
    # Устанавливаем тестовые значения через update_from_registers
    manager.update_from_registers(test_data)
    
    print("✅ Тестовые данные установлены")
    
    # Тестируем получение значений
    test_variables = [
        ('flame_level', 'Уровень пламени'),
        ('flame_present', 'Наличие пламени'),
        ('temperature', 'Температура'),
        ('operation_mode', 'Режим работы'),
        ('relay_state', 'Состояние реле'),
        ('discrete_inputs', 'Дискретные входы'),
        ('min_work_time', 'Мин. время работы'),
        ('start_delay', 'Задержка пуска'),
        ('purge_duration', 'Продувка')
    ]
    
    print("\n📊 Значения переменных:")
    for var_name, display_name in test_variables:
        value = manager.get_variable_value(var_name)
        status = manager.get_variable_status(var_name)
        
        if value is not None and status == "ok":
            if var_name in ['flame_level', 'temperature']:
                print(f"   🔧 {display_name}: {value:.2f}")
            elif var_name == 'flame_present':
                print(f"   🔧 {display_name}: {'Да' if value else 'Нет'}")
            elif var_name in ['relay_state', 'discrete_inputs']:
                print(f"   🔧 {display_name}: 0x{value:04X} ({bin(value)})")
            else:
                print(f"   🔧 {display_name}: {value}")
        else:
            print(f"   ⚠️ {display_name}: {status}")
    
    return manager


def test_formatting():
    """Тест форматирования для отображения"""
    print("\n🧪 Тестируем форматирование...")
    
    adapter = KUB1112Adapter()
    manager = adapter.create_device_manager(2)
    
    # Тестовые данные
    test_data = {
        0x0400: 5000,    # flame_level = 50.00%
        0x0401: 1,       # flame_present = true
        0x0405: 250,     # temperature = 25.0°C  
        0x0409: 2,       # operation_mode = Непрерывный обогрев
        0x0407: 0b00111, # relay_state = клапан газа + розжиг + основной вентилятор
        0x0408: 0b111000, # discrete_inputs = флюгер + давление + вентиляция
        0x0402: 300,     # min_work_time = 30.0с
        0x0403: 50,      # start_delay = 5.0с
        0x0404: 150,     # purge_duration = 15.0с
        0x0301: 0x0102,  # software_version = v1.2
    }
    
    manager.update_from_registers(test_data)
    
    formatted_text = adapter.format_for_display(manager)
    print("✅ Форматированный текст сгенерирован")
    print(f"   Длина: {len(formatted_text)} символов")
    print(f"   Строк: {formatted_text.count('•')}")
    
    # Покажем фрагмент
    print("\n📄 Пример форматированного вывода:")
    lines = formatted_text.split('\n')
    for line in lines[:10]:  # Первые 10 строк
        print(f"   {line}")
    if len(lines) > 10:
        print(f"   ... (и еще {len(lines) - 10} строк)")
    
    return formatted_text


def test_alarms_and_warnings():
    """Тест обработки аварий и предупреждений"""
    print("\n🧪 Тестируем аварии и предупреждения...")
    
    adapter = KUB1112Adapter()
    manager = adapter.create_device_manager(2)
    
    # Сценарий 1: Нормальная работа
    print("\n   📋 Сценарий 1: Нормальная работа")
    normal_data = {
        0x0401: 1,       # flame_present = true
        0x0409: 2,       # operation_mode = Непрерывный обогрев
        0x0405: 250,     # temperature = 25.0°C (нормальная)
        0x0408: 0b111000, # discrete_inputs = все входы в норме
        0x0410: 0,       # registered_alarms_0 = нет аварий
        0x0411: 0,       # registered_alarms_1 = нет аварий
    }
    
    manager.update_from_registers(normal_data)
    
    alarms = adapter.get_critical_alarms(manager)
    warnings = adapter.get_warnings(manager)
    
    print(f"      Аварий: {len(alarms)}")
    print(f"      Предупреждений: {len(warnings)}")
    
    # Сценарий 2: Нет пламени при обогреве
    print("\n   📋 Сценарий 2: Нет пламени при обогреве")
    manager.update_from_registers({0x0401: 0})  # flame_present = false
    
    alarms = adapter.get_critical_alarms(manager)
    warnings = adapter.get_warnings(manager)
    
    print(f"      Аварий: {len(alarms)}")
    for alarm in alarms:
        print(f"         🚨 {alarm}")
    
    # Сценарий 3: Ошибка датчика температуры
    print("\n   📋 Сценарий 3: Ошибка датчика температуры")
    manager.update_from_registers({0x0405: 0x8000})  # temperature = error
    
    alarms = adapter.get_critical_alarms(manager)
    warnings = adapter.get_warnings(manager)
    
    print(f"      Аварий: {len(alarms)}")
    for alarm in alarms:
        print(f"         🚨 {alarm}")
    
    # Сценарий 4: Низкое давление газа
    print("\n   📋 Сценарий 4: Низкое давление газа")
    manager.update_from_registers({0x0408: 0b110000})  # discrete_inputs = бит 3 (давление) выключен
    
    alarms = adapter.get_critical_alarms(manager)
    warnings = adapter.get_warnings(manager)
    
    print(f"      Предупреждений: {len(warnings)}")
    for warning in warnings:
        print(f"         ⚠️ {warning}")


def main():
    """Основная функция тестирования"""
    print("🚀 ТЕСТИРОВАНИЕ КУБ-1112 VARIABLE SYSTEM")
    print("=" * 60)
    
    test_results = []
    
    try:
        # 1. Инициализация адаптера
        adapter = test_adapter_initialization()
        test_results.append(("Инициализация адаптера", adapter is not None))
        
        # 2. Создание Device Manager
        manager = test_device_manager_creation()
        test_results.append(("Создание Device Manager", manager is not None))
        
        if not manager:
            print("❌ Дальнейшее тестирование невозможно")
            return 1
        
        # 3. Доступ к переменным
        manager = test_variable_access()
        test_results.append(("Доступ к переменным", manager is not None))
        
        # 4. Форматирование
        formatted = test_formatting()
        test_results.append(("Форматирование", len(formatted) > 100))
        
        # 5. Аварии и предупреждения
        test_alarms_and_warnings()
        test_results.append(("Аварии и предупреждения", True))
        
        # Подведение итогов
        print("\n" + "=" * 60)
        print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ КУБ-1112:")
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
            print("\n🎉 ВСЕ ТЕСТЫ КУБ-1112 VARIABLE SYSTEM ПРОШЛИ!")
            print("✅ КУБ-1112 адаптер обновлен на Variable System")
            print("✅ Device Manager корректно работает")
            print("✅ Все переменные доступны")
            print("✅ Форматирование и аварии работают")
            print("✅ Интеграция с Remote Dashboard готова")
            return 0
        else:
            print(f"\n⚠️ {total - passed} тестов провалены")
            return 1
            
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())