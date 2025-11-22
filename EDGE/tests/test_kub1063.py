#!/usr/bin/env python3
"""Live KUB-1063 reader test – polls the full register map from real device."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.device_registry import DeviceInfo, DeviceType  # noqa: E402
from core.device_adapters.base import (  # noqa: E402
    RegisterInfo,
    RegisterType,
    ValueType,
)
from modbus.universal_reader import UniversalModbusReader  # noqa: E402


# Актуальная карта регистров (по документу "Модбас карта КУБ-1063М")
REGISTER_SPECS: Dict[str, RegisterInfo] = {
    "software_version": RegisterInfo(
        address=0x0301,
        name="software_version",
        value_type=ValueType.VERSION,
        description="Версия ПО",
        register_type=RegisterType.INPUT,
    ),
    "digital_outputs_1": RegisterInfo(
        address=0x0081,
        name="digital_outputs_1",
        value_type=ValueType.BITFIELD,
        description="ГНВ базовой и туннельной вентиляции",
        register_type=RegisterType.INPUT,
    ),
    "digital_outputs_2": RegisterInfo(
        address=0x0082,
        name="digital_outputs_2",
        value_type=ValueType.BITFIELD,
        description="ГРВ, нагреватели, аварии, освещение",
        register_type=RegisterType.INPUT,
    ),
    "digital_outputs_3": RegisterInfo(
        address=0x00A2,
        name="digital_outputs_3",
        value_type=ValueType.BITFIELD,
        description="Таймеры",
        register_type=RegisterType.INPUT,
    ),
    "pressure": RegisterInfo(
        address=0x0083,
        name="pressure",
        value_type=ValueType.FLOAT,
        scale=0.1,
        description="Отрицательное давление, Па",
        register_type=RegisterType.INPUT,
        special_values={0xFFFF: "pending", 0xFFFE: "break", 0xFFFD: "error", 0xFFFC: "disabled"},
    ),
    "humidity": RegisterInfo(
        address=0x0084,
        name="humidity",
        value_type=ValueType.PERCENTAGE,
        scale=0.1,
        description="Относительная влажность, %",
        register_type=RegisterType.INPUT,
        special_values={0xFFFF: "pending", 0xFFFE: "break", 0xFFFD: "error", 0xFFFC: "disabled"},
    ),
    "co2": RegisterInfo(
        address=0x0085,
        name="co2",
        value_type=ValueType.INTEGER,
        description="Концентрация CO2, ppm",
        register_type=RegisterType.INPUT,
        special_values={0xFFFF: "pending", 0xFFFE: "break", 0xFFFD: "error", 0xFFFC: "disabled"},
    ),
    "nh3": RegisterInfo(
        address=0x0086,
        name="nh3",
        value_type=ValueType.FLOAT,
        scale=0.1,
        description="Концентрация NH3, ppm",
        register_type=RegisterType.INPUT,
        special_values={0xFFFF: "pending", 0xFFFE: "break", 0xFFFD: "error", 0xFFFC: "disabled"},
    ),
    "grv_base": RegisterInfo(
        address=0x0087,
        name="grv_base",
        value_type=ValueType.PERCENTAGE,
        scale=0.1,
        description="ГРВ базовой вентиляции",
        register_type=RegisterType.INPUT,
        special_values={0xFFFF: "pending", 0xFFFE: "not_assigned", 0xFFFD: "error", 0xFFFC: "unused"},
    ),
    "grv_tunnel": RegisterInfo(
        address=0x0088,
        name="grv_tunnel",
        value_type=ValueType.PERCENTAGE,
        scale=0.1,
        description="ГРВ туннельной вентиляции",
        register_type=RegisterType.INPUT,
        special_values={0xFFFF: "pending", 0xFFFE: "not_assigned", 0xFFFD: "error", 0xFFFC: "unused"},
    ),
    "damper": RegisterInfo(
        address=0x0089,
        name="damper",
        value_type=ValueType.PERCENTAGE,
        scale=0.1,
        description="Демпфер",
        register_type=RegisterType.INPUT,
    ),
    "air_intake_1": RegisterInfo(
        address=0x008A,
        name="air_intake_1",
        value_type=ValueType.PERCENTAGE,
        scale=0.1,
        description="Воздухозаборник 1",
        register_type=RegisterType.INPUT,
    ),
    "air_intake_2": RegisterInfo(
        address=0x008B,
        name="air_intake_2",
        value_type=ValueType.PERCENTAGE,
        scale=0.1,
        description="Воздухозаборник 2",
        register_type=RegisterType.INPUT,
    ),
    "air_intake_tunnel": RegisterInfo(
        address=0x008C,
        name="air_intake_tunnel",
        value_type=ValueType.PERCENTAGE,
        scale=0.1,
        description="Туннельный воздухозаборник",
        register_type=RegisterType.INPUT,
    ),
    "temp_inside_1": RegisterInfo(
        address=0x008D,
        name="temp_inside_1",
        value_type=ValueType.TEMPERATURE,
        scale=0.1,
        signed=True,
        description="Температура внутри 1",
        register_type=RegisterType.INPUT,
        special_values={0x7FFF: "pending", 0x7FFE: "break", 0x7FFD: "error", 0x7FFC: "disabled"},
    ),
    "temp_inside_2": RegisterInfo(
        address=0x008E,
        name="temp_inside_2",
        value_type=ValueType.TEMPERATURE,
        scale=0.1,
        signed=True,
        description="Температура внутри 2",
        register_type=RegisterType.INPUT,
        special_values={0x7FFF: "pending", 0x7FFE: "break", 0x7FFD: "error", 0x7FFC: "disabled"},
    ),
    "temp_outside": RegisterInfo(
        address=0x008F,
        name="temp_outside",
        value_type=ValueType.TEMPERATURE,
        scale=0.1,
        signed=True,
        description="Температура снаружи",
        register_type=RegisterType.INPUT,
        special_values={0x7FFF: "pending", 0x7FFE: "break", 0x7FFD: "error", 0x7FFC: "disabled"},
    ),
    "temp_inside_3": RegisterInfo(
        address=0x0090,
        name="temp_inside_3",
        value_type=ValueType.TEMPERATURE,
        scale=0.1,
        signed=True,
        description="Температура внутри 3",
        register_type=RegisterType.INPUT,
        special_values={0x7FFF: "pending", 0x7FFE: "break", 0x7FFD: "error", 0x7FFC: "disabled"},
    ),
    "temp_inside_4": RegisterInfo(
        address=0x0091,
        name="temp_inside_4",
        value_type=ValueType.TEMPERATURE,
        scale=0.1,
        signed=True,
        description="Температура внутри 4",
        register_type=RegisterType.INPUT,
        special_values={0x7FFF: "pending", 0x7FFE: "break", 0x7FFD: "error", 0x7FFC: "disabled"},
    ),
    "air_intake_3": RegisterInfo(
        address=0x0092,
        name="air_intake_3",
        value_type=ValueType.PERCENTAGE,
        scale=0.1,
        description="Воздухозаборник 3",
        register_type=RegisterType.INPUT,
    ),
    "air_intake_4": RegisterInfo(
        address=0x0093,
        name="air_intake_4",
        value_type=ValueType.PERCENTAGE,
        scale=0.1,
        description="Воздухозаборник 4",
        register_type=RegisterType.INPUT,
    ),
    "lighting_1": RegisterInfo(0x0094, "lighting_1", ValueType.PERCENTAGE, scale=0.1, description="Освещение 1", register_type=RegisterType.INPUT),
    "lighting_2": RegisterInfo(0x0095, "lighting_2", ValueType.PERCENTAGE, scale=0.1, description="Освещение 2", register_type=RegisterType.INPUT),
    "lighting_3": RegisterInfo(0x0096, "lighting_3", ValueType.PERCENTAGE, scale=0.1, description="Освещение 3", register_type=RegisterType.INPUT),
    "lighting_4": RegisterInfo(0x0097, "lighting_4", ValueType.PERCENTAGE, scale=0.1, description="Освещение 4", register_type=RegisterType.INPUT),
    "timer_1_output_1": RegisterInfo(0x0098, "timer_1_output_1", ValueType.PERCENTAGE, scale=0.1, description="Таймер 1 выход 1", register_type=RegisterType.INPUT),
    "timer_1_output_2": RegisterInfo(0x0099, "timer_1_output_2", ValueType.PERCENTAGE, scale=0.1, description="Таймер 1 выход 2", register_type=RegisterType.INPUT),
    "timer_1_output_3": RegisterInfo(0x009A, "timer_1_output_3", ValueType.PERCENTAGE, scale=0.1, description="Таймер 1 выход 3", register_type=RegisterType.INPUT),
    "timer_1_output_4": RegisterInfo(0x009B, "timer_1_output_4", ValueType.PERCENTAGE, scale=0.1, description="Таймер 1 выход 4", register_type=RegisterType.INPUT),
    "timer_2_output_1": RegisterInfo(0x009C, "timer_2_output_1", ValueType.PERCENTAGE, scale=0.1, description="Таймер 2 выход 1", register_type=RegisterType.INPUT),
    "timer_2_output_2": RegisterInfo(0x009D, "timer_2_output_2", ValueType.PERCENTAGE, scale=0.1, description="Таймер 2 выход 2", register_type=RegisterType.INPUT),
    "timer_2_output_3": RegisterInfo(0x009E, "timer_2_output_3", ValueType.PERCENTAGE, scale=0.1, description="Таймер 2 выход 3", register_type=RegisterType.INPUT),
    "timer_2_output_4": RegisterInfo(0x009F, "timer_2_output_4", ValueType.PERCENTAGE, scale=0.1, description="Таймер 2 выход 4", register_type=RegisterType.INPUT),
    "active_alarms_0": RegisterInfo(0x00C0, "active_alarms_0", ValueType.BITFIELD, description="Активные аварии 1", register_type=RegisterType.INPUT),
    "active_alarms_1": RegisterInfo(0x00C1, "active_alarms_1", ValueType.BITFIELD, description="Активные аварии 2", register_type=RegisterType.INPUT),
    "active_alarms_2": RegisterInfo(0x00C2, "active_alarms_2", ValueType.BITFIELD, description="Активные аварии 3", register_type=RegisterType.INPUT),
    "active_alarms_3": RegisterInfo(0x00C3, "active_alarms_3", ValueType.BITFIELD, description="Активные аварии 4", register_type=RegisterType.INPUT),
    "registered_alarms_0": RegisterInfo(0x00C4, "registered_alarms_0", ValueType.BITFIELD, description="Зарегистрированные аварии 1", register_type=RegisterType.INPUT),
    "registered_alarms_1": RegisterInfo(0x00C5, "registered_alarms_1", ValueType.BITFIELD, description="Зарегистрированные аварии 2", register_type=RegisterType.INPUT),
    "registered_alarms_2": RegisterInfo(0x00C6, "registered_alarms_2", ValueType.BITFIELD, description="Зарегистрированные аварии 3", register_type=RegisterType.INPUT),
    "registered_alarms_3": RegisterInfo(0x00C7, "registered_alarms_3", ValueType.BITFIELD, description="Зарегистрированные аварии 4", register_type=RegisterType.INPUT),
    "active_warnings_0": RegisterInfo(0x00C8, "active_warnings_0", ValueType.BITFIELD, description="Активные предупреждения 1", register_type=RegisterType.INPUT),
    "active_warnings_1": RegisterInfo(0x00C9, "active_warnings_1", ValueType.BITFIELD, description="Активные предупреждения 2", register_type=RegisterType.INPUT),
    "active_warnings_2": RegisterInfo(0x00CA, "active_warnings_2", ValueType.BITFIELD, description="Активные предупреждения 3", register_type=RegisterType.INPUT),
    "active_warnings_3": RegisterInfo(0x00CB, "active_warnings_3", ValueType.BITFIELD, description="Активные предупреждения 4", register_type=RegisterType.INPUT),
    "registered_warnings_0": RegisterInfo(0x00CC, "registered_warnings_0", ValueType.BITFIELD, description="Зарегистрированные предупреждения 1", register_type=RegisterType.INPUT),
    "registered_warnings_1": RegisterInfo(0x00CD, "registered_warnings_1", ValueType.BITFIELD, description="Зарегистрированные предупреждения 2", register_type=RegisterType.INPUT),
    "registered_warnings_2": RegisterInfo(0x00CE, "registered_warnings_2", ValueType.BITFIELD, description="Зарегистрированные предупреждения 3", register_type=RegisterType.INPUT),
    "registered_warnings_3": RegisterInfo(0x00CF, "registered_warnings_3", ValueType.BITFIELD, description="Зарегистрированные предупреждения 4", register_type=RegisterType.INPUT),
    "ventilation_target": RegisterInfo(0x00D0, "ventilation_target", ValueType.PERCENTAGE, scale=0.1, description="Целевой уровень вентиляции", register_type=RegisterType.INPUT),
    "ventilation_level": RegisterInfo(0x00D1, "ventilation_level", ValueType.PERCENTAGE, scale=0.1, description="Фактический уровень вентиляции", register_type=RegisterType.INPUT),
    "ventilation_scheme": RegisterInfo(0x00D2, "ventilation_scheme", ValueType.INTEGER, description="Активная схема вентиляции", register_type=RegisterType.INPUT),
    "day_counter": RegisterInfo(0x00D3, "day_counter", ValueType.INTEGER, signed=True, description="Счетчик дней", register_type=RegisterType.INPUT),
    "temp_target": RegisterInfo(0x00D4, "temp_target", ValueType.TEMPERATURE, scale=0.1, signed=True, description="Целевая температура", register_type=RegisterType.INPUT),
    "temp_inside": RegisterInfo(0x00D5, "temp_inside", ValueType.TEMPERATURE, scale=0.1, signed=True, description="Текущая внутренняя температура", register_type=RegisterType.INPUT),
    "temp_vent_activation": RegisterInfo(0x00D6, "temp_vent_activation", ValueType.TEMPERATURE, scale=0.1, signed=True, description="Температура активации вентиляции", register_type=RegisterType.INPUT),
    # Аналоговые выходы/назначения (0x011A-0x012F)
    "analog_grv_base": RegisterInfo(0x011A, "analog_grv_base", ValueType.INTEGER, signed=True, description="Аналоговый выход для ГРВ базовой", register_type=RegisterType.INPUT),
    "analog_grv_tunnel": RegisterInfo(0x011B, "analog_grv_tunnel", ValueType.INTEGER, signed=True, description="Аналоговый выход для ГРВ туннельной", register_type=RegisterType.INPUT),
    "analog_damper": RegisterInfo(0x011C, "analog_damper", ValueType.INTEGER, signed=True, description="Аналоговый выход для демпфера", register_type=RegisterType.INPUT),
    "analog_intake_1": RegisterInfo(0x011D, "analog_intake_1", ValueType.INTEGER, signed=True, description="Аналоговый выход воздухозаборник 1", register_type=RegisterType.INPUT),
    "analog_intake_2": RegisterInfo(0x011E, "analog_intake_2", ValueType.INTEGER, signed=True, description="Аналоговый выход воздухозаборник 2", register_type=RegisterType.INPUT),
    "analog_intake_tunnel": RegisterInfo(0x011F, "analog_intake_tunnel", ValueType.INTEGER, signed=True, description="Аналоговый выход туннель", register_type=RegisterType.INPUT),
    "analog_intake_3": RegisterInfo(0x0120, "analog_intake_3", ValueType.INTEGER, signed=True, description="Аналоговый выход воздухозаборник 3", register_type=RegisterType.INPUT),
    "analog_intake_4": RegisterInfo(0x0121, "analog_intake_4", ValueType.INTEGER, signed=True, description="Аналоговый выход воздухозаборник 4", register_type=RegisterType.INPUT),
    "analog_light_1": RegisterInfo(0x0124, "analog_light_1", ValueType.INTEGER, signed=True, description="Аналоговый выход освещение 1", register_type=RegisterType.INPUT),
    "analog_light_2": RegisterInfo(0x0125, "analog_light_2", ValueType.INTEGER, signed=True, description="Аналоговый выход освещение 2", register_type=RegisterType.INPUT),
    "analog_light_3": RegisterInfo(0x0126, "analog_light_3", ValueType.INTEGER, signed=True, description="Аналоговый выход освещение 3", register_type=RegisterType.INPUT),
    "analog_light_4": RegisterInfo(0x0127, "analog_light_4", ValueType.INTEGER, signed=True, description="Аналоговый выход освещение 4", register_type=RegisterType.INPUT),
    "analog_timer1_out1": RegisterInfo(0x0128, "analog_timer1_out1", ValueType.INTEGER, signed=True, description="Аналоговый выход таймер1-1", register_type=RegisterType.INPUT),
    "analog_timer1_out2": RegisterInfo(0x0129, "analog_timer1_out2", ValueType.INTEGER, signed=True, description="Аналоговый выход таймер1-2", register_type=RegisterType.INPUT),
    "analog_timer1_out3": RegisterInfo(0x012A, "analog_timer1_out3", ValueType.INTEGER, signed=True, description="Аналоговый выход таймер1-3", register_type=RegisterType.INPUT),
    "analog_timer1_out4": RegisterInfo(0x012B, "analog_timer1_out4", ValueType.INTEGER, signed=True, description="Аналоговый выход таймер1-4", register_type=RegisterType.INPUT),
    "analog_timer2_out1": RegisterInfo(0x012C, "analog_timer2_out1", ValueType.INTEGER, signed=True, description="Аналоговый выход таймер2-1", register_type=RegisterType.INPUT),
    "analog_timer2_out2": RegisterInfo(0x012D, "analog_timer2_out2", ValueType.INTEGER, signed=True, description="Аналоговый выход таймер2-2", register_type=RegisterType.INPUT),
    "analog_timer2_out3": RegisterInfo(0x012E, "analog_timer2_out3", ValueType.INTEGER, signed=True, description="Аналоговый выход таймер2-3", register_type=RegisterType.INPUT),
    "analog_timer2_out4": RegisterInfo(0x012F, "analog_timer2_out4", ValueType.INTEGER, signed=True, description="Аналоговый выход таймер2-4", register_type=RegisterType.INPUT),
}


RELAY_LABELS = {
    0: "ГНВ1 базовая",
    1: "ГНВ2 базовая",
    2: "ГНВ3 базовая",
    3: "ГНВ4 базовая",
    4: "ГНВ5 базовая",
    5: "ГНВ6 базовая",
    6: "ГНВ7 базовая",
    7: "ГНВ8 базовая",
    8: "ГНВ1 туннель",
    9: "ГНВ2 туннель",
    10: "ГНВ3 туннель",
    11: "ГНВ4 туннель",
    12: "ГНВ5 туннель",
    13: "ГНВ6 туннель",
    14: "ГНВ7 туннель",
    15: "ГНВ8 туннель",
}

OUTPUT2_LABELS = {
    0: "ГРВ1 базовая",
    1: "ГРВ2 базовая",
    2: "ГРВ туннель",
    3: "Режим вентиляции",
    4: "Нагреватель 1",
    5: "Нагреватель 2",
    6: "Охладитель",
    7: "Авария",
    8: "Нагреватель 3",
    9: "Нагреватель 4",
    10: "Освещение 1",
    11: "Освещение 2",
    12: "Освещение 3",
    13: "Освещение 4",
    14: "Таймер1 выход 1",
    15: "Таймер1 выход 2",
}

OUTPUT3_LABELS = {
    0: "Таймер1 выход 3",
    1: "Таймер1 выход 4",
    2: "Таймер2 выход 1",
    3: "Таймер2 выход 2",
    4: "Таймер2 выход 3",
    5: "Таймер2 выход 4",
}


SPECIAL_VALUE_MAP = {
    "pending": "⏳",
    "break": "❌ обрыв",
    "error": "⚠️ ошибка",
    "disabled": "🚫 отключено",
    "not_assigned": "🚫 не назначен",
    "unused": "🚫 не используется",
}


def _format_value(value, status):
    if status != "ok" and status in SPECIAL_VALUE_MAP:
        return SPECIAL_VALUE_MAP[status]
    return value


def _format_bitfield(raw: int, labels: Dict[int, str]) -> str:
    active = [labels[bit] for bit in sorted(labels) if raw & (1 << bit)]
    return ", ".join(active) if active else "нет активных"


def read_kub1063_raw(reader: UniversalModbusReader, device: DeviceInfo) -> Dict[int, int]:
    return reader._read_registers_with_types(device.slave_id, REGISTER_SPECS)  # type: ignore[attr-defined]


def parse_kub1063_registers(raw: Dict[int, int]) -> Dict[str, Tuple[object, str]]:
    parsed: Dict[str, Tuple[object, str]] = {}
    for name, info in REGISTER_SPECS.items():
        if info.address not in raw:
            continue
        value = raw[info.address]
        status = "ok"

        if info.special_values and value in info.special_values:
            status = info.special_values[value]
            parsed[name] = (status, status)
            continue

        # Обрабатываем знаковость
        if info.signed:
            if value > 0x7FFF:
                value = value - 0x10000

        if info.value_type == ValueType.VERSION:
            major = value // 100
            minor = value % 100
            parsed[name] = (f"{major}.{minor:02d}", status)
            continue

        if info.value_type == ValueType.BITFIELD:
            parsed[name] = (value, status)
            continue

        if info.value_type in (ValueType.TEMPERATURE, ValueType.FLOAT, ValueType.PERCENTAGE):
            parsed[name] = (value * info.scale, status)
            continue

        parsed[name] = (value, status)

    return parsed


def run_live_kub(port: str, slave_id: int, timeout: float = 0.5) -> bool:
    reader = UniversalModbusReader(port=port, baudrate=9600, timeout=timeout)
    if not reader.connect():
        print(f"❌ Не удалось подключиться к {port}")
        return False

    try:
        device = DeviceInfo(
            device_id=slave_id,
            device_type=DeviceType.KUB_1063,
            slave_id=slave_id,
            name=f"LIVE KUB-1063 #{slave_id}",
            enabled=True,
        )

        print(f"📡 Читаем KUB-1063 (port={port}, slave_id={slave_id})")
        raw = read_kub1063_raw(reader, device)

        if not raw:
            print("❌ Данные не получены")
            return False

        parsed = parse_kub1063_registers(raw)
        print(f"✅ Получены {len(parsed)} переменных")

        def show(name: str, formatter=lambda v: v):
            value, status = parsed.get(name, (None, "missing"))
            if value is None:
                print(f"   {name}: — ({status})")
            elif status != "ok":
                print(f"   {name}: {_format_value(value, status)} ({status})")
            else:
                print(f"   {name}: {formatter(value)}")

        show("software_version")
        show("pressure", lambda v: f"{v:.1f} Па")
        show("humidity", lambda v: f"{v:.1f}%")
        show("co2", lambda v: f"{v:.0f} ppm")
        show("nh3", lambda v: f"{v:.1f} ppm")
        show("grv_base", lambda v: f"{v:.1f}%")
        show("grv_tunnel", lambda v: f"{v:.1f}%")
        show("damper", lambda v: f"{v:.1f}%")
        show("ventilation_target", lambda v: f"{v:.1f}%")
        show("ventilation_level", lambda v: f"{v:.1f}%")
        show("ventilation_scheme")
        show("day_counter")

        for idx in range(1, 5):
            show(f"temp_inside_{idx}", lambda v: f"{v:.1f}°C")
        show("temp_outside", lambda v: f"{v:.1f}°C")
        show("temp_target", lambda v: f"{v:.1f}°C")
        show("temp_inside", lambda v: f"{v:.1f}°C")
        show("temp_vent_activation", lambda v: f"{v:.1f}°C")

        for name in ("digital_outputs_1", "digital_outputs_2", "digital_outputs_3"):
            value, status = parsed.get(name, (None, "missing"))
            if value is None:
                print(f"   {name}: — ({status})")
            elif status != "ok":
                print(f"   {name}: {_format_value(value, status)} ({status})")
            else:
                labels = RELAY_LABELS if name == "digital_outputs_1" else OUTPUT2_LABELS if name == "digital_outputs_2" else OUTPUT3_LABELS
                print(f"   {name}: 0x{int(value):04X}")
                print(f"      активны: {_format_bitfield(int(value), labels)}")

        lighting_names = [
            ("lighting_1", "Освещение 1"),
            ("lighting_2", "Освещение 2"),
            ("lighting_3", "Освещение 3"),
            ("lighting_4", "Освещение 4"),
        ]
        for name, label in lighting_names:
            value, status = parsed.get(name, (None, "missing"))
            if value is None:
                print(f"   {label}: — ({status})")
            elif status != "ok":
                print(f"   {label}: {_format_value(value, status)} ({status})")
            else:
                print(f"   {label}: {value:.1f}%")

        timer_names = [
            ("timer_1_output_1", "Таймер1 выход 1"),
            ("timer_1_output_2", "Таймер1 выход 2"),
            ("timer_1_output_3", "Таймер1 выход 3"),
            ("timer_1_output_4", "Таймер1 выход 4"),
            ("timer_2_output_1", "Таймер2 выход 1"),
            ("timer_2_output_2", "Таймер2 выход 2"),
            ("timer_2_output_3", "Таймер2 выход 3"),
            ("timer_2_output_4", "Таймер2 выход 4"),
        ]
        for name, label in timer_names:
            value, status = parsed.get(name, (None, "missing"))
            if value is None:
                print(f"   {label}: — ({status})")
            elif status != "ok":
                print(f"   {label}: {_format_value(value, status)} ({status})")
            else:
                print(f"   {label}: {value:.1f}%")

        alarm_sections = [
            "active_alarms_0",
            "active_alarms_1",
            "active_alarms_2",
            "active_alarms_3",
            "registered_alarms_0",
            "registered_alarms_1",
            "registered_alarms_2",
            "registered_alarms_3",
        ]
        for name in alarm_sections:
            value, status = parsed.get(name, (None, "missing"))
            if value is None:
                print(f"   {name}: — ({status})")
            elif status != "ok":
                print(f"   {name}: {_format_value(value, status)} ({status})")
            else:
                print(f"   {name}: 0x{int(value):04X}")

        warning_sections = [
            "active_warnings_0",
            "active_warnings_1",
            "active_warnings_2",
            "active_warnings_3",
            "registered_warnings_0",
            "registered_warnings_1",
            "registered_warnings_2",
            "registered_warnings_3",
        ]
        for name in warning_sections:
            value, status = parsed.get(name, (None, "missing"))
            if value is None:
                print(f"   {name}: — ({status})")
            elif status != "ok":
                print(f"   {name}: {_format_value(value, status)} ({status})")
            else:
                print(f"   {name}: 0x{int(value):04X}")

        analog_assignments = [
            ("analog_grv_base", "Аналоговый выход ГРВ базовой"),
            ("analog_grv_tunnel", "Аналоговый выход ГРВ туннель"),
            ("analog_damper", "Аналоговый выход демпфер"),
            ("analog_intake_1", "Аналоговый выход воздухозаборник 1"),
            ("analog_intake_2", "Аналоговый выход воздухозаборник 2"),
            ("analog_intake_tunnel", "Аналоговый выход туннель"),
            ("analog_intake_3", "Аналоговый выход воздухозаборник 3"),
            ("analog_intake_4", "Аналоговый выход воздухозаборник 4"),
            ("analog_light_1", "Аналоговый выход освещение 1"),
            ("analog_light_2", "Аналоговый выход освещение 2"),
            ("analog_light_3", "Аналоговый выход освещение 3"),
            ("analog_light_4", "Аналоговый выход освещение 4"),
            ("analog_timer1_out1", "Аналоговый выход таймер1-1"),
            ("analog_timer1_out2", "Аналоговый выход таймер1-2"),
            ("analog_timer1_out3", "Аналоговый выход таймер1-3"),
            ("analog_timer1_out4", "Аналоговый выход таймер1-4"),
            ("analog_timer2_out1", "Аналоговый выход таймер2-1"),
            ("analog_timer2_out2", "Аналоговый выход таймер2-2"),
            ("analog_timer2_out3", "Аналоговый выход таймер2-3"),
            ("analog_timer2_out4", "Аналоговый выход таймер2-4"),
        ]
        for name, label in analog_assignments:
            value, status = parsed.get(name, (None, "missing"))
            if value is None:
                print(f"   {label}: — ({status})")
            elif status != "ok":
                print(f"   {label}: {_format_value(value, status)} ({status})")
            else:
                print(f"   {label}: {int(value)}")

        return True
    finally:
        reader.disconnect()
        print(f"🔌 Порт {port} закрыт")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Live KUB-1063 reader test (full register map)")
    parser.add_argument("--port", required=True, help="Serial port (e.g. /dev/ttyUSB0)")
    parser.add_argument("--slave", type=int, required=True, help="Slave ID of KUB-1063")
    parser.add_argument("--timeout", type=float, default=0.5)
    args = parser.parse_args(argv)

    return 0 if run_live_kub(args.port, args.slave, args.timeout) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
