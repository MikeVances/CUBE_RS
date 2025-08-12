#!/usr/bin/env python3
"""
Отладочный тест для проверки чтения регистра 0x00D5
"""

import socket
import struct
import time

def read_single_register_debug(register_address, host='tcp.cloudpub.ru', port=27521):
    """
    Читает один регистр с подробной отладочной информацией
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
        
        # Подробный анализ ответа
        if len(response) >= 9:
            print(f"📊 Анализ ответа:")
            print(f"   Длина ответа: {len(response)} байт")
            print(f"   Transaction ID: 0x{response[0:2].hex()}")
            print(f"   Protocol ID: 0x{response[2:4].hex()}")
            print(f"   Length: 0x{response[4:6].hex()}")
            print(f"   Unit ID: 0x{response[6]:02X}")
            print(f"   Function Code: 0x{response[7]:02X}")
            
            function_code = response[7]
            
            if function_code == 0x03:
                # Успешный ответ
                byte_count = response[8]
                print(f"   Byte Count: {byte_count}")
                
                if byte_count >= 2:
                    data = response[9:9+byte_count]
                    print(f"   Data: {data.hex()}")
                    
                    value = struct.unpack('>H', data[0:2])[0]
                    print(f"   Raw Value: {value} (0x{value:04X})")
                    
                    # Форматируем значение
                    if register_address == 0x00D5:
                        formatted_value = f"{value / 10:.1f}°C"
                    else:
                        formatted_value = f"{value}"
                    
                    print(f"   Formatted Value: {formatted_value}")
                    sock.close()
                    return True, value, formatted_value
                else:
                    print(f"   ❌ Недостаточно данных: {byte_count} байт")
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
                print(f"   ❌ Ошибка Modbus: {error_msg}")
                sock.close()
                return False, None, None
                
            else:
                print(f"   ❌ Неожиданный код функции: 0x{function_code:02X}")
                sock.close()
                return False, None, None
        else:
            print(f"   ❌ Слишком короткий ответ: {len(response)} байт")
            sock.close()
            return False, None, None
            
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return False, None, None

def main():
    """Основная функция для отладки"""
    print("🔍 ОТЛАДОЧНЫЙ ТЕСТ РЕГИСТРА 0x00D5")
    print("=" * 60)
    
    # Тестируем регистр 0x00D5 (Текущая температура)
    register_addr = 0x00D5
    print(f"🎯 Тестирование регистра 0x{register_addr:04X} (Текущая температура)")
    print("=" * 60)
    
    success, raw_value, formatted_value = read_single_register_debug(register_addr)
    
    print("\n" + "=" * 60)
    print("📋 РЕЗУЛЬТАТ ОТЛАДКИ")
    print("=" * 60)
    
    if success:
        print(f"✅ УСПЕХ:")
        print(f"   Регистр: 0x{register_addr:04X}")
        print(f"   Сырое значение: {raw_value} (0x{raw_value:04X})")
        print(f"   Форматированное: {formatted_value}")
        
        if raw_value == 0:
            print(f"   ⚠️ ВНИМАНИЕ: Значение равно 0!")
            print(f"   Возможные причины:")
            print(f"   - КУБ не подключен к серверу")
            print(f"   - КУБ в режиме ожидания")
            print(f"   - Датчик температуры отключен")
            print(f"   - Нормальное состояние для данного КУБ")
    else:
        print(f"❌ ОШИБКА: Не удалось прочитать регистр 0x{register_addr:04X}")
    
    print("=" * 60)

if __name__ == "__main__":
    main() 