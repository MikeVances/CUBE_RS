#!/usr/bin/env python3
"""ESQ-230 drive adapter based on Modbus register map."""

from __future__ import annotations

from typing import Any, Dict, List

from .base import DeviceAdapter, DeviceData, RegisterInfo, RegisterType, ValueType


class ESQ230Adapter(DeviceAdapter):
    """Adapter for ESQ-230 inverter (subset of monitoring registers)."""

    STATUS_MAP = {
        1: "Вперёд",
        2: "Назад",
        3: "Стоп",
    }

    def __init__(self) -> None:
        self._registers: Dict[str, RegisterInfo] = {
            "pid_setpoint": RegisterInfo(0x1010, "pid_setpoint", ValueType.INTEGER, description="Уставка PID", register_type=RegisterType.HOLDING),
            "pid_feedback": RegisterInfo(0x1011, "pid_feedback", ValueType.INTEGER, description="Обратная связь PID", register_type=RegisterType.HOLDING),
            "plc_step": RegisterInfo(0x1012, "plc_step", ValueType.INTEGER, description="Шаг ПЛК", register_type=RegisterType.HOLDING),
            "hdi_pulse_frequency": RegisterInfo(0x1013, "hdi_pulse_frequency", ValueType.INTEGER, unit="kHz", description="Частота импульсов HDI", register_type=RegisterType.HOLDING),
            "remaining_run_time": RegisterInfo(0x1015, "remaining_run_time", ValueType.INTEGER, unit="min", description="Оставшееся время работы", register_type=RegisterType.HOLDING),
            "ai1_raw": RegisterInfo(0x1016, "ai1_raw", ValueType.FLOAT, scale=0.01, unit="V", description="AI1 до коррекции", register_type=RegisterType.HOLDING),
            "ai2_raw": RegisterInfo(0x1017, "ai2_raw", ValueType.FLOAT, scale=0.01, unit="V", description="AI2 до коррекции", register_type=RegisterType.HOLDING),
            "ai3_raw": RegisterInfo(0x1018, "ai3_raw", ValueType.FLOAT, scale=0.01, unit="V", description="AI3 до коррекции", register_type=RegisterType.HOLDING),
            "linear_speed": RegisterInfo(0x1019, "linear_speed", ValueType.INTEGER, description="Линейная скорость", register_type=RegisterType.HOLDING),
            "current_power_on_time": RegisterInfo(0x101A, "current_power_on_time", ValueType.INTEGER, unit="min", description="Текущее время включения", register_type=RegisterType.HOLDING),
            "current_running_time": RegisterInfo(0x101B, "current_running_time", ValueType.INTEGER, unit="min", description="Текущее время работы", register_type=RegisterType.HOLDING),
            "hdi_command": RegisterInfo(0x101C, "hdi_command", ValueType.INTEGER, description="Задание входа HDI", register_type=RegisterType.HOLDING),
            "protocol_command": RegisterInfo(0x101D, "protocol_command", ValueType.INTEGER, description="Задание протокола", register_type=RegisterType.HOLDING),
            "channel_x": RegisterInfo(0x101F, "channel_x", ValueType.INTEGER, description="Канал X", register_type=RegisterType.HOLDING),
            "channel_y": RegisterInfo(0x1020, "channel_y", ValueType.INTEGER, description="Канал Y", register_type=RegisterType.HOLDING),
            "status_word": RegisterInfo(0x3000, "status_word", ValueType.BITFIELD, description="Регистр состояния", register_type=RegisterType.HOLDING),
        }

    @property
    def device_type(self) -> str:
        return "ESQ-230"

    @property
    def register_map(self) -> Dict[str, RegisterInfo]:
        return self._registers

    def parse_register_value(self, register_name: str, raw_value: int) -> tuple[Any, str]:
        info = self._registers.get(register_name)
        if not info:
            return raw_value, "unknown"

        special = self._check_special_values(raw_value, info)
        if special:
            return special, special

        value = self._apply_scale_and_sign(raw_value, info)

        if register_name == "status_word":
            return self.STATUS_MAP.get(raw_value, f"код {raw_value}"), "ok"

        return value, "ok"

    def format_for_display(self, data: DeviceData) -> str:
        lines = [f"⚙️ ESQ-230 #{data.device_id}"]
        status = data.registers.get("status_word") or "—"
        lines.append(f"Статус: {status}")
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
        # ESQ-230 в рамках мониторинга U1 регистров не предоставляет явных аварий,
        # поэтому отдаём пустой список.
        return []

    def get_warnings(self, data: DeviceData) -> List[str]:
        warnings: List[str] = []
        remaining = data.registers.get("remaining_run_time")
        if isinstance(remaining, (int, float)) and remaining < 60:
            warnings.append("Мало оставшегося времени работы (<60 мин)")
        return warnings
