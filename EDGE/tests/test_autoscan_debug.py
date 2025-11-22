#!/usr/bin/env python3
"""
file: EDGE/tests/test_autoscan_debug.py
description: Отладочный тест автосканирования с детальным логированием
author: EDGE Full-Stack RS485 Senior Engineer GPT
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from pymodbus.client import ModbusSerialClient
    try:
        from pymodbus.framer import FramerType
    except Exception:
        FramerType = None
except Exception:
    print("❌ pymodbus не установлен")
    sys.exit(1)

# Импортируем probe definitions
from start_edge import AUTOSCAN_DEVICE_PROBES, _make_reader

def debug_autoscan(port: str, slave_id: int):
    """Отладочное автосканирование с детальным выводом"""

    print(f"🔎 Отладочный автоскан: порт={port}, slave_id={slave_id}")
    print("="*70)

    # Подключаемся
    if FramerType is not None:
        client = ModbusSerialClient(
            port=port,
            framer=FramerType.RTU,
            baudrate=9600,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=0.5
        )
    else:
        client = ModbusSerialClient(
            port=port,
            baudrate=9600,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=0.5
        )

    try:
        if not client.connect():
            print(f"❌ Не удалось подключиться к {port}")
            return

        print(f"✅ Подключено к {port}\n")
        # Создаём reader
        read = _make_reader(client)

        # Проверяем каждый тип устройства
        for device_type, probes in AUTOSCAN_DEVICE_PROBES:
            print(f"📋 Проверка типа: {device_type}")
            print("-" * 70)

            for i, probe in enumerate(probes, 1):
                address = probe["address"]
                kind = probe.get("kind", "holding")
                count = probe.get("count", 1)
                require_non_zero = probe.get("require_non_zero", False)
                expected_value = probe.get("expected_value")

                print(f"  Probe {i}: 0x{address:04X} ({kind})")
                print(f"    count={count}, require_non_zero={require_non_zero}, expected={expected_value}")

                try:
                    # Выполняем чтение
                    result = read(kind, address, count, slave_id)

                    # Проверяем результат
                    if hasattr(result, "isError"):
                        if result.isError():
                            print(f"    ❌ Modbus ошибка")
                            continue

                        registers = getattr(result, "registers", [])
                        if not registers:
                            print(f"    ⚠️ Пустой ответ")
                            continue

                        print(f"    ✅ Прочитано: {registers}")

                        # Проверяем условия
                        if expected_value is not None:
                            if registers[0] == expected_value:
                                print(f"    ✅ Значение совпадает с ожидаемым: {expected_value}")
                            else:
                                print(f"    ❌ Значение {registers[0]} != {expected_value}")
                                continue

                        if require_non_zero:
                            if any(val not in (0, None) for val in registers):
                                print(f"    ✅ Есть не-нулевые значения")
                            else:
                                print(f"    ❌ Все значения нулевые: {registers}")
                                continue

                        print(f"    🎯 PROBE УСПЕШЕН!")
                        print(f"\n✅ УСТРОЙСТВО НАЙДЕНО: {device_type}\n")
                        return device_type

                    else:
                        print(f"    ⚠️ Неожиданный формат ответа: {type(result)}")

                except Exception as e:
                    print(f"    ❌ Исключение: {e}")

            print()

        print("❌ Устройство не распознано")
        return None
    finally:
        # Гарантированно закрываем порт (принудительно для macOS)
        try:
            if hasattr(client, 'socket') and client.socket:
                client.socket.close()
        except Exception:
            pass

        try:
            client.close()
        except Exception:
            pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Отладочный тест автосканирования")
    parser.add_argument("--port", required=True, help="Serial port")
    parser.add_argument("--slave", type=int, required=True, help="Slave ID")

    args = parser.parse_args()

    detected = debug_autoscan(args.port, args.slave)

    if detected:
        print(f"\n{'='*70}")
        print(f"✅ РЕЗУЛЬТАТ: Обнаружено устройство типа {detected}")
        print(f"{'='*70}")
        sys.exit(0)
    else:
        print(f"\n{'='*70}")
        print(f"❌ РЕЗУЛЬТАТ: Устройство не обнаружено")
        print(f"{'='*70}")
        sys.exit(1)
