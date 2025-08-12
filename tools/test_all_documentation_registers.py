#!/usr/bin/env python3
"""
Тест всех регистров из документации КУБ-1063
"""

import socket
import struct
import time

# Все регистры из документации КУБ-1063
REGISTER_MAP = {
    # Регистры ввода (функция 0x04)
    0x0301: ('Версия ПО', 'version'),
    0x0081: ('Состояние цифровых выходов (1)', 'raw'),
    0x0082: ('Состояние цифровых выходов (2)', 'raw'),
    0x00A2: ('Состояние цифровых выходов (3)', 'raw'),
    0x0083: ('Отрицательное давление', 'pressure'),
    0x0084: ('Относительная влажность', 'humidity'),
    0x0085: ('Концентрация CO2', 'co2'),
    0x0086: ('Концентрация NH3', 'nh3'),
    0x0087: ('Выход управления ГРВ базовой вентиляции', 'raw'),
    0x0088: ('Выход управления ГРВ туннельной вентиляции', 'raw'),
    0x0089: ('Выход управления демпфером', 'raw'),
    0x00C3: ('Активные аварии', 'raw'),
    0x00C7: ('Зарегистрированные аварии', 'raw'),
    0x00CB: ('Активные предупреждения', 'raw'),
    0x00CF: ('Зарегистрированные предупреждения', 'raw'),
    0x00D0: ('Целевой уровень вентиляции', 'raw'),
    0x00D1: ('Фактический уровень вентиляции', 'raw'),
    0x00D2: ('Активная схема вентиляции', 'scheme'),
    0x00D3: ('Счетчик дней', 'raw'),
    0x00D4: ('Целевая температура', 'temperature'),
    0x00D5: ('Текущая температура', 'temperature'),
    0x00D6: ('Температура активации вентиляции', 'temperature'),
    
    # Регистры хранения (функция 0x03)
    0x0020: ('Сброс зарегистрированных аварий и предупреждений', 'raw'),
    0x003F: ('Часовой пояс', 'raw'),
}

def format_value(value, unit_type):
    """Форматирует значение в зависимости от типа единиц измерения"""
    if unit_type == 'raw':
        return f"{value}"
    elif unit_type == 'temperature':
        return f"{value / 10:.1f}°C"
    elif unit_type == 'humidity':
        return f"{value / 10:.1f}%"
    elif unit_type == 'pressure':
        return f"{value / 10:.1f} Па"
    elif unit_type == 'co2':
        return f"{value} ppm"
    elif unit_type == 'nh3':
        return f"{value / 10:.1f} ppm"
    elif unit_type == 'version':
        return f"{value / 100:.2f}"
    elif unit_type == 'scheme':
        schemes = {0: "Базовая", 1: "Туннельная"}
        return schemes.get(value, f"Неизвестно ({value})")
    else:
        return f"{value}"

def read_register_with_function(register_address, function_code, host='tcp.cloudpub.ru', port=27521):
    """Читает регистр с указанной функцией Modbus"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((host, port))
        
        # Формируем Modbus TCP запрос
        transaction_id = (register_address & 0xFFFF)
        request = struct.pack('>HHHBBHH',
            transaction_id, 0x0000, 0x0006, 0x01, function_code, register_address, 1
        )
        
        sock.send(request)
        response = sock.recv(1024)
        
        if len(response) >= 9:
            response_function = response[7]
            
            if response_function == function_code:
                byte_count = response[8]
                if byte_count >= 2:
                    data = response[9:9+byte_count]
                    raw_value = struct.unpack('>H', data[0:2])[0]
                    sock.close()
                    return True, raw_value, data
                    
            elif response_function == 0x80 + function_code:
                error_code = response[8] if len(response) > 8 else 0
                sock.close()
                return False, None, f"Ошибка {error_code}"
                
        sock.close()
        return False, None, "Неожиданный ответ"
        
    except Exception as e:
        return False, None, str(e)

def test_all_registers():
    """Тестирует все регистры из документации"""
    print("🔍 ТЕСТ ВСЕХ РЕГИСТРОВ ИЗ ДОКУМЕНТАЦИИ КУБ-1063")
    print("=" * 80)
    print("🌐 Сервер: tcp.cloudpub.ru:27521")
    print("=" * 80)
    
    results = {
        'input_registers': {},   # Функция 0x04
        'holding_registers': {}  # Функция 0x03
    }
    
    # Тестируем регистры ввода (функция 0x04)
    print("\n📋 ТЕСТИРОВАНИЕ РЕГИСТРОВ ВВОДА (функция 0x04)")
    print("-" * 80)
    
    input_registers = [
        0x0301, 0x0081, 0x0082, 0x00A2, 0x0083, 0x0084, 0x0085, 0x0086,
        0x0087, 0x0088, 0x0089, 0x00C3, 0x00C7, 0x00CB, 0x00CF, 0x00D0,
        0x00D1, 0x00D2, 0x00D3, 0x00D4, 0x00D5, 0x00D6
    ]
    
    for reg_addr in input_registers:
        if reg_addr in REGISTER_MAP:
            desc, unit_type = REGISTER_MAP[reg_addr]
            print(f"\n🔍 Тестирование: {desc}")
            print(f"📍 Адрес: 0x{reg_addr:04X}, Функция: 0x04")
            
            success, raw_value, error = read_register_with_function(reg_addr, 0x04)
            
            if success:
                formatted_value = format_value(raw_value, unit_type)
                print(f"✅ УСПЕХ: {formatted_value} (0x{raw_value:04X})")
                results['input_registers'][reg_addr] = {
                    'description': desc,
                    'raw_value': raw_value,
                    'formatted_value': formatted_value,
                    'unit_type': unit_type
                }
            else:
                print(f"❌ ОШИБКА: {error}")
            
            time.sleep(0.2)
    
    # Тестируем регистры хранения (функция 0x03)
    print("\n\n📋 ТЕСТИРОВАНИЕ РЕГИСТРОВ ХРАНЕНИЯ (функция 0x03)")
    print("-" * 80)
    
    holding_registers = [0x0020, 0x003F]
    
    for reg_addr in holding_registers:
        if reg_addr in REGISTER_MAP:
            desc, unit_type = REGISTER_MAP[reg_addr]
            print(f"\n🔍 Тестирование: {desc}")
            print(f"📍 Адрес: 0x{reg_addr:04X}, Функция: 0x03")
            
            success, raw_value, error = read_register_with_function(reg_addr, 0x03)
            
            if success:
                formatted_value = format_value(raw_value, unit_type)
                print(f"✅ УСПЕХ: {formatted_value} (0x{raw_value:04X})")
                results['holding_registers'][reg_addr] = {
                    'description': desc,
                    'raw_value': raw_value,
                    'formatted_value': formatted_value,
                    'unit_type': unit_type
                }
            else:
                print(f"❌ ОШИБКА: {error}")
            
            time.sleep(0.2)
    
    # Выводим сводку
    print("\n" + "=" * 80)
    print("📋 СВОДКА РЕЗУЛЬТАТОВ")
    print("=" * 80)
    
    if results['input_registers']:
        print("\n🌡️ РЕГИСТРЫ ВВОДА (функция 0x04):")
        print("-" * 40)
        for reg_addr, data in sorted(results['input_registers'].items()):
            print(f"• 0x{reg_addr:04X} - {data['description']}: {data['formatted_value']}")
    
    if results['holding_registers']:
        print("\n⚙️ РЕГИСТРЫ ХРАНЕНИЯ (функция 0x03):")
        print("-" * 40)
        for reg_addr, data in sorted(results['holding_registers'].items()):
            print(f"• 0x{reg_addr:04X} - {data['description']}: {data['formatted_value']}")
    
    # Статистика
    total_tested = len(input_registers) + len(holding_registers)
    total_success = len(results['input_registers']) + len(results['holding_registers'])
    
    print(f"\n📊 СТАТИСТИКА:")
    print(f"• Всего протестировано: {total_tested}")
    print(f"• Успешно прочитано: {total_success}")
    print(f"• Процент успеха: {(total_success/total_tested)*100:.1f}%")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    test_all_registers() 