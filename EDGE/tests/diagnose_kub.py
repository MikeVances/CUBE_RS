#!/usr/bin/env python3
"""
Диагностика чтения КУБ-1063 через UniversalModbusReader
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.device_registry import DeviceInfo, DeviceType
from modbus.universal_reader import UniversalModbusReader

def diagnose_kub_reading(port: str, slave_id: int):
    """Диагностика чтения с замером времени"""

    print("="*70)
    print(f"🔎 ДИАГНОСТИКА ЧТЕНИЯ КУБ-1063 (slave_id={slave_id})")
    print("="*70)

    reader = UniversalModbusReader(port=port, baudrate=9600, timeout=5.0)

    if not reader.connect():
        print(f"❌ Не удалось подключиться к {port}")
        return False

    try:
        print(f"✅ Подключено к {port}\n")

        device = DeviceInfo(
            device_id=2,
            device_type=DeviceType.KUB_1063,
            slave_id=slave_id,
            name=f"TEST KUB #{slave_id}",
            enabled=True,
        )

        print("📊 Засекаем время чтения всех регистров...")
        start_time = time.time()

        data = reader.read_device(device)

        elapsed = time.time() - start_time

        print(f"\n⏱️  Время чтения: {elapsed:.2f} секунд")

        if not data:
            print("❌ ДАННЫЕ НЕ ПОЛУЧЕНЫ!")
            return False

        print(f"✅ ДАННЫЕ ПОЛУЧЕНЫ!")
        print(f"   Статус соединения: {data.get('connection_status')}")

        regs = data.get("registers", {})
        print(f"   Количество прочитанных регистров: {len(regs)}")

        # Показываем первые 5 регистров
        print("\n   Первые 5 значений:")
        for i, (name, value) in enumerate(list(regs.items())[:5]):
            print(f"     {name}: {value}")

        return True

    finally:
        # Гарантированное закрытие порта
        reader.disconnect()
        print(f"🔌 Порт {port} закрыт")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Диагностика чтения КУБ-1063")
    parser.add_argument("--port", required=True, help="Serial port")
    parser.add_argument("--slave", type=int, required=True, help="Slave ID")

    args = parser.parse_args()

    success = diagnose_kub_reading(args.port, args.slave)
    sys.exit(0 if success else 1)
