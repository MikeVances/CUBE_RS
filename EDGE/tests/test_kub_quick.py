#!/usr/bin/env python3
"""
Быстрый тест КУБ-1063 - читает только ключевые регистры
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


def read_input_register(client, slave_id: int, address: int, description: str = ""):
    """Чтение одного Input Register (FC04)"""
    try:
        result = client.read_input_registers(address=address, count=1, slave=slave_id)
        if hasattr(result, 'isError') and not result.isError():
            registers = getattr(result, 'registers', [])
            if registers:
                return registers[0]
        return None
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
        return None


def test_kub_quick(port: str, slave_id: int):
    """Быстрый тест ключевых регистров КУБ-1063"""

    print("="*70)
    print(f"🔎 БЫСТРЫЙ ТЕСТ КУБ-1063 (slave_id={slave_id})")
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
            return False

        print(f"✅ Подключено к {port}\n")

        # Тестовые регистры
        test_registers = [
            (0x0301, "Версия ПО", lambda x: f"{x/100:.2f}"),
            (0x0302, "Заводской номер", lambda x: f"0x{x:04X}"),
            (0x0303, "Номер устройства", lambda x: str(x)),
            (0x0081, "Цифровые выходы 1", lambda x: f"0x{x:04X}"),
            (0x0082, "Цифровые выходы 2", lambda x: f"0x{x:04X}"),
            (0x00A2, "Цифровые выходы 3", lambda x: f"0x{x:04X}"),
            (0x0083, "Давление", lambda x: f"{x*0.1:.1f} Па" if x < 0xFFFC else f"Спец: 0x{x:04X}"),
            (0x0084, "Влажность", lambda x: f"{x*0.1:.1f} %" if x < 0xFFFC else f"Спец: 0x{x:04X}"),
            (0x0085, "CO2", lambda x: f"{x} ppm" if x < 0xFFFC else f"Спец: 0x{x:04X}"),
            (0x0086, "NH3", lambda x: f"{x*0.1:.1f} ppm" if x < 0xFFFC else f"Спец: 0x{x:04X}"),
            (0x008D, "Температура внутри 1", lambda x: f"{(x if x < 0x8000 else x - 0x10000)*0.1:.1f} °C" if x < 0x7FFC else f"Спец: 0x{x:04X}"),
            (0x008E, "Температура внутри 2", lambda x: f"{(x if x < 0x8000 else x - 0x10000)*0.1:.1f} °C" if x < 0x7FFC else f"Спец: 0x{x:04X}"),
            (0x008F, "Температура снаружи", lambda x: f"{(x if x < 0x8000 else x - 0x10000)*0.1:.1f} °C" if x < 0x7FFC else f"Спец: 0x{x:04X}"),
            (0x00C0, "Активные аварии 0", lambda x: f"0x{x:04X}"),
            (0x00C1, "Активные аварии 1", lambda x: f"0x{x:04X}"),
            (0x00C2, "Активные аварии 2", lambda x: f"0x{x:04X}"),
            (0x00C3, "Активные аварии 3", lambda x: f"0x{x:04X}"),
            (0x00D0, "Целевой уровень вентиляции", lambda x: f"{x*0.1:.1f} %"),
            (0x00D1, "Фактический уровень вентиляции", lambda x: f"{x*0.1:.1f} %"),
            (0x00D2, "Схема вентиляции", lambda x: "Базовая" if x == 0 else "Туннельная"),
            (0x00D3, "Счетчик дней", lambda x: str(x if x < 0x8000 else x - 0x10000) if x != 0x7FFF else "Отключен"),
        ]

        success_count = 0
        fail_count = 0

        for addr, desc, formatter in test_registers:
            value = read_input_register(client, slave_id, addr, desc)
            if value is not None:
                formatted = formatter(value)
                print(f"  ✅ 0x{addr:04X} {desc:30s} = {formatted}")
                success_count += 1
            else:
                print(f"  ❌ 0x{addr:04X} {desc:30s} = ОШИБКА ЧТЕНИЯ")
                fail_count += 1

        print("\n" + "="*70)
        print(f"ИТОГО: ✅ {success_count} успешно, ❌ {fail_count} ошибок")
        print("="*70)

        return fail_count == 0

    finally:
        # Принудительное закрытие порта (для macOS)
        try:
            if hasattr(client, 'socket') and client.socket:
                client.socket.close()
        except Exception:
            pass

        try:
            client.close()
        except Exception:
            pass

        print(f"\n🔌 Порт {port} закрыт")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Быстрый тест КУБ-1063")
    parser.add_argument("--port", required=True, help="Serial port")
    parser.add_argument("--slave", type=int, required=True, help="Slave ID")

    args = parser.parse_args()

    success = test_kub_quick(args.port, args.slave)
    sys.exit(0 if success else 1)
