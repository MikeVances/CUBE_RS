#!/usr/bin/env python3
"""
Тест для проверки разных функций Modbus
"""

import socket
import struct
import time

def read_register_with_function(register_address, function_code, host='tcp.cloudpub.ru', port=27521):
    """
    Читает регистр с указанной функцией Modbus
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
            transaction_id, 0x0000, 0x0006, 0x01, function_code, register_address, 1
        )
        
        function_name = "Read Holding Registers" if function_code == 0x03 else "Read Input Registers"
        print(f"📤 Чтение регистра 0x{register_address:04X} (функция 0x{function_code:02X} - {function_name})...")
        print(f"📤 Запрос: {request.hex()}")
        sock.send(request)
        
        # Получаем ответ
        response = sock.recv(1024)
        print(f"📥 Ответ: {response.hex()}")
        
        # Анализируем ответ
        if len(response) >= 9:
            response_function = response[7]
            print(f"📊 Response Function Code: 0x{response_function:02X}")
            
            if response_function == function_code:
                # Успешный ответ
                byte_count = response[8]
                print(f"📊 Byte Count: {byte_count}")
                
                if byte_count >= 2:
                    data = response[9:9+byte_count]
                    print(f"📊 Data: {data.hex()}")
                    
                    # Получаем сырое значение
                    raw_value = struct.unpack('>H', data[0:2])[0]
                    print(f"📊 Raw Value: {raw_value} (0x{raw_value:04X})")
                    
                    sock.close()
                    return True, raw_value, data
                else:
                    print(f"❌ Недостаточно данных: {byte_count} байт")
                    sock.close()
                    return False, None, None
                    
            elif response_function == 0x80 + function_code:
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
                return False, None, None
                
            else:
                print(f"❌ Неожиданный код функции: 0x{response_function:02X}")
                sock.close()
                return False, None, None
        else:
            print(f"❌ Слишком короткий ответ: {len(response)} байт")
            sock.close()
            return False, None, None
            
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return False, None, None

def main():
    """Основная функция для тестирования функций"""
    print("🔍 ТЕСТ РАЗНЫХ ФУНКЦИЙ MODBUS")
    print("=" * 60)
    
    # Тестируем регистры с разными функциями
    test_cases = [
        # (адрес, функция, описание)
        (0x00D5, 0x03, "Текущая температура (Holding)"),
        (0x00D5, 0x04, "Текущая температура (Input)"),
        (0x0084, 0x03, "Влажность (Holding)"),
        (0x0084, 0x04, "Влажность (Input)"),
        (0x0085, 0x03, "CO2 (Holding)"),
        (0x0085, 0x04, "CO2 (Input)"),
        (0x0301, 0x03, "Версия ПО (Holding)"),
        (0x0301, 0x04, "Версия ПО (Input)"),
    ]
    
    results = {}
    
    for reg_addr, func_code, description in test_cases:
        print(f"\n{'='*60}")
        print(f"🔍 Тестирование: {description}")
        print(f"📍 Адрес: 0x{reg_addr:04X}, Функция: 0x{func_code:02X}")
        print("=" * 60)
        
        success, raw_value, raw_data = read_register_with_function(reg_addr, func_code)
        
        if success:
            key = f"0x{reg_addr:04X}_0x{func_code:02X}"
            results[key] = {
                'description': description,
                'raw_value': raw_value,
                'function': func_code
            }
            print(f"✅ УСПЕХ: {raw_value} (0x{raw_value:04X})")
        else:
            print(f"❌ ОШИБКА: Не удалось прочитать регистр")
        
        time.sleep(0.5)  # Пауза между запросами
    
    # Выводим сводку
    print(f"\n{'='*60}")
    print("📋 СВОДКА РЕЗУЛЬТАТОВ")
    print("=" * 60)
    
    if results:
        for key, data in results.items():
            print(f"• {data['description']}: {data['raw_value']} (функция 0x{data['function']:02X})")
    else:
        print("❌ Нет успешных результатов")
    
    print("=" * 60)

if __name__ == "__main__":
    main() 