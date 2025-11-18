#!/usr/bin/env python3
"""
Простой тест RS485 порта
"""

import sys
import time
import os
from pathlib import Path

# Добавляем путь для импортов
sys.path.insert(0, str(Path(__file__).parent))

from modbus.reader import KUB1063Reader

def test_rs485_port():
    """Тест подключения к RS485 порту"""
    port = "/dev/tty.usbserial-2130"
    
    print(f"🔍 Тестируем RS485 порт: {port}")
    
    # Проверяем существование порта
    if not os.path.exists(port):
        print(f"❌ Порт {port} не найден")
        return False
    
    print(f"✅ Порт {port} существует")
    
    # Проверяем права доступа
    try:
        with open(port, 'r+b') as f:
            print(f"✅ Порт {port} доступен для чтения/записи")
    except PermissionError:
        print(f"❌ Нет прав доступа к порту {port}")
        return False
    except Exception as e:
        print(f"⚠️ Ошибка доступа к порту {port}: {e}")
    
    # Тестируем Modbus подключение
    print(f"🔌 Создаем Modbus reader...")
    try:
        reader = KUB1063Reader(
            port=port,
            baudrate=9600,
            slave_id=1,
            timeout=2.0
        )
        print(f"✅ KUB1063Reader создан")
    except Exception as e:
        print(f"❌ Ошибка создания KUB1063Reader: {e}")
        return False
    
    # Тестируем подключение
    print(f"🤝 Пытаемся подключиться...")
    try:
        if reader.connect():
            print(f"✅ Подключение успешно")
            
            # Тестируем чтение
            print(f"📖 Пытаемся прочитать данные...")
            try:
                data = reader.read_all_keep_connection()
                if data:
                    print(f"✅ Данные получены: {data}")
                    return True
                else:
                    print(f"⚠️ Данные не получены (None)")
                    return False
            except Exception as e:
                print(f"❌ Ошибка чтения данных: {e}")
                return False
            finally:
                reader.disconnect()
                print(f"🔒 Соединение закрыто")
        else:
            print(f"❌ Не удалось подключиться")
            return False
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return False

if __name__ == "__main__":
    success = test_rs485_port()
    sys.exit(0 if success else 1)