#!/usr/bin/env python3
"""
Тест различных настроек RS485 для КУБ-1063
"""

import serial
import time
import sys
from pathlib import Path

# Добавляем путь для импортов
sys.path.insert(0, str(Path(__file__).parent))

def test_serial_settings():
    """Тест различных настроек serial порта"""
    port = "/dev/tty.usbserial-2130"
    
    # Проверяем что порт существует
    import os
    if not os.path.exists(port):
        print(f"❌ Порт {port} не найден")
        return False
    
    print(f"🔍 Тестируем различные настройки для {port}")
    
    # Различные варианты настроек
    settings_variants = [
        # Стандартные настройки
        {"baudrate": 9600, "parity": serial.PARITY_NONE, "name": "9600 8N1"},
        {"baudrate": 9600, "parity": serial.PARITY_EVEN, "name": "9600 8E1"},
        {"baudrate": 9600, "parity": serial.PARITY_ODD, "name": "9600 8O1"},
        
        # Другие скорости
        {"baudrate": 19200, "parity": serial.PARITY_NONE, "name": "19200 8N1"},
        {"baudrate": 19200, "parity": serial.PARITY_EVEN, "name": "19200 8E1"},
        
        {"baudrate": 38400, "parity": serial.PARITY_NONE, "name": "38400 8N1"},
        {"baudrate": 38400, "parity": serial.PARITY_EVEN, "name": "38400 8E1"},
    ]
    
    successful_connections = []
    
    for settings in settings_variants:
        print(f"\n🔧 Тестируем {settings['name']}...")
        
        try:
            # Пытаемся открыть порт с таймаутом
            ser = serial.Serial(
                port=port,
                baudrate=settings["baudrate"],
                bytesize=serial.EIGHTBITS,
                parity=settings["parity"],
                stopbits=serial.STOPBITS_ONE,
                timeout=1.0,  # Короткий таймаут
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            
            print(f"✅ Порт открыт успешно")
            
            # Пытаемся отправить простой Modbus запрос
            # Чтение версии ПО КУБ-1063 (регистр 0x0301)
            # Slave ID = 1, Function = 0x04 (Read Input Registers), Address = 0x0301, Count = 1
            request = bytes([0x01, 0x04, 0x03, 0x01, 0x00, 0x01])
            
            # Добавляем CRC
            import crcmod
            crc16 = crcmod.predefined.mkPredefinedCrcFun("modbus")
            crc = crc16(request)
            request += crc.to_bytes(2, byteorder='little')
            
            print(f"📤 Отправляем запрос: {request.hex()}")
            
            # Очищаем буфер
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            
            # Отправляем запрос
            ser.write(request)
            
            # Ждем ответ
            time.sleep(0.1)
            response = ser.read(100)  # Читаем до 100 байт
            
            if response:
                print(f"📥 Получен ответ: {response.hex()}")
                if len(response) >= 7:  # Минимальная длина корректного ответа
                    successful_connections.append(settings['name'])
                    print(f"✅ Успешная связь с {settings['name']}")
                else:
                    print(f"⚠️ Короткий ответ: {len(response)} байт")
            else:
                print(f"❌ Нет ответа")
            
            ser.close()
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
        
        # Пауза между тестами
        time.sleep(0.5)
    
    print(f"\n📊 РЕЗУЛЬТАТЫ:")
    if successful_connections:
        print(f"✅ Успешные настройки:")
        for setting in successful_connections:
            print(f"  • {setting}")
    else:
        print(f"❌ Ни одна настройка не сработала")
        print(f"🔍 Возможные причины:")
        print(f"  • Устройство не подключено")
        print(f"  • Неправильный slave_id (попробуйте 1-247)")
        print(f"  • Устройство в другом режиме")
        print(f"  • Проблемы с кабелем RS485")
    
    return len(successful_connections) > 0

if __name__ == "__main__":
    success = test_serial_settings()
    sys.exit(0 if success else 1)