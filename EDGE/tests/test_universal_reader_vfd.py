#!/usr/bin/env python3
"""
Тест Universal Modbus Reader с реальным VFD устройством
Проверка чтения данных через адаптер
"""

import sys
from pathlib import Path

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent.parent))

from modbus.universal_reader import UniversalModbusReader, get_universal_reader
from core.device_registry import DeviceInfo, DeviceType


def test_direct_vfd_read():
    """Прямое чтение VFD через Universal Reader"""
    print("=" * 70)
    print("🧪 Тест: Прямое чтение VFD Inverter")
    print("=" * 70)

    # Настройки порта (как в вашем тесте)
    PORT = "/dev/ttys027"
    BAUDRATE = 9600
    SLAVE_ID = 7

    # Создаем reader
    reader = UniversalModbusReader(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=0.5
    )

    # Подключаемся
    if not reader.connect():
        print("❌ Не удалось подключиться к порту")
        return False

    print(f"✅ Подключено к {PORT}")

    # Создаем DeviceInfo для VFD
    vfd_device = DeviceInfo(
        device_id=1,
        device_type=DeviceType.VFD_INVERTER,
        slave_id=SLAVE_ID,
        name="VFD Test Device",
        description="Test VFD Inverter",
        enabled=True
    )

    print(f"\n📡 Читаем данные VFD (slave_id={SLAVE_ID})...")

    # Читаем данные через универсальный reader
    data = reader.read_device(vfd_device)

    if not data:
        print("❌ Не удалось прочитать данные")
        reader.disconnect()
        return False

    # Выводим результаты
    print("\n" + "=" * 70)
    print(f"✅ Устройство: {data['device_name']}")
    print(f"✅ Тип: {data['device_type']}")
    print(f"✅ Статус: {data['connection_status']}")
    print(f"✅ Время: {data['timestamp']}")
    print("=" * 70)

    print("\n📊 Основные параметры VFD:")
    print("-" * 70)

    registers = data.get("registers", {})

    # Ключевые параметры
    key_params = [
        ("running_state", "Состояние"),
        ("fault_code", "Код ошибки"),
        ("set_frequency", "Заданная частота"),
        ("running_frequency", "Текущая частота"),
        ("running_speed", "Скорость"),
        ("output_voltage", "Напряжение"),
        ("output_current", "Ток"),
        ("output_power", "Мощность"),
        ("dc_bus_voltage", "DC шина"),
        ("output_torque", "Момент"),
        ("motor_temperature", "Т мотора"),
        ("igbt_temperature", "Т IGBT"),
        ("cumulative_running_time", "Время работы"),
        ("cumulative_power_consumption", "Потребление"),
    ]

    for param_key, param_name in key_params:
        value = registers.get(param_key)
        if value is not None:
            status = data.get("status", {}).get(param_key, "ok")
            status_icon = "✅" if status == "ok" else "⚠️"
            print(f"{status_icon} {param_name:25s}: {value}")

    # Аварии и предупреждения
    alarms = data.get("alarms", [])
    warnings = data.get("warnings", [])

    if alarms:
        print("\n🚨 КРИТИЧЕСКИЕ АВАРИИ:")
        for alarm in alarms:
            print(f"   ❌ {alarm}")

    if warnings:
        print("\n⚠️  ПРЕДУПРЕЖДЕНИЯ:")
        for warning in warnings:
            print(f"   ⚠️  {warning}")

    if not alarms and not warnings:
        print("\n✅ Аварий и предупреждений нет")

    # Отключаемся
    reader.disconnect()

    print("\n✅ Тест завершен успешно!")
    return True


def test_multiple_reads():
    """Тест множественных чтений VFD"""
    print("\n" + "=" * 70)
    print("🧪 Тест: Множественное чтение VFD (3 раза)")
    print("=" * 70)

    PORT = "/dev/ttys027"
    BAUDRATE = 9600
    SLAVE_ID = 7

    reader = UniversalModbusReader(port=PORT, baudrate=BAUDRATE, timeout=0.5)

    vfd_device = DeviceInfo(
        device_id=1,
        device_type=DeviceType.VFD_INVERTER,
        slave_id=SLAVE_ID,
        name="VFD Test",
        enabled=True
    )

    success_count = 0
    total_reads = 3

    for i in range(total_reads):
        print(f"\n📡 Чтение #{i + 1}/{total_reads}...")

        data = reader.read_device(vfd_device)

        if data:
            freq = data.get("registers", {}).get("running_frequency", "N/A")
            current = data.get("registers", {}).get("output_current", "N/A")
            temp = data.get("registers", {}).get("motor_temperature", "N/A")

            print(f"   ✅ Частота: {freq} Hz, Ток: {current} A, Т: {temp}°C")
            success_count += 1
        else:
            print("   ❌ Ошибка чтения")

        import time
        time.sleep(1)  # Пауза между чтениями

    reader.disconnect()

    print(f"\n📊 Результат: {success_count}/{total_reads} успешных чтений")

    if success_count == total_reads:
        print("✅ Тест множественного чтения пройден!")
        return True
    else:
        print(f"⚠️ Только {success_count} из {total_reads} чтений успешны")
        return False


def test_batch_reading():
    """Тест пакетного чтения регистров"""
    print("\n" + "=" * 70)
    print("🧪 Тест: Пакетное чтение регистров VFD")
    print("=" * 70)

    PORT = "/dev/ttys027"
    BAUDRATE = 9600
    SLAVE_ID = 7

    reader = UniversalModbusReader(port=PORT, baudrate=BAUDRATE, timeout=0.5)

    if not reader.connect():
        print("❌ Не удалось подключиться")
        return False

    # Читаем несколько последовательных регистров
    addresses = [0x1000, 0x1001, 0x1002, 0x1003, 0x1004, 0x1005, 0x1006]

    print(f"📖 Читаем {len(addresses)} регистров пакетом...")

    registers = reader.read_registers_batch(
        slave_id=SLAVE_ID,
        register_addresses=addresses,
        batch_size=10
    )

    if not registers:
        print("❌ Не удалось прочитать регистры")
        reader.disconnect()
        return False

    print(f"✅ Прочитано {len(registers)} регистров:")

    register_names = {
        0x1000: "running_state",
        0x1001: "fault_code",
        0x1002: "set_frequency",
        0x1003: "running_frequency",
        0x1004: "running_speed",
        0x1005: "output_voltage",
        0x1006: "output_current",
    }

    for addr in sorted(registers.keys()):
        name = register_names.get(addr, f"0x{addr:04X}")
        value = registers[addr]
        print(f"   0x{addr:04X} ({name:20s}): {value}")

    reader.disconnect()
    print("✅ Тест пакетного чтения пройден!")
    return True


def run_all_tests():
    """Запуск всех тестов"""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 10 + "🧪 UNIVERSAL READER + VFD TEST SUITE 🧪" + " " * 17 + "║")
    print("╚" + "=" * 68 + "╝")

    tests = [
        ("Прямое чтение VFD", test_direct_vfd_read),
        ("Множественное чтение", test_multiple_reads),
        ("Пакетное чтение", test_batch_reading),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            print(f"\n🔬 Запуск теста: {test_name}")
            result = test_func()
            if result:
                passed += 1
            else:
                failed += 1
                print(f"❌ Тест '{test_name}' провален")
        except Exception as e:
            failed += 1
            print(f"\n💥 ОШИБКА в тесте '{test_name}': {e}")
            import traceback
            traceback.print_exc()

    # Итоги
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 25 + "📊 РЕЗУЛЬТАТЫ" + " " * 30 + "║")
    print("╠" + "=" * 68 + "╣")
    print(f"║  ✅ Пройдено: {passed:2d}/{len(tests)}" + " " * 51 + "║")
    print(f"║  ❌ Провалено: {failed:2d}/{len(tests)}" + " " * 50 + "║")
    print("╚" + "=" * 68 + "╝")

    if failed == 0:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! 🎉\n")
        return 0
    else:
        print(f"\n⚠️  {failed} ТЕСТ(ОВ) ПРОВАЛЕНО\n")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
