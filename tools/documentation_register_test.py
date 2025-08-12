#!/usr/bin/env python3
"""
Тест регистров из документации КУБ-1063
"""

import socket
import struct
import time

def read_single_register(register_address, host='tcp.cloudpub.ru', port=27521):
    """
    Читает один регистр по Modbus TCP
    
    Args:
        register_address (int): Адрес регистра
        host (str): Хост сервера
        port (int): Порт сервера
    
    Returns:
        tuple: (success, value, error_message)
    """
    try:
        # Создаем сокет
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        
        print(f"📡 Подключение к {host}:{port}...")
        sock.connect((host, port))
        print("✅ Подключение установлено")
        
        # Формируем Modbus TCP запрос
        transaction_id = (register_address & 0xFFFF)
        request = struct.pack('>HHHBBHH',
            transaction_id, 0x0000, 0x0006, 0x01, 0x03, register_address, 1
        )
        
        print(f"📤 Чтение регистра 0x{register_address:04X}...")
        sock.send(request)
        
        # Получаем ответ
        response = sock.recv(1024)
        print(f"📥 Ответ: {response.hex()}")
        
        # Анализируем ответ
        if len(response) >= 9:
            function_code = response[7]
            
            if function_code == 0x03:
                # Успешный ответ
                byte_count = response[8]
                if byte_count >= 2:
                    value = struct.unpack('>H', response[9:11])[0]
                    print(f"✅ Регистр 0x{register_address:04X} = 0x{value:04X} ({value})")
                    sock.close()
                    return True, value, None
                else:
                    error_msg = "Недостаточно данных в ответе"
                    print(f"❌ {error_msg}")
                    sock.close()
                    return False, None, error_msg
                    
            elif function_code == 0x83:
                # Ошибка Modbus
                error_code = response[8] if len(response) > 8 else 0
                error_messages = {
                    1: "Неподдерживаемая функция",
                    2: "Неправильный адрес регистра", 
                    3: "Неправильное количество регистров",
                    4: "Ошибка устройства"
                }
                error_msg = error_messages.get(error_code, f"Неизвестная ошибка ({error_code})")
                print(f"❌ Ошибка Modbus: {error_msg}")
                sock.close()
                return False, None, error_msg
                
            else:
                error_msg = f"Неожиданный код функции: 0x{function_code:02X}"
                print(f"❌ {error_msg}")
                sock.close()
                return False, None, error_msg
        else:
            error_msg = "Слишком короткий ответ"
            print(f"❌ {error_msg}")
            sock.close()
            return False, None, error_msg
            
    except Exception as e:
        error_msg = f"Ошибка подключения: {e}"
        print(f"❌ {error_msg}")
        return False, None, error_msg

def format_value(value, unit_type):
    """Форматирует значение в зависимости от типа единиц измерения"""
    if unit_type == 'temperature':
        return f"{value / 10:.1f}°C"
    elif unit_type == 'humidity':
        return f"{value / 10:.1f}%"
    elif unit_type == 'co2':
        return f"{value} ppm"
    elif unit_type == 'pressure':
        return f"{value / 10:.1f} Па"
    elif unit_type == 'nh3':
        return f"{value / 10:.1f} ppm"
    elif unit_type == 'version':
        return f"{value / 100:.2f}"
    elif unit_type == 'raw':
        return f"{value}"
    else:
        return f"{value}"

def main():
    """Основная функция для тестирования регистров из документации"""
    print("🔍 ТЕСТ РЕГИСТРОВ ИЗ ДОКУМЕНТАЦИИ КУБ-1063")
    print("=" * 60)
    
    # Регистры из документации КУБ-1063
    test_registers = [
        (0x0301, "Версия ПО", 'version'),
        (0x0083, "Отрицательное давление", 'pressure'),
        (0x0084, "Относительная влажность", 'humidity'),
        (0x0085, "Концентрация CO2", 'co2'),
        (0x0086, "Концентрация NH3", 'nh3'),
        (0x00D0, "Целевой уровень вентиляции", 'raw'),
        (0x00D1, "Фактический уровень вентиляции", 'raw'),
        (0x00D2, "Активная схема вентиляции", 'raw'),
        (0x00D4, "Целевая температура", 'temperature'),
        (0x00D5, "Текущая температура", 'temperature'),
        (0x00D6, "Температура активации вентиляции", 'temperature'),
    ]
    
    results = {}
    
    for reg_addr, description, unit_type in test_registers:
        print(f"\n{'='*60}")
        print(f"🔍 Тестирование: {description}")
        print(f"📍 Адрес: 0x{reg_addr:04X}")
        print(f"📊 Тип: {unit_type}")
        
        success, value, error = read_single_register(reg_addr)
        
        if success:
            formatted_value = format_value(value, unit_type)
            results[f"0x{reg_addr:04X}"] = {
                'description': description,
                'raw_value': value,
                'formatted_value': formatted_value,
                'unit_type': unit_type
            }
            print(f"✅ УСПЕХ: {formatted_value}")
        else:
            print(f"❌ ОШИБКА: {error}")
        
        time.sleep(0.5)  # Пауза между запросами
    
    # Выводим сводку
    print(f"\n{'='*60}")
    print("📋 СВОДКА РЕЗУЛЬТАТОВ")
    print("=" * 60)
    
    if results:
        # Группируем по категориям
        categories = {
            "🌡️ ТЕМПЕРАТУРА": [],
            "💧 ВЛАЖНОСТЬ": [],
            "🌬️ ДАВЛЕНИЕ": [],
            "🌿 ГАЗЫ": [],
            "⚙️ УПРАВЛЕНИЕ": [],
            "📊 СИСТЕМА": []
        }
        
        for reg_addr, data in results.items():
            desc = data['description']
            if 'температура' in desc.lower():
                categories["🌡️ ТЕМПЕРАТУРА"].append((reg_addr, data))
            elif 'влажность' in desc.lower():
                categories["💧 ВЛАЖНОСТЬ"].append((reg_addr, data))
            elif 'давление' in desc.lower():
                categories["🌬️ ДАВЛЕНИЕ"].append((reg_addr, data))
            elif 'co2' in desc.lower() or 'nh3' in desc.lower():
                categories["🌿 ГАЗЫ"].append((reg_addr, data))
            elif 'вентиляция' in desc.lower() or 'уровень' in desc.lower():
                categories["⚙️ УПРАВЛЕНИЕ"].append((reg_addr, data))
            else:
                categories["📊 СИСТЕМА"].append((reg_addr, data))
        
        for category, items in categories.items():
            if items:
                print(f"\n{category}:")
                for reg_addr, data in items:
                    print(f"   • {data['description']}: {data['formatted_value']} (0x{reg_addr})")
    else:
        print("❌ Нет успешных результатов")
    
    print("=" * 60)

if __name__ == "__main__":
    main() 