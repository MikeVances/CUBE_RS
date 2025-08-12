#!/usr/bin/env python3
"""
Простой тест для чтения одного регистра с tcp.cloudpub.ru:27521
"""

import socket
import struct
import time

def read_single_register(register_address, host='tcp.cloudpub.ru', port=27521):
    """
    Читает один регистр по Modbus TCP
    
    Args:
        register_address (int): Адрес регистра (например, 0x0000)
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

def main():
    """Основная функция для тестирования"""
    print("🔍 ПРОСТОЙ ТЕСТ ЧТЕНИЯ РЕГИСТРА")
    print("=" * 50)
    
    # Тестируем несколько регистров
    test_registers = [
        0x0000,  # Текущая температура
        0x0001,  # Влажность
        0x0002,  # CO2
        0x0084,  # Запрошенный регистр
        0x00D5,  # Текущая температура (из документации)
    ]
    
    results = {}
    
    for reg_addr in test_registers:
        print(f"\n{'='*50}")
        success, value, error = read_single_register(reg_addr)
        
        if success:
            results[f"0x{reg_addr:04X}"] = value
            print(f"✅ УСПЕХ: 0x{reg_addr:04X} = {value}")
        else:
            print(f"❌ ОШИБКА: 0x{reg_addr:04X} - {error}")
        
        time.sleep(0.5)  # Пауза между запросами
    
    # Выводим сводку
    print(f"\n{'='*50}")
    print("📋 СВОДКА РЕЗУЛЬТАТОВ")
    print("=" * 50)
    
    if results:
        for reg_addr, value in results.items():
            print(f"• {reg_addr}: 0x{value:04X} ({value})")
    else:
        print("❌ Нет успешных результатов")
    
    print("=" * 50)

if __name__ == "__main__":
    main() 