#!/usr/bin/env python3
"""
VFD/Inverter Device Adapter
Адаптер для регулятора скорости (Variable Frequency Drive)
На основе инструкции с Modbus регистрами U0-00 до U0-71
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from .base import (
    DeviceAdapter,
    RegisterInfo,
    ValueType,
    DeviceData,
)


READABLE_KEYS = {
    "running_state",
    "fault_code",
    "set_frequency",
    "running_frequency",
    "running_speed",
    "output_voltage",
    "output_current",
    "output_power",
    "dc_bus_voltage",
    "output_torque",
    "motor_temperature",
    "igbt_temperature",
    "di_input_state",
    "current_power_on_time",
    "current_running_time",
    "cumulative_running_time",
    "accumulated_power_on_time",
    "cumulative_power_consumption",
}


class VFDInverterAdapter(DeviceAdapter):
    """Адаптер для регулятора скорости VFD/Inverter"""

    DEFAULT_DASHBOARD_METRICS = [
        "running_speed",
        "running_frequency",
        "set_frequency",
        "output_voltage",
        "output_current",
        "output_power",
    ]

    # Предпочтительные параметры Modbus для этого инвертора
    # - регистры мониторинга читаются через FC03 (Holding Registers)
    # - база адресов U0-xx начинается с 0x1000 (смещение 0)
    PREFERRED_READ_FUNCTION = "holding"  # либо "input" при альтернативных прошивках
    ADDRESS_BASE = 0x1000
    ADDRESS_OFFSET = 0

    # Коды ошибок (по руководству) → краткое название и рекомендации
    # Значения регистров обычно соответствуют числу из "ErrXX" (например, 1 → Err01)
    FAULT_MAP = {
        1: ("Защита силового модуля", "Проверьте КЗ/пробой на выходе, длину кабеля двигателя, охлаждение; восстановите соединения; при необходимости — сервис"),
        2: ("Перегрузка по току при разгоне", "Устраните внешние причины, выполните автонастройку двигателя, увеличьте время разгона, откорректируйте V/F/boost, нормализуйте напряжение, снизьте нагрузку"),
        3: ("Перегрузка по току при торможении", "Устраните внешние причины, выполните автонастройку, увеличьте время торможения, нормализуйте напряжение, установите тормозной блок/резистор"),
        4: ("Перегрузка по току на постоянной скорости", "Проверьте КЗ/пробой, выполните автонастройку, нормализуйте напряжение, уменьшите нагрузку/подберите мощность"),
        5: ("Перенапряжение при разгоне", "Нормализуйте входное напряжение, исключите внешнюю раскрутку, увеличьте время разгона, установите тормозной резистор"),
        6: ("Перенапряжение при торможении", "Нормализуйте входное напряжение, исключите внешнюю силу при торможении, увеличьте время торможения, установите тормозной резистор"),
        7: ("Перенапряжение на постоянной скорости", "Нормализуйте напряжение; исключите внешнюю силу или установите тормозной резистор"),
        8: ("Ошибка питания цепей управления", "Приведите входное напряжение к допустимому диапазону"),
        9: ("Пониженное напряжение", "Проверьте питание и DC‑шину, выпрямитель/буферный резистор; при необходимости — сервис"),
        10: ("Перегрузка инвертора", "Снизьте нагрузку/проверьте механику; при необходимости — привод большего класса"),
        11: ("Перегрузка двигателя", "Снизьте нагрузку; при необходимости — привод большего класса"),
        12: ("Потеря фазы на входе", "Устраните внешние неисправности трёхфазного ввода; при необходимости — сервис"),
        13: ("Потеря фазы на выходе", "Проверьте кабель/соединения двигателя, баланс фаз; при необходимости — сервис"),
        14: ("Перегрев модуля", "Понизьте температуру, очистите фильтр, замените вентилятор/датчик; при необходимости — модуль"),
        15: ("Внешняя авария", "Проверьте внешний аварийный вход, сбросьте аварию"),
        16: ("Ошибка связи", "Проверьте кабель связи/подключение, параметры Modbus"),
        17: ("Ошибка контактора", "Замените контактoр и/или драйверную/питающую плату"),
        18: ("Ошибка датчика тока", "Проверьте/замените датчик Холла или драйверную плату"),
        19: ("Ошибка автонастройки двигателя", "Установите правильные паспортные параметры, проверьте соединение двигателя, повторите автонастройку"),
        21: ("Ошибка записи EEPROM", "Замените основную плату"),
        22: ("Аппаратная ошибка инвертора", "Устраните перенапряжение/перегрузку по току"),
        26: ("Достигнуто суммарное время работы", "Сбросьте счётчик через функцию инициализации параметров"),
        29: ("Достигнуто суммарное время включения", "Сбросьте счётчик через функцию инициализации параметров"),
        40: ("Ограничение тока импульсами", "Снизьте нагрузку/проверьте механику; при необходимости — привод большего класса"),
        41: ("Переключение типа двигателя на ходу", "Выполняйте переключение типа двигателя только после остановки"),
        42: ("Чрезмерное отклонение скорости", "Проверьте уставки контроля скорости; выполните идентификацию параметров"),
        53: ("Переподавление/перегрузка по давлению", "Проверьте датчик давления и корректность параметров инвертора"),
    }

    @classmethod
    def fault_description(cls, code: int) -> Optional[str]:
        info = cls.FAULT_MAP.get(code)
        if not info:
            return None
        title, advice = info
        return f"{title}. Рекомендации: {advice}"

    @staticmethod
    def _parse_fault_code(value) -> Optional[int]:
        """Преобразует значение fault_code в int, учитывая текстовые значения симулятора."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            try:
                return int(value)
            except ValueError:
                return None
        if isinstance(value, str):
            normalized = value.strip().lower()
            if not normalized or normalized in {"no_fault", "none", "ok"}:
                return 0
            try:
                return int(normalized, 10)
            except ValueError:
                return None
        return None

    @property
    def device_type(self) -> str:
        return "VFD-INVERTER"

    @property
    def register_map(self) -> Dict[str, RegisterInfo]:
        """
        Карта регистров VFD Inverter
        Базовый адрес: 0x1000H
        """
        regs = {
            # === MONITORING PARAMETERS (Read-Only) ===

            # U0-00: Inverter Running State (1: forward, 2: reverse, 3: stop)
            "running_state": RegisterInfo(
                address=0x1000,
                name="running_state",
                value_type=ValueType.INTEGER,
                unit=None,
                description="Состояние привода: 1 — вперёд, 2 — назад, 3 — стоп"
            ),

            # U0-01: Fault Code
            "fault_code": RegisterInfo(
                address=0x1001,
                name="fault_code",
                value_type=ValueType.INTEGER,
                unit=None,
                description="Текущий код аварии"
            ),

            # U0-02: Set Frequency
            "set_frequency": RegisterInfo(
                address=0x1002,
                name="set_frequency",
                value_type=ValueType.FLOAT,
                unit="Hz",
                scale=0.1,
                description="Заданное значение частоты"
            ),

            # U0-03: Running Frequency
            "running_frequency": RegisterInfo(
                address=0x1003,
                name="running_frequency",
                value_type=ValueType.FLOAT,
                unit="Hz",
                scale=0.1,
                description="Фактическая рабочая частота"
            ),

            # U0-04: Running Speed
            "running_speed": RegisterInfo(
                address=0x1004,
                name="running_speed",
                value_type=ValueType.INTEGER,
                unit="RPM",
                description="Скорость двигателя, об/мин"
            ),

            # U0-05: Output Voltage
            "output_voltage": RegisterInfo(
                address=0x1005,
                name="output_voltage",
                value_type=ValueType.FLOAT,
                unit="V",
                scale=1.0,
                description="Выходное напряжение на двигатель"
            ),

            # U0-06: Output Current
            "output_current": RegisterInfo(
                address=0x1006,
                name="output_current",
                value_type=ValueType.FLOAT,
                unit="A",
                scale=0.1,
                description="Выходной ток на двигатель"
            ),

            # U0-07: Output Power
            "output_power": RegisterInfo(
                address=0x1007,
                name="output_power",
                value_type=ValueType.FLOAT,
                unit="kW",
                scale=0.1,
                description="Выходная мощность"
            ),

            # U0-08: DC Bus Voltage
            "dc_bus_voltage": RegisterInfo(
                address=0x1008,
                name="dc_bus_voltage",
                value_type=ValueType.FLOAT,
                unit="V",
                scale=1.0,
                description="Напряжение звена постоянного тока"
            ),

            # U0-09: Output Torque
            "output_torque": RegisterInfo(
                address=0x1009,
                name="output_torque",
                value_type=ValueType.FLOAT,
                unit="Nm",
                scale=0.1,
                description="Момент на валу двигателя"
            ),

            # U0-10: Power Factor Angle
            "power_factor_angle": RegisterInfo(
                address=0x100A,
                name="power_factor_angle",
                value_type=ValueType.INTEGER,
                unit=None,
                description="Угол сдвига фаз (cos φ)"
            ),

            # U0-11: DI Input State
            "di_input_state": RegisterInfo(
                address=0x100B,
                name="di_input_state",
                value_type=ValueType.BITFIELD,
                unit=None,
                description="Состояние дискретных входов (битовое поле)"
            ),

            # U0-13: AI1 Voltage Before Correction
            "ai1_voltage_before_correction": RegisterInfo(
                address=0x100D,
                name="ai1_voltage_before_correction",
                value_type=ValueType.FLOAT,
                unit="V",
                scale=0.01,
                description="Напряжение AI1 до коррекции"
            ),

            # U0-15: AI1 Voltage
            "ai1_voltage": RegisterInfo(
                address=0x100F,
                name="ai1_voltage",
                value_type=ValueType.FLOAT,
                unit="V",
                scale=0.01,
                description="Напряжение AI1 после коррекции"
            ),

            # U0-17: PID Setting
            "pid_setting": RegisterInfo(
                address=0x1011,
                name="pid_setting",
                value_type=ValueType.INTEGER,
                unit=None,
                description="Уставка PID-регулятора"
            ),

            # U0-18: PID Feedback
            "pid_feedback": RegisterInfo(
                address=0x1012,
                name="pid_feedback",
                value_type=ValueType.INTEGER,
                unit=None,
                description="Обратная связь PID-регулятора"
            ),

            # U0-19: Remaining Running Time
            "remaining_running_time": RegisterInfo(
                address=0x1013,
                name="remaining_running_time",
                value_type=ValueType.FLOAT,
                unit="Min",
                scale=0.1,
                description="Оставшееся время работы, мин"
            ),

            # U0-20: Current Power-on Time
            "current_power_on_time": RegisterInfo(
                address=0x1014,
                name="current_power_on_time",
                value_type=ValueType.INTEGER,
                unit="Min",
                description="Время текущего включения, мин"
            ),

            # U0-21: Current Running Time
            "current_running_time": RegisterInfo(
                address=0x1015,
                name="current_running_time",
                value_type=ValueType.FLOAT,
                unit="Min",
                scale=0.1,
                description="Длительность текущего цикла, мин"
            ),

            # U0-22: Cumulative Running Time
            "cumulative_running_time": RegisterInfo(
                address=0x1016,
                name="cumulative_running_time",
                value_type=ValueType.INTEGER,
                unit="Hour",
                description="Суммарное время работы, ч"
            ),

            # U0-23: Accumulated Power-on Time
            "accumulated_power_on_time": RegisterInfo(
                address=0x1017,
                name="accumulated_power_on_time",
                value_type=ValueType.INTEGER,
                unit="Hour",
                description="Суммарное время включений, ч"
            ),

            # U0-24: Cumulative Power Consumption
            "cumulative_power_consumption": RegisterInfo(
                address=0x1018,
                name="cumulative_power_consumption",
                value_type=ValueType.FLOAT,
                unit="kWh",
                scale=1.0,
                description="Накопленное энергопотребление, кВт·ч"
            ),

            # U0-25: Motor Temperature Value
            "motor_temperature": RegisterInfo(
                address=0x1019,
                name="motor_temperature",
                value_type=ValueType.TEMPERATURE,
                unit="°C",
                scale=1.0,
                signed=True,
                description="Температура двигателя"
            ),

            # U0-26: IGBT Temperature Value
            "igbt_temperature": RegisterInfo(
                address=0x101A,
                name="igbt_temperature",
                value_type=ValueType.TEMPERATURE,
                unit="°C",
                scale=1.0,
                signed=True,
                description="Температура модуля IGBT / радиатора"
            ),

            # U0-27: Actual Switching Frequency
            "actual_switching_frequency": RegisterInfo(
                address=0x101B,
                name="actual_switching_frequency",
                value_type=ValueType.FLOAT,
                unit="kHz",
                scale=0.1,
                description="Фактическая частота ШИМ"
            ),

            # U0-28: M-axis Current Actual Value
            "m_axis_current": RegisterInfo(
                address=0x101C,
                name="m_axis_current",
                value_type=ValueType.FLOAT,
                unit="A",
                scale=0.1,
                description="Ток по оси M (моментная составляющая)"
            ),

            # U0-29: T-axis Current Actual Value
            "t_axis_current": RegisterInfo(
                address=0x101D,
                name="t_axis_current",
                value_type=ValueType.FLOAT,
                unit="A",
                scale=0.1,
                description="Ток по оси T (потоковая составляющая)"
            ),

            # U0-30: Feedback Speed Actual Value
            "feedback_speed": RegisterInfo(
                address=0x101E,
                name="feedback_speed",
                value_type=ValueType.INTEGER,
                unit="Hz",
                description="Скорость по обратной связи энкодера"
            ),

            # === DEVICE INFORMATION ===

            # U0-42: Product Serial Number Lower 16 Digits
            "serial_number_low": RegisterInfo(
                address=0x102B,
                name="serial_number_low",
                value_type=ValueType.INTEGER,
                unit=None,
                description="Серийный номер (младшие 16 бит)"
            ),

            # U0-43: Product Serial Number Higher 16 Digits
            "serial_number_high": RegisterInfo(
                address=0x102C,
                name="serial_number_high",
                value_type=ValueType.INTEGER,
                unit=None,
                description="Серийный номер (старшие 16 бит)"
            ),

            # U0-44: Motor Boot Version
            "motor_boot_version": RegisterInfo(
                address=0x102D,
                name="motor_boot_version",
                value_type=ValueType.VERSION,
                unit=None,
                description="Версия загрузчика двигателя"
            ),

            # U0-45: CPU Type
            "cpu_type": RegisterInfo(
                address=0x102E,
                name="cpu_type",
                value_type=ValueType.INTEGER,
                unit=None,
                description="Идентификатор типа CPU"
            ),

            # U0-46: Power Board Hardware Version
            "power_board_hw_version": RegisterInfo(
                address=0x102F,
                name="power_board_hw_version",
                value_type=ValueType.VERSION,
                unit=None,
                description="Версия аппаратной части силовой платы"
            ),

            # U0-47: Power Board Software Version
            "power_board_sw_version": RegisterInfo(
                address=0x1030,
                name="power_board_sw_version",
                value_type=ValueType.VERSION,
                unit=None,
                description="Версия ПО силовой платы"
            ),

            # U0-48: Control Board Software Version
            "control_board_sw_version": RegisterInfo(
                address=0x1031,
                name="control_board_sw_version",
                value_type=ValueType.VERSION,
                unit=None,
                description="Версия ПО управляющей платы"
            ),

            # U0-49: Product Number
            "product_number": RegisterInfo(
                address=0x1032,
                name="product_number",
                value_type=ValueType.INTEGER,
                unit=None,
                description="Код модели привода"
            ),

            # U0-50: Manufacturer Code
            "manufacturer_code": RegisterInfo(
                address=0x1033,
                name="manufacturer_code",
                value_type=ValueType.INTEGER,
                unit=None,
                description="Код производителя"
            ),

            # === FAULT HISTORY (Last 3 Faults) ===

            # U0-51: Third (most recent) Fault Code
            "fault_third_code": RegisterInfo(
                address=0x1034,
                name="fault_third_code",
                value_type=ValueType.INTEGER,
                unit=None,
                description="Последний (третий) код аварии"
            ),

            # U0-52: Second Fault Code
            "fault_second_code": RegisterInfo(
                address=0x1035,
                name="fault_second_code",
                value_type=ValueType.INTEGER,
                unit=None,
                description="Предыдущий (второй) код аварии"
            ),

            # U0-53: First Fault Code
            "fault_first_code": RegisterInfo(
                address=0x1036,
                name="fault_first_code",
                value_type=ValueType.INTEGER,
                unit=None,
                description="Самый ранний код из последних трёх аварий"
            ),

            # === THIRD FAULT DETAILS ===

            "fault_third_frequency": RegisterInfo(
                address=0x1037,
                name="fault_third_frequency",
                value_type=ValueType.FLOAT,
                unit="Hz",
                scale=0.1,
                description="Частота при третьей аварии"
            ),

            "fault_third_current": RegisterInfo(
                address=0x1038,
                name="fault_third_current",
                value_type=ValueType.FLOAT,
                unit="A",
                scale=0.1,
                description="Ток при третьей аварии"
            ),

            "fault_third_dc_voltage": RegisterInfo(
                address=0x1039,
                name="fault_third_dc_voltage",
                value_type=ValueType.FLOAT,
                unit="V",
                scale=0.1,
                description="Напряжение звена DC при третьей аварии"
            ),

            "fault_third_temperature": RegisterInfo(
                address=0x103A,
                name="fault_third_temperature",
                value_type=ValueType.TEMPERATURE,
                unit="°C",
                scale=1.0,
                signed=True,
                description="Температура радиатора при третьей аварии"
            ),

            "fault_third_time_power_on": RegisterInfo(
                address=0x103B,
                name="fault_third_time_power_on",
                value_type=ValueType.INTEGER,
                unit="Min",
                description="Накопленное время включения к моменту 3-й аварии"
            ),

            "fault_third_time_running": RegisterInfo(
                address=0x103C,
                name="fault_third_time_running",
                value_type=ValueType.FLOAT,
                unit="Hour",
                scale=0.1,
                description="Накопленное время работы к моменту 3-й аварии"
            ),

            # === SECOND FAULT DETAILS ===

            "fault_second_frequency": RegisterInfo(
                address=0x103D,
                name="fault_second_frequency",
                value_type=ValueType.FLOAT,
                unit="Hz",
                scale=0.1,
                description="Частота при второй аварии"
            ),

            "fault_second_current": RegisterInfo(
                address=0x103E,
                name="fault_second_current",
                value_type=ValueType.FLOAT,
                unit="A",
                scale=0.1,
                description="Ток при второй аварии"
            ),

            "fault_second_dc_voltage": RegisterInfo(
                address=0x103F,
                name="fault_second_dc_voltage",
                value_type=ValueType.FLOAT,
                unit="V",
                scale=0.1,
                description="Напряжение звена DC при второй аварии"
            ),

            "fault_second_temperature": RegisterInfo(
                address=0x1040,
                name="fault_second_temperature",
                value_type=ValueType.TEMPERATURE,
                unit="°C",
                scale=1.0,
                signed=True,
                description="Температура радиатора при второй аварии"
            ),

            "fault_second_time_power_on": RegisterInfo(
                address=0x1041,
                name="fault_second_time_power_on",
                value_type=ValueType.INTEGER,
                unit="Min",
                description="Накопленное время включения к моменту 2-й аварии"
            ),

            "fault_second_time_running": RegisterInfo(
                address=0x1042,
                name="fault_second_time_running",
                value_type=ValueType.FLOAT,
                unit="Hour",
                scale=0.1,
                description="Накопленное время работы к моменту 2-й аварии"
            ),

            # === FIRST FAULT DETAILS ===

            "fault_first_frequency": RegisterInfo(
                address=0x1043,
                name="fault_first_frequency",
                value_type=ValueType.FLOAT,
                unit="Hz",
                scale=0.1,
                description="Частота при первой аварии"
            ),

            "fault_first_current": RegisterInfo(
                address=0x1044,
                name="fault_first_current",
                value_type=ValueType.FLOAT,
                unit="A",
                scale=0.1,
                description="Ток при первой аварии"
            ),

            "fault_first_dc_voltage": RegisterInfo(
                address=0x1045,
                name="fault_first_dc_voltage",
                value_type=ValueType.FLOAT,
                unit="V",
                scale=0.1,
                description="Напряжение звена DC при первой аварии"
            ),

            "fault_first_temperature": RegisterInfo(
                address=0x1046,
                name="fault_first_temperature",
                value_type=ValueType.TEMPERATURE,
                unit="°C",
                scale=1.0,
                signed=True,
                description="Температура радиатора при первой аварии"
            ),

            "fault_first_time_power_on": RegisterInfo(
                address=0x1047,
                name="fault_first_time_power_on",
                value_type=ValueType.INTEGER,
                unit="Min",
                description="Накопленное время включения к моменту 1-й аварии"
            ),

            "fault_first_time_running": RegisterInfo(
                address=0x1048,
                name="fault_first_time_running",
                value_type=ValueType.FLOAT,
                unit="Hour",
                scale=0.1,
                description="Накопленное время работы к моменту 1-й аварии"
            ),
        }

        # Некоторые реальные VFD (например, модель на объекте) реализуют только
        # диапазон U0-00..U0-26 (0x1000–0x101B). Чтобы избежать Modbus
        # исключений при чтении несуществующих адресов, ограничиваем карту теми
        # регистрами, чей адрес <= 0x101B. Остальные остаются задокументированными,
        # но не участвуют в live polling.
        supported_regs = {
            name: info
            for name, info in regs.items()
            if name in READABLE_KEYS
        }
        return supported_regs

    def parse_register_value(
        self, register_name: str, raw_value: int
    ) -> tuple[Any, str]:
        """
        Парсинг значения регистра VFD

        Returns:
            tuple: (parsed_value, status)
        """
        register_info = self.register_map.get(register_name)
        if not register_info:
            return raw_value, "unknown_register"

        # Проверяем специальные значения
        special = self._check_special_values(raw_value, register_info)
        if special:
            return special, special

        # Применяем масштаб и знак
        value = self._apply_scale_and_sign(raw_value, register_info)

        # Специальная обработка для running_state
        if register_name == "running_state":
            # Русская локализация состояний
            states_ru = {1: "вперёд", 2: "реверс", 3: "стоп"}
            return states_ru.get(raw_value, f"неизвестно_{raw_value}"), "ok"

        # Специальная обработка для fault codes
        if "fault" in register_name and "_code" in register_name:
            if raw_value == 0:
                return "no_fault", "ok"
            else:
                return raw_value, "fault_detected"

        # Проверка диапазонов для температур
        if register_info.value_type == ValueType.TEMPERATURE:
            if value > 100:
                return value, "overtemperature"
            elif value > 80:
                return value, "high_temperature"

        # Проверка для токов (перегрузка)
        if "current" in register_name and register_info.unit == "A":
            if value > 100:  # Примерный порог, должен быть из спецификации
                return value, "overcurrent"

        # Проверка для напряжений
        if "voltage" in register_name:
            if value < 100 or value > 500:  # Примерные пороги
                return value, "voltage_out_of_range"

        return value, "ok"

    def format_for_display(self, data: DeviceData) -> str:
        """Форматирование данных VFD для отображения"""
        lines = []
        lines.append(f"🔌 Инвертор VFD: {data.device_id}")
        lines.append("")

        # Состояние работы
        state = data.registers.get("running_state", "неизвестно")
        # Поддержка как русских, так и англ. значений
        state_key = {
            "forward": "forward",
            "reverse": "reverse",
            "stop": "stop",
            "вперёд": "forward",
            "реверс": "reverse",
            "стоп": "stop",
        }.get(str(state).lower(), "unknown")
        state_emoji = {"forward": "▶️", "reverse": "◀️", "stop": "⏹️"}.get(state_key, "❓")
        lines.append(f"{state_emoji} Состояние: {state}")

        # Частота и скорость
        freq = data.registers.get("running_frequency", 0)
        speed = data.registers.get("running_speed", 0)
        lines.append(f"⚡ Частота: {freq} Hz")
        lines.append(f"🔄 Скорость: {speed} RPM")

        # Электрические параметры
        voltage = data.registers.get("output_voltage", 0)
        current = data.registers.get("output_current", 0)
        power = data.registers.get("output_power", 0)
        lines.append(f"⚡ Напряжение: {voltage} V")
        lines.append(f"⚡ Ток: {current} A")
        lines.append(f"⚡ Мощность: {power} kW")

        # Температуры
        motor_temp = data.registers.get("motor_temperature")
        igbt_temp = data.registers.get("igbt_temperature")
        if motor_temp is not None:
            temp_emoji = "🔥" if motor_temp > 80 else "🌡️"
            lines.append(f"{temp_emoji} Т мотора: {motor_temp}°C")
        if igbt_temp is not None:
            temp_emoji = "🔥" if igbt_temp > 80 else "🌡️"
            lines.append(f"{temp_emoji} Т IGBT: {igbt_temp}°C")

        # Fault code
        fault = data.registers.get("fault_code", 0)
        if fault != 0 and fault != "no_fault":
            desc = self.fault_description(fault)
            if desc:
                lines.append(f"⚠️ Ошибка Err{int(fault):02d}: {desc}")
            else:
                lines.append(f"⚠️ Код ошибки: Err{int(fault):02d}")

        # Время работы
        running_time = data.registers.get("cumulative_running_time")
        if running_time is not None:
            lines.append(f"⏱️ Время работы: {running_time} ч")

        # Потребление энергии
        power_consumption = data.registers.get("cumulative_power_consumption")
        if power_consumption is not None:
            lines.append(f"⚡ Потребление: {power_consumption} kWh")

        return "\n".join(lines)

    def get_critical_alarms(self, data: DeviceData) -> List[str]:
        """Получение критичных аварий VFD"""
        alarms = []

        # Проверка fault code
        fault = data.registers.get("fault_code")
        if fault and fault != 0 and fault != "no_fault":
            desc = self.fault_description(int(fault))
            if desc:
                alarms.append(f"Активная ошибка Err{int(fault):02d}: {desc}")
            else:
                alarms.append(f"Активная ошибка: код Err{int(fault):02d}")

        # Проверка перегрева IGBT
        igbt_temp = data.registers.get("igbt_temperature")
        if igbt_temp and igbt_temp > 90:
            alarms.append(f"КРИТИЧНО: Перегрев IGBT {igbt_temp}°C")

        # Проверка перегрева мотора
        motor_temp = data.registers.get("motor_temperature")
        if motor_temp and motor_temp > 100:
            alarms.append(f"КРИТИЧНО: Перегрев мотора {motor_temp}°C")

        # Проверка перегрузки по току
        current = data.registers.get("output_current")
        if current and current > 100:  # Примерный порог
            alarms.append(f"КРИТИЧНО: Перегрузка по току {current}A")

        # Проверка напряжения DC шины
        dc_voltage = data.registers.get("dc_bus_voltage")
        if dc_voltage:
            if dc_voltage < 200 or dc_voltage > 450:
                alarms.append(f"КРИТИЧНО: Напряжение DC шины {dc_voltage}V")

        return alarms

    def get_warnings(self, data: DeviceData) -> List[str]:
        """Получение предупреждений VFD"""
        warnings = []

        # Предупреждение о повышенной температуре IGBT
        igbt_temp = data.registers.get("igbt_temperature")
        if igbt_temp and 70 < igbt_temp <= 90:
            warnings.append(f"Высокая температура IGBT: {igbt_temp}°C")

        # Предупреждение о повышенной температуре мотора
        motor_temp = data.registers.get("motor_temperature")
        if motor_temp and 80 < motor_temp <= 100:
            warnings.append(f"Высокая температура мотора: {motor_temp}°C")

        # Предупреждение о высоком токе
        current = data.registers.get("output_current")
        if current and 80 < current <= 100:
            warnings.append(f"Высокий ток: {current}A")

        # История ошибок
        fault_third_raw = data.registers.get("fault_third_code")
        fault_third = self._parse_fault_code(fault_third_raw)
        if fault_third is not None and fault_third != 0:
            d = self.fault_description(fault_third)
            if d:
                warnings.append(f"История: Err{fault_third:02d} — {d}")
            else:
                warnings.append(f"История: код Err{fault_third:02d}")

        return warnings
