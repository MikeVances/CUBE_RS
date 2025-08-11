#!/usr/bin/env python3
"""
Тест облачного Modbus TCP - ИСПРАВЛЕННАЯ ВЕРСИЯ
"""

import socket
import struct
import time

# Регистры КУБ-1063
REGISTER_MAP = [
    (0x00D5, 'Текущая температура', 'temperature'),
    (0x00D4, 'Целевая температура', 'temperature'),
    (0x0084, 'Относительная влажность', 'humidity'),
    (0x0085, 'Концентрация CO2', 'co2'),
    (0x0086, 'Концентрация NH3', 'nh3'),
    (0x0083, 'Отрицательное давление', 'pressure'),
    (0x00D0, 'Целевой уровень вентиляции', 'ventilation'),
    (0x00D1, 'Фактический уровень вентиляции', 'ventilation'),
    (0x00D2, 'Активная схема вентиляции', 'scheme'),
    (0x0301, 'Версия ПО', 'version'),
]

ADDR_TO_DESC = {addr: (desc, unit) for addr, desc, unit in REGISTER_MAP}

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
    elif unit_type == 'ventilation':
        return f"{value / 10:.1f}%"
    elif unit_type == 'scheme':
        schemes = {0: "Базовая", 1: "Туннельная"}
        return schemes.get(value, f"Неизвестно ({value})")
    elif unit_type == 'version':
        return f"{value // 100}.{value % 100:02d}"
    else:
        return f"{value}"

def test_modbus():
    print("🔍 ТЕСТИРОВАНИЕ MODBUS TCP")
    print("=" * 60)
    print("🎯 Цель: Чтение регистров КУБ-1063")
    print("🌐 Сервер: tcp.cloudpub.ru:16212")
    print("=" * 60)
    
    results = {}
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        print("📡 Подключение к серверу...")
        sock.connect(('tcp.cloudpub.ru', 16212))
        print("✅ Подключение установлено")

        # Группируем чтение по 10 регистров подряд
        addresses = [addr for addr, _, _ in REGISTER_MAP]
        addresses = sorted(set(addresses))
        
        i = 0
        while i < len(addresses):
            start_addr = addresses[i]
            # Считаем сколько подряд идущих адресов можно прочитать (максимум 10)
            quantity = 1
            for j in range(i+1, min(i+10, len(addresses))):
                if addresses[j] == addresses[j-1] + 1:
                    quantity += 1
                else:
                    break
                    
            transaction_id = (start_addr & 0xFFFF)
            request = struct.pack('>HHHBBHH',
                transaction_id, 0x0000, 0x0006, 0x01, 0x04, start_addr, quantity
            )
            
            print(f"\n📤 Чтение регистров {hex(start_addr)} - {hex(start_addr+quantity-1)}...")
            sock.send(request)
            response = sock.recv(1024)
            print(f"📥 Ответ: {response.hex()}")
            
            if len(response) >= 9:
                function_code = response[7]
                if function_code == 0x04:
                    # Успешный ответ
                    byte_count = response[8]
                    if byte_count > 0:
                        data = response[9:9+byte_count]
                        for k in range(0, len(data), 2):
                            if i + (k//2) < len(addresses):
                                reg_addr = start_addr + (k//2)
                                reg_value = struct.unpack('>H', data[k:k+2])[0]
                                desc_info = ADDR_TO_DESC.get(reg_addr, ('Неизвестный регистр', 'raw'))
                                desc, unit_type = desc_info
                                formatted_value = format_value(reg_value, unit_type)
                                print(f"   ✅ {desc}: {formatted_value} (0x{reg_value:04X})")
                                results[desc] = formatted_value
                                
                elif function_code == 0x84:
                    # Ошибка чтения регистров
                    error_code = response[8] if len(response) > 8 else 0
                    error_messages = {
                        1: "Неподдерживаемая функция",
                        2: "Неправильный адрес регистра", 
                        3: "Неправильное количество регистров",
                        4: "Ошибка устройства"
                    }
                    error_msg = error_messages.get(error_code, f"Неизвестная ошибка ({error_code})")
                    print(f"   ❌ Ошибка чтения регистров {hex(start_addr)}: {error_msg}")
                else:
                    print(f"   ⚠️ Неожиданный код функции: 0x{function_code:02X}")
                    
            i += quantity
            time.sleep(0.2)
            
        sock.close()
        print("✅ Соединение закрыто")
        
        # Выводим подробную сводку
        if results:
            print("\n" + "=" * 60)
            print("📋 СВОДКА ПОКАЗАНИЙ КУБ-1063")
            print("=" * 60)
            
            # ИСПРАВЛЕННЫЕ категории с правильными названиями
            categories = {
                "🌡️ ТЕМПЕРАТУРА": [
                    "Текущая температура",
                    "Целевая температура"
                ],
                "💧 ВЛАЖНОСТЬ И ДАВЛЕНИЕ": [
                    "Относительная влажность",  # ИСПРАВЛЕНО
                    "Отрицательное давление"
                ],
                "🌬️ ГАЗЫ": [
                    "Концентрация CO2",  # ИСПРАВЛЕНО
                    "Концентрация NH3"
                ],
                "⚙️ ВЕНТИЛЯЦИЯ": [
                    "Целевой уровень вентиляции",
                    "Фактический уровень вентиляции", 
                    "Активная схема вентиляции"
                ],
                "🔧 СИСТЕМА": [
                    "Версия ПО"
                ]
            }
            
            for category, items in categories.items():
                print(f"\n{category}:")
                category_has_data = False
                for item in items:
                    if item in results:
                        print(f"   • {item}: {results[item]}")
                        category_has_data = True
                
                if not category_has_data:
                    print("   • Нет данных")
            
            # Дополнительная информация
            print(f"\n📊 СТАТИСТИКА:")
            print(f"   • Всего параметров: {len(REGISTER_MAP)}")
            print(f"   • Получено данных: {len(results)}")
            print(f"   • Успешность: {len(results)/len(REGISTER_MAP)*100:.1f}%")
            
            print("\n" + "=" * 60)
            print("✅ Тест завершен успешно!")
        else:
            print("❌ Нет данных для отображения")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    test_modbus()