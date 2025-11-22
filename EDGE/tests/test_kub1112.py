#!/usr/bin/env python3
"""Live KUB-1112 reader test – polls a real RTU heating controller."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Dict, Tuple

from core.device_registry import DeviceInfo, DeviceType  # noqa: E402
from core.device_adapters.base import (  # noqa: E402
    RegisterInfo,
    RegisterType,
    ValueType,
)
from modbus.universal_reader import UniversalModbusReader  # noqa: E402


# Минимальная карта регистров на основе документа "КУБ-1112 карта регистров"
REGISTER_SPECS = {
    "software_version": RegisterInfo(
        address=0x0301,
        name="software_version",
        value_type=ValueType.VERSION,
        description="Версия ПО",
        register_type=RegisterType.INPUT,
    ),
    "flame_level": RegisterInfo(
        address=0x0400,
        name="flame_level",
        value_type=ValueType.FLOAT,
        scale=0.01,
        signed=True,
        description="Уровень пламени",
        register_type=RegisterType.INPUT,
    ),
    "flame_present": RegisterInfo(
        address=0x0401,
        name="flame_present",
        value_type=ValueType.BOOLEAN,
        description="Флаг наличия пламени",
        register_type=RegisterType.INPUT,
    ),
    "min_work_time": RegisterInfo(
        address=0x0402,
        name="min_work_time",
        value_type=ValueType.FLOAT,
        scale=0.1,
        description="Мин. время работы, с",
        register_type=RegisterType.INPUT,
        special_values={0xFFFF: "pending"},
    ),
    "start_delay": RegisterInfo(
        address=0x0403,
        name="start_delay",
        value_type=ValueType.FLOAT,
        scale=0.1,
        description="Задержка включения, с",
        register_type=RegisterType.INPUT,
        special_values={0xFFFF: "pending"},
    ),
    "purge_duration": RegisterInfo(
        address=0x0404,
        name="purge_duration",
        value_type=ValueType.FLOAT,
        scale=0.1,
        description="Продолжительность продувки, с",
        register_type=RegisterType.INPUT,
        special_values={0xFFFF: "pending"},
    ),
    "temperature": RegisterInfo(
        address=0x0405,
        name="temperature",
        value_type=ValueType.TEMPERATURE,
        scale=0.1,
        signed=True,
        description="Температура корпуса, °C",
        register_type=RegisterType.INPUT,
        special_values={0x8000: "error"},
    ),
    "temp_resistance": RegisterInfo(
        address=0x0406,
        name="temp_resistance",
        value_type=ValueType.FLOAT,
        description="Сопротивление датчика, Ом",
        register_type=RegisterType.INPUT,
    ),
    "relay_state": RegisterInfo(
        address=0x0407,
        name="relay_state",
        value_type=ValueType.BITFIELD,
        description="Состояние реле",
        register_type=RegisterType.INPUT,
    ),
    "discrete_inputs": RegisterInfo(
        address=0x0408,
        name="discrete_inputs",
        value_type=ValueType.BITFIELD,
        description="Дискретные входы",
        register_type=RegisterType.INPUT,
    ),
    "operation_mode": RegisterInfo(
        address=0x0409,
        name="operation_mode",
        value_type=ValueType.INTEGER,
        description="Режим работы",
        register_type=RegisterType.INPUT,
    ),
    # 0x0410 должен быть прочитан первым – остальные регистры аварий
    # обновляют содержимое только после обращения к нему.
    "registered_alarms_0": RegisterInfo(
        address=0x0410,
        name="registered_alarms_0",
        value_type=ValueType.BITFIELD,
        description="Аварии [0..15] (чтение инициирует следующие регистры)",
        register_type=RegisterType.INPUT,
    ),
    "registered_alarms_1": RegisterInfo(
        address=0x0411,
        name="registered_alarms_1",
        value_type=ValueType.BITFIELD,
        description="Аварии [16..31]",
        register_type=RegisterType.INPUT,
    ),
    "registered_alarms_2": RegisterInfo(
        address=0x0412,
        name="registered_alarms_2",
        value_type=ValueType.BITFIELD,
        description="Аварии [32..47]",
        register_type=RegisterType.INPUT,
    ),
    "registered_alarms_3": RegisterInfo(
        address=0x0413,
        name="registered_alarms_3",
        value_type=ValueType.BITFIELD,
        description="Аварии [48..63]",
        register_type=RegisterType.INPUT,
    ),
    "modbus_address": RegisterInfo(
        address=0x0220,
        name="modbus_address",
        value_type=ValueType.INTEGER,
        description="Адрес Modbus",
        register_type=RegisterType.HOLDING,
    ),
    "modbus_baudrate": RegisterInfo(
        address=0x0221,
        name="modbus_baudrate",
        value_type=ValueType.INTEGER,
        description="Скорость Modbus",
        register_type=RegisterType.HOLDING,
    ),
}

RELAY_BITS = {
    0: "Клапан газа",
    1: "Розжиг",
    2: "Осн. вентилятор",
    3: "Доп. вентилятор",
    4: "Авария",
}

INPUT_BITS = {
    0: "Резерв 0",
    1: "Резерв 1",
    2: "Обдув есть",
    3: "Давление газа норм",
    4: "Запуск вентиляции",
    5: "Запуск нагрева",
    6: "Сброс аварии",
}

ALARM_BITS = {
    # 0x0411 (биты 0..15)
    0: "Резерв",
    1: "Не обнаружено пламя при запуске",
    2: "Низкое давление / обрыв датчика",
    3: "Пламя погасло",
    4: "Обдув при выключенном вентиляторе",
    5: "Отсутствует обдув камеры",
    6: "Обрыв/неисправность датчика температуры",
    7: "Пламя не гаснет",
    8: "Неправильный сигнал пламени",
    9: "Длительный сигнал сброса аварии",
    10: "Частые попытки сброса",
    11: "Сигнал STL",
    12: "Сигнал STM",
    13: "Отключился обдув камеры",
    14: "Короткий промежуток между пусками",
    15: "Ошибка при перепрошивке",
    # 0x0412 (биты 16..31)
    16: "Подача газа блокирована резервом",
    17: "Резерв",
    18: "Резерв",
    19: "Резерв",
    20: "Ошибка инициализации",
    21: "Ошибка доступа к устройству",
    22: "Включен режим тестирования",
    23: "Резерв",
    24: "Резерв",
    25: "Резерв",
    26: "Резерв",
    27: "Резерв",
    28: "Низкое напряжение питания",
    29: "Резерв",
    30: "Резерв",
    31: "Резерв",
    # 0x0413 (биты 32..47)
    32: "Резерв",
    33: "Перегрузка системы",
    34: "Резерв",
    35: "Резерв",
    36: "Резерв",
    37: "Резерв",
    38: "Резерв",
    39: "Резерв",
    40: "Резерв",
    41: "Резерв",
    42: "Резерв",
    43: "Резерв",
    44: "Резерв",
    45: "Резерв",
    46: "Резерв",
    47: "Резерв",
}


def _parse_value(info: RegisterInfo, raw_value: int) -> Tuple[object, str]:
    """Парсинг значения в соответствии с типом."""
    if info.special_values and raw_value in info.special_values:
        status = info.special_values[raw_value]
        return status, status

    value = raw_value
    if info.signed and raw_value > 0x7FFF:
        value = raw_value - 0x10000

    if info.value_type == ValueType.BOOLEAN:
        parsed = bool(value)
    elif info.value_type == ValueType.VERSION:
        major = value // 100
        minor = value % 100
        parsed = f"{major}.{minor:02d}"
    elif info.value_type == ValueType.BITFIELD:
        parsed = value
    else:
        parsed = value * info.scale

    return parsed, "ok"


def _decode_baudrate(code: int) -> str:
    mapping = {
        1: "1200",
        2: "2400",
        3: "4800",
        4: "9600",
        5: "19200",
        6: "38400",
        7: "57600",
        8: "115200",
    }
    return mapping.get(code, f"unknown({code})")


def _decode_operation_mode(mode: int) -> str:
    return {
        0: "Не выбран",
        1: "Авто обогрев + авто вентиляция",
        2: "Непрерывный обогрев",
        3: "Непрерывная вентиляция",
        4: "Авто обогрев + непрерывная вентиляция",
    }.get(mode, f"Режим {mode}")


def _format_bitfield(value: int, labels: Dict[int, str]) -> str:
    active = [labels[bit] for bit in sorted(labels) if value & (1 << bit)]
    return ", ".join(active) if active else "нет активных"


def _decode_alarm_register(index: int, value: int) -> str:
    bit_offset = index * 16
    details = []
    for bit in range(16):
        if value & (1 << bit):
            description = ALARM_BITS.get(bit_offset + bit, f"Авария бит {bit_offset + bit}")
            details.append(description)
    return ", ".join(details) if details else "нет зарегистрированных"


def read_kub1112_raw(reader: UniversalModbusReader, device: DeviceInfo) -> Dict[int, int]:
    # Используем внутренний метод universal reader для чтения нужных адресов
    return reader._read_registers_with_types(slave_id=device.slave_id, register_map=REGISTER_SPECS)  # type: ignore[attr-defined]


def parse_kub1112_registers(raw: Dict[int, int]) -> Dict[str, Tuple[object, str]]:
    parsed: Dict[str, Tuple[object, str]] = {}
    for name, info in REGISTER_SPECS.items():
        if info.address in raw:
            parsed[name] = _parse_value(info, raw[info.address])
    return parsed


def run_live_kub1112(port: str, slave_id: int, timeout: float = 0.5) -> bool:
    reader = UniversalModbusReader(port=port, baudrate=9600, timeout=timeout)
    if not reader.connect():
        print(f"❌ Не удалось подключиться к {port}")
        return False

    try:
        device = DeviceInfo(
            device_id=slave_id,
            device_type=DeviceType.KUB_1112,
            slave_id=slave_id,
            name=f"LIVE KUB-1112 #{slave_id}",
            enabled=True,
        )

        print(f"📡 Читаем KUB-1112 (port={port}, slave_id={slave_id})")
        raw = read_kub1112_raw(reader, device)
        if not raw:
            print("❌ Данные не получены")
            return False

        parsed = parse_kub1112_registers(raw)
        print("✅ Получены", len(parsed), "переменных")

        def show(name: str, formatter=lambda v: v):
            value, status = parsed.get(name, (None, "missing"))
            if value is None:
                print(f"   {name}: — ({status})")
            elif status != "ok":
                print(f"   {name}: {value} ({status})")
            else:
                print(f"   {name}: {formatter(value)}")

        show("software_version")
        show("flame_present", lambda v: "🔥 есть" if v else "нет")
        show("flame_level", lambda v: f"{v:.2f}%")
        show("temperature", lambda v: f"{v:.1f}°C")
        show("min_work_time", lambda v: f"{v:.1f} с")
        show("start_delay", lambda v: f"{v:.1f} с")
        show("purge_duration", lambda v: f"{v:.1f} с")
        show("temp_resistance", lambda v: f"{v:.0f} Ом")

        relay_val, _ = parsed.get("relay_state", (0, "missing"))
        print("   relay_state:", f"0x{int(relay_val):04X}")
        print("     активны:", _format_bitfield(int(relay_val), RELAY_BITS))

        inputs_val, _ = parsed.get("discrete_inputs", (0, "missing"))
        print("   discrete_inputs:", f"0x{int(inputs_val):04X}")
        print("     активны:", _format_bitfield(int(inputs_val), INPUT_BITS))

        op_mode, status = parsed.get("operation_mode", (None, "missing"))
        if op_mode is not None and status == "ok":
            print("   operation_mode:", _decode_operation_mode(int(op_mode)))
        else:
            print("   operation_mode: — (", status, ")")

        alarms = []
        for idx in range(4):
            reg_name = f"registered_alarms_{idx}"
            value, st = parsed.get(reg_name, (None, "missing"))
            if value is not None and st == "ok":
                print(f"   {reg_name}: 0x{int(value):04X}")
                decoded = _decode_alarm_register(idx, int(value))
                print("     ", decoded)
                if value:
                    alarms.append((idx, int(value)))

        if alarms:
            print("🚨 Зарегистрированные аварии присутствуют")
        else:
            print("✅ Зарегистрированных аварий нет")

        addr, addr_status = parsed.get("modbus_address", (None, "missing"))
        baud, baud_status = parsed.get("modbus_baudrate", (None, "missing"))
        if addr is not None and addr_status == "ok":
            print("   Modbus address:", int(addr))
        if baud is not None and baud_status == "ok":
            print("   Modbus baudrate:", _decode_baudrate(int(baud)))

        return True
    finally:
        reader.disconnect()
        print(f"🔌 Порт {port} закрыт")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Live KUB-1112 reader test")
    parser.add_argument("--port", required=True, help="Serial port (e.g. /dev/ttyUSB0)")
    parser.add_argument("--slave", type=int, required=True, help="Slave ID of KUB-1112")
    parser.add_argument("--timeout", type=float, default=0.5)
    args = parser.parse_args(argv)

    return 0 if run_live_kub1112(args.port, args.slave, args.timeout) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
