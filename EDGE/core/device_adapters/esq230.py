#!/usr/bin/env python3
"""ESQ-230 drive adapter based on Modbus register map."""

from __future__ import annotations

from typing import Any, Dict, List

from .base import DeviceAdapter, DeviceData, RegisterInfo, RegisterType, ValueType


class ESQ230Adapter(DeviceAdapter):
    """Adapter for ESQ-230 inverter (subset of monitoring registers)."""

    DEFAULT_DASHBOARD_METRICS = [
        "running_speed",
        "set_frequency",
        "output_voltage",
        "output_current",
        "output_power",
        "remaining_run_time",
    ]

    FAULT_MAP = {
        0x0000: "Ошибок нет",
        0x0001: "Зарезервировано",
        0x0002: "Перегрузка по току (разгон)",
        0x0003: "Перегрузка по току (торможение)",
        0x0004: "Перегрузка по току (номинальная)",
        0x0005: "Перенапряжение при разгоне",
        0x0006: "Перенапряжение при торможении",
        0x0007: "Перенапряжение при номинальной скорости",
        0x0008: "Зарезервировано",
        0x0009: "Пониженное напряжение",
        0x000A: "Перегрузка преобразователя",
        0x000B: "Перегрузка двигателя",
        0x000C: "Потеря входной фазы",
        0x000D: "Потеря выходной фазы",
        0x000E: "Перегрев модуля",
        0x000F: "Внешняя авария",
        0x0010: "Ошибка связи",
        0x0011: "Сбой контактора",
        0x0012: "Ошибка датчиков тока",
        0x0013: "Сбой автонастройки",
        0x0015: "Ошибка памяти",
        0x0016: "Аппаратная неисправность",
        0x0017: "Замыкание выхода на землю",
        0x0018: "Зарезервировано",
        0x0019: "Зарезервировано",
        0x001A: "Достигнуто суммарное время работы",
        0x001B: "Пользовательская ошибка 1",
        0x001C: "Пользовательская ошибка 2",
        0x001D: "Достигнуто суммарное время включения",
        0x001E: "Потеря нагрузки",
        0x001F: "Потеря обратной связи",
        0x0028: "Неисправность ограничения тока",
    }

    PROTOCOL_FAULT_MAP = {
        0x0000: "Ошибок связи нет",
        0x0001: "Неверный пароль",
        0x0002: "Ошибка кода команды",
        0x0003: "Ошибка CRC",
        0x0004: "Недействительный адрес",
        0x0005: "Недействительный параметр",
        0x0006: "Редактирование параметров невозможно",
        0x0007: "Система заблокирована",
        0x0008: "Запись в ПЗУ во время работы",
    }

    def __init__(self) -> None:
        self._registers: Dict[str, RegisterInfo] = {
            # Документация называет мониторинговые регистры «input only»,
            # но реальный привод отвечает только на FC03, поэтому явно
            # помечаем их как HOLDING, чтобы опросник использовал FC03.
            "set_frequency": RegisterInfo(0x1001, "set_frequency", ValueType.FLOAT, unit="Гц", scale=0.01, description="Заданная частота", register_type=RegisterType.HOLDING),
            "dc_bus_voltage": RegisterInfo(0x1002, "dc_bus_voltage", ValueType.FLOAT, unit="В", scale=0.1, description="Напряжение звена постоянного тока"),
            "output_voltage": RegisterInfo(0x1003, "output_voltage", ValueType.FLOAT, unit="В", scale=0.1, description="Выходное напряжение"),
            "output_current": RegisterInfo(0x1004, "output_current", ValueType.FLOAT, unit="А", scale=0.1, description="Выходной ток"),
            "output_power": RegisterInfo(0x1005, "output_power", ValueType.FLOAT, unit="кВт", scale=0.001, description="Выходная мощность"),
            "output_torque": RegisterInfo(0x1006, "output_torque", ValueType.FLOAT, unit="Н·м", scale=0.1, description="Выходной крутящий момент"),
            "running_speed": RegisterInfo(0x1007, "running_speed", ValueType.FLOAT, unit="Гц", scale=0.01, description="Рабочая скорость"),
            "input_status": RegisterInfo(0x1008, "input_status", ValueType.BITFIELD, description="Состояние входных клемм"),
            "output_status": RegisterInfo(0x1009, "output_status", ValueType.BITFIELD, description="Состояние выходных клемм"),
            "ai1_voltage": RegisterInfo(0x100A, "ai1_voltage", ValueType.FLOAT, scale=0.01, unit="В", description="Напряжение AI1"),
            "ai2_voltage": RegisterInfo(0x100B, "ai2_voltage", ValueType.FLOAT, scale=0.01, unit="В", description="Напряжение AI2"),
            "ai3_voltage": RegisterInfo(0x100C, "ai3_voltage", ValueType.FLOAT, scale=0.01, unit="В", description="Напряжение AI3"),
            "counter_value": RegisterInfo(0x100D, "counter_value", ValueType.INTEGER, description="Значение счётчика"),
            "length_value": RegisterInfo(0x100E, "length_value", ValueType.INTEGER, description="Значение длины"),
            "load_speed": RegisterInfo(0x100F, "load_speed", ValueType.INTEGER, description="Скорость нагрузки"),
            "pid_setpoint": RegisterInfo(0x1010, "pid_setpoint", ValueType.INTEGER, description="Уставка PID"),
            "pid_feedback": RegisterInfo(0x1011, "pid_feedback", ValueType.INTEGER, description="Обратная связь PID"),
            "plc_step": RegisterInfo(0x1012, "plc_step", ValueType.INTEGER, description="Шаг ПЛК"),
            "hdi_pulse_frequency": RegisterInfo(0x1013, "hdi_pulse_frequency", ValueType.INTEGER, unit="kHz", description="Частота импульсов HDI"),
            "remaining_run_time": RegisterInfo(0x1015, "remaining_run_time", ValueType.INTEGER, unit="min", description="Оставшееся время работы"),
            "ai1_raw": RegisterInfo(0x1016, "ai1_raw", ValueType.FLOAT, scale=0.01, unit="V", description="AI1 до коррекции"),
            "ai2_raw": RegisterInfo(0x1017, "ai2_raw", ValueType.FLOAT, scale=0.01, unit="V", description="AI2 до коррекции"),
            "ai3_raw": RegisterInfo(0x1018, "ai3_raw", ValueType.FLOAT, scale=0.01, unit="V", description="AI3 до коррекции"),
            "linear_speed": RegisterInfo(0x1019, "linear_speed", ValueType.INTEGER, description="Линейная скорость"),
            "current_power_on_time": RegisterInfo(0x101A, "current_power_on_time", ValueType.INTEGER, unit="min", description="Текущее время включения"),
            "current_running_time": RegisterInfo(0x101B, "current_running_time", ValueType.INTEGER, unit="min", description="Текущее время работы"),
            "hdi_command": RegisterInfo(0x101C, "hdi_command", ValueType.INTEGER, description="Задание входа HDI"),
            "protocol_command": RegisterInfo(0x101D, "protocol_command", ValueType.INTEGER, description="Задание протокола"),
            "channel_x": RegisterInfo(0x101F, "channel_x", ValueType.INTEGER, description="Канал X"),
            "channel_y": RegisterInfo(0x1020, "channel_y", ValueType.INTEGER, description="Канал Y"),
        }

    @property
    def device_type(self) -> str:
        return "ESQ-230"

    @property
    def register_map(self) -> Dict[str, RegisterInfo]:
        return self._registers

    @property
    def max_batch_size(self) -> int:
        # Привод уверенно отвечает на блоки до ~6 регистров, большие запросы
        # часто приводят к пустым ответам. Ограничим пакет при опросе.
        return 6

    def parse_register_value(self, register_name: str, raw_value: int) -> tuple[Any, str]:
        info = self._registers.get(register_name)
        if not info:
            return raw_value, "unknown"

        special = self._check_special_values(raw_value, info)
        if special:
            return special, special

        value = self._apply_scale_and_sign(raw_value, info)

        return value, "ok"

    def format_for_display(self, data: DeviceData) -> str:
        lines = [f"⚙️ ESQ-230 #{data.device_id}"]
        remaining = data.registers.get("remaining_run_time")
        if remaining is not None:
            lines.append(f"Оставшееся время работы: {remaining} мин")
        runtime = data.registers.get("current_running_time")
        if runtime is not None:
            lines.append(f"Текущее время работы: {runtime} мин")
        pid = data.registers.get("pid_setpoint")
        fb = data.registers.get("pid_feedback")
        if pid is not None or fb is not None:
            lines.append(f"PID: зад={pid}, обр={fb}")
        return "\n".join(lines)

    def get_critical_alarms(self, data: DeviceData) -> List[str]:
        return []

    def get_warnings(self, data: DeviceData) -> List[str]:
        warnings: List[str] = []
        remaining = data.registers.get("remaining_run_time")
        if isinstance(remaining, (int, float)) and remaining < 60:
            warnings.append("Мало оставшегося времени работы (<60 мин)")
        return warnings
