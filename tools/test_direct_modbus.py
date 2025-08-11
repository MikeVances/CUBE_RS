#!/usr/bin/env python3
"""
Прямой тест чтения Modbus регистров с локальных портов
"""

import socket
import struct
import time

def read_modbus_register(host, port, address):
    """Читает один Modbus регистр"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        
        # Modbus TCP запрос (Read Holding Registers)
        request = struct.pack('>HHHBBHH',
            address,    # Transaction ID
            0x0000,     # Protocol ID
            0x0006,     # Length
            0x01,       # Unit ID
            0x03,       # Function Code (Read Holding Registers)
            address,    # Start Address
            1           # Quantity
        )
        
        sock.send(request)
        response = sock.recv(1024)
        sock.close()
        
        if len(response) >= 11:
            function_code = response[7]
            if function_code == 0x03:
                value = struct.unpack('>H', response[9:11])[0]
                return value
            elif function_code == 0x83:
                error_code = response[8] if len(response) > 8 else 0
                print(f"   ❌ Ошибка Modbus: код {error_code}")
                return None
        
        print(f"   ❌ Неверный ответ: {response.hex()}")
        return None
        
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return None

def test_key_registers():
    """Тестирует ключевые регистры на обоих портах"""
    print("🔍 ПРЯМОЙ ТЕСТ MODBUS РЕГИСТРОВ")
    print("=" * 60)
    
    # Ключевые регистры для тестирования
    registers = [
        (0x00D5, "Температура", "temp"),
        (0x0084, "Влажность", "humidity"), 
        (0x0085, "CO2", "co2"),
        (0x0301, "Версия ПО", "version")
    ]
    
    ports = [
        (5021, "Gateway 1"),
        (5022, "Gateway 2")
    ]
    
    for port, name in ports:
        print(f"\n🔌 Тестирование {name} (порт {port}):")
        print("-" * 40)
        
        working = True
        for addr, desc, reg_type in registers:
            print(f"📖 Читаем {desc} (0x{addr:04X})...")
            value = read_modbus_register("localhost", port, addr)
            
            if value is not None:
                # Форматируем значение
                if reg_type == "temp":
                    formatted = f"{value / 10:.1f}°C"
                elif reg_type == "humidity":
                    formatted = f"{value / 10:.1f}%"
                elif reg_type == "co2":
                    formatted = f"{value} ppm"
                elif reg_type == "version":
                    formatted = f"{value // 100}.{value % 100:02d}"
                else:
                    formatted = str(value)
                
                print(f"   ✅ {desc}: {formatted} (raw: {value})")
                
                # Проверяем что значение не нулевое
                if value == 0:
                    print(f"   ⚠️ ВНИМАНИЕ: Нулевое значение!")
                    
            else:
                print(f"   ❌ {desc}: НЕТ ОТВЕТА")
                working = False
        
        if working:
            print(f"✅ {name} работает корректно")
        else:
            print(f"❌ {name} имеет проблемы")

def test_cloud_simulation():
    """Симулируем запрос как от облачного сервиса"""
    print(f"\n🌐 СИМУЛЯЦИЯ ОБЛАЧНОГО ЗАПРОСА:")
    print("-" * 40)
    
    # Тестируем тот же запрос что делает облачный сервис
    # Читаем несколько регистров подряд (как в оригинальном скрипте)
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        print("📡 Подключение к localhost:5022...")
        sock.connect(('localhost', 5022))
        print("✅ Подключение установлено")

        # Читаем регистры 0x83-0x86 (как в облачном тесте)
        transaction_id = 0x0083
        request = struct.pack('>HHHBBHH',
            transaction_id, 0x0000, 0x0006, 0x01, 0x04, 0x0083, 4
        )
        print("📤 Отправка запроса регистров 0x83-0x86...")
        sock.send(request)
        
        response = sock.recv(1024)
        print(f"📥 Ответ: {response.hex()}")
        
        if len(response) >= 9:
            function_code = response[7]
            if function_code == 0x04:
                byte_count = response[8]
                if byte_count > 0:
                    data = response[9:9+byte_count]
                    print(f"📊 Данные ({byte_count} байт): {data.hex()}")
                    
                    # Парсим значения
                    for i in range(0, len(data), 2):
                        if i + 1 < len(data):
                            reg_addr = 0x0083 + (i // 2)
                            value = struct.unpack('>H', data[i:i+2])[0]
                            
                            if reg_addr == 0x0083:
                                print(f"   0x{reg_addr:04X} (Давление): {value/10:.1f} Па")
                            elif reg_addr == 0x0084:
                                print(f"   0x{reg_addr:04X} (Влажность): {value/10:.1f}%")
                            elif reg_addr == 0x0085:
                                print(f"   0x{reg_addr:04X} (CO2): {value} ppm")
                            elif reg_addr == 0x0086:
                                print(f"   0x{reg_addr:04X} (NH3): {value/10:.1f} ppm")
                else:
                    print("❌ Нет данных в ответе")
            else:
                print(f"❌ Неожиданный код функции: 0x{function_code:02X}")
        else:
            print("❌ Слишком короткий ответ")
            
        sock.close()
        print("✅ Соединение закрыто")
        
    except Exception as e:
        print(f"❌ Ошибка симуляции: {e}")

if __name__ == "__main__":
    test_key_registers()
    test_cloud_simulation()
