#!/usr/bin/env python3
"""
Тест для получения сырых данных из регистров без интерпретации
"""

import socket
import struct
import time

def read_raw_register(register_address, host='tcp.cloudpub.ru', port=27521):
    """
    Читает сырые данные из регистра без интерпретации
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
        print(f"📤 Запрос: {request.hex()}")
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
                print(f"📊 Byte Count: {byte_count}")
                
                if byte_count >= 2:
                    data = response[9:9+byte_count]
                    print(f"📊 Data: {data.hex()}")
                    
                    # Получаем сырое значение
                    raw_value = struct.unpack('>H', data[0:2])[0]
                    print(f"📊 Raw Value: {raw_value}")
                    print(f"📊 Raw Value (hex): 0x{raw_value:04X}")
                    print(f"📊 Raw Value (binary): {raw_value:016b}")
                    
                    sock.close()
                    return True, raw_value, data
                else:
                    print(f"❌ Недостаточно данных: {byte_count} байт")
                    sock.close()
                    return False, None, None
                    
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
                return False, None, None
                
            else:
                print(f"❌ Неожиданный код функции: 0x{function_code:02X}")
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
    """Основная функция для получения сырых данных"""
    print("🔍 ТЕСТ СЫРЫХ ДАННЫХ ИЗ РЕГИСТРОВ")
    print("=" * 60)
    
    # Тестируем основные регистры
    test_registers = [
        0x00D5,  # Текущая температура
        0x00D4,  # Целевая температура
        0x0084,  # Относительная влажность
        0x0085,  # Концентрация CO2
        0x0086,  # Концентрация NH3
        0x0083,  # Отрицательное давление
        0x00D0,  # Целевой уровень вентиляции
        0x00D1,  # Фактический уровень вентиляции
        0x00D2,  # Активная схема вентиляции
        0x0301,  # Версия ПО
    ]
    
    results = {}
    
    for reg_addr in test_registers:
        print(f"\n{'='*60}")
        print(f"🔍 Тестирование регистра 0x{reg_addr:04X}")
        print("=" * 60)
        
        success, raw_value, raw_data = read_raw_register(reg_addr)
        
        if success:
            results[f"0x{reg_addr:04X}"] = {
                'raw_value': raw_value,
                'raw_data': raw_data,
                'hex_value': f"0x{raw_value:04X}",
                'binary': f"{raw_value:016b}"
            }
            print(f"✅ УСПЕХ: Сырое значение = {raw_value}")
        else:
            print(f"❌ ОШИБКА: Не удалось прочитать регистр")
        
        time.sleep(0.5)  # Пауза между запросами
    
    # Выводим сводку сырых данных
    print(f"\n{'='*60}")
    print("📋 СВОДКА СЫРЫХ ДАННЫХ")
    print("=" * 60)
    
    if results:
        for reg_addr, data in results.items():
            print(f"• {reg_addr}:")
            print(f"  - Сырое значение: {data['raw_value']}")
            print(f"  - Hex: {data['hex_value']}")
            print(f"  - Binary: {data['binary']}")
            print(f"  - Raw bytes: {data['raw_data'].hex()}")
    else:
        print("❌ Нет данных для отображения")
    
    print("=" * 60)

if __name__ == "__main__":
    main() 