#!/usr/bin/env python3
"""
Sequential test for both VFD and KUB-1063 devices
Tests autoscan for both devices to verify no port conflicts
"""

import sys
import time
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

from start_edge import AUTOSCAN_DEVICE_PROBES, _make_reader


def test_single_device(port: str, slave_id: int, expected_type: str) -> bool:
    """Тест одного устройства с автосканом"""

    print(f"\n{'='*70}")
    print(f"🔎 Тест устройства: slave_id={slave_id}, ожидается: {expected_type}")
    print('='*70)

    # Создаём клиент
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

        print(f"✅ Подключено к {port}")

        # Создаём reader
        read = _make_reader(client)

        # Проверяем только ожидаемый тип устройства
        for device_type, probes in AUTOSCAN_DEVICE_PROBES:
            if device_type != expected_type:
                continue

            print(f"\n📋 Проверка типа: {device_type}")

            for i, probe in enumerate(probes, 1):
                address = probe["address"]
                kind = probe.get("kind", "holding")
                count = probe.get("count", 1)
                require_non_zero = probe.get("require_non_zero", False)

                print(f"  Probe {i}: 0x{address:04X} ({kind})", end=" ")

                try:
                    result = read(kind, address, count, slave_id)

                    if hasattr(result, "isError") and not result.isError():
                        registers = getattr(result, "registers", [])
                        if registers:
                            print(f"→ {registers}", end="")

                            # Проверяем условия
                            if require_non_zero and any(val not in (0, None) for val in registers):
                                print(" ✅")
                                print(f"\n✅ УСТРОЙСТВО НАЙДЕНО: {device_type}")
                                return True
                            elif not require_non_zero:
                                print(" ✅")
                                print(f"\n✅ УСТРОЙСТВО НАЙДЕНО: {device_type}")
                                return True
                            else:
                                print(" ❌ (нули)")
                        else:
                            print(" ⚠️ (пусто)")
                    else:
                        print(" ❌ (ошибка)")

                except Exception as e:
                    print(f" ❌ ({e})")

        print(f"\n❌ Устройство {expected_type} не найдено")
        return False

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

        print(f"🔌 Порт {port} закрыт")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Sequential test for VFD and KUB-1063")
    parser.add_argument("--port", required=True, help="Serial port")
    parser.add_argument("--vfd-id", type=int, default=1, help="VFD slave ID")
    parser.add_argument("--kub-id", type=int, default=2, help="KUB slave ID")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between tests (seconds)")

    args = parser.parse_args()

    print("\n" + "="*70)
    print("ПОСЛЕДОВАТЕЛЬНЫЙ ТЕСТ УСТРОЙСТВ")
    print("="*70)

    # Тест 1: VFD-INVERTER
    vfd_success = test_single_device(args.port, args.vfd_id, "VFD-INVERTER")

    # Пауза между тестами
    print(f"\n⏳ Пауза {args.delay}с перед следующим тестом...")
    time.sleep(args.delay)

    # Тест 2: KUB-1063
    kub_success = test_single_device(args.port, args.kub_id, "KUB-1063")

    # Итоговый отчёт
    print("\n" + "="*70)
    print("ИТОГОВЫЙ ОТЧЁТ")
    print("="*70)
    print(f"VFD-INVERTER (slave_id={args.vfd_id}): {'✅ OK' if vfd_success else '❌ FAIL'}")
    print(f"KUB-1063 (slave_id={args.kub_id}): {'✅ OK' if kub_success else '❌ FAIL'}")
    print("="*70)

    if vfd_success and kub_success:
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        sys.exit(0)
    else:
        print("❌ ЕСТЬ ОШИБКИ")
        sys.exit(1)


if __name__ == "__main__":
    main()
