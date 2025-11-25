#!/usr/bin/env python3
"""
Адаптер для КУБ-1112 (блок управления обогревателя)
Использует Variable System для гибкого маппинга переменных
"""

from typing import Dict, List, Any, Union, Optional
from .base import DeviceAdapter, RegisterInfo, DeviceData, ValueType, RegisterType
from .variable_system import (
    KUBVariableMapper, DeviceVariableManager, VariableTypeDefinition, 
    VariableReference, VariableType
)


ALARM_BIT_DESCRIPTIONS: Dict[int, str] = {
    0: "Резерв",
    1: "Не обнаружено пламя при запуске",
    2: "Низкое давление / обрыв датчика",
    3: "Пламя погасло",
    4: "Обдув при выключенном вентиляторе",
    5: "Отсутствует обдув камеры",
    6: "Обрыв или неисправность датчика температуры",
    7: "Пламя не гаснет",
    8: "Неправильный сигнал пламени",
    9: "Длительный сигнал сброса аварии",
    10: "Частые попытки сброса аварий",
    11: "Сигнал STL",
    12: "Сигнал STM",
    13: "Отключился обдув камеры",
    14: "Короткий промежуток между пусками",
    15: "Ошибка при перепрошивке",
    16: "Подача газа блокирована резервом",
    20: "Ошибка инициализации системы",
    21: "Ошибка доступа к устройству",
    22: "Включен режим тестирования",
    28: "Низкое напряжение питания",
    33: "Перегрузка системы",
}

ALARM_REGISTER_OFFSETS = {
    "registered_alarms_0": 0,
    "registered_alarms_1": 16,
    "registered_alarms_2": 32,
    "registered_alarms_3": 48,
}

DISCRETE_INPUTS_MAP = [
    ("Флюгер", 2, "Обдув есть", "Обдува нет"),
    ("Давление газа", 3, "Нормальное", "Низкое"),
    ("Вентиляция", 4, "Запуск", "Останов"),
    ("Нагрев", 5, "Запуск", "Останов"),
]


class KUB1112Adapter(DeviceAdapter):
    """Адаптер для КУБ-1112 с Variable System"""

    def __init__(self):
        super().__init__()
        self._mapper = KUBVariableMapper()
        self._setup_variable_definitions()
        self._setup_variable_references()
        self._device_managers: Dict[int, DeviceVariableManager] = {}

    DEFAULT_DASHBOARD_METRICS = [
        "temperature",
        "flame_level",
        "flame_present",
        "operation_mode",
        "min_work_time",
        "purge_duration",
    ]
    
    @property
    def device_type(self) -> str:
        return "KUB-1112"
        
    @property
    def variable_mapper(self) -> KUBVariableMapper:
        return self._mapper
    
    def _setup_variable_definitions(self):
        """Настройка определений типов переменных КУБ-1112"""
        type_definitions = [
            # Уровень пламени (процент с масштабом 0.01)
            VariableTypeDefinition(
                id=1, name="FlameLevel", var_type=VariableType.PERCENTAGE,
                scale=0.01, signed=True, unit="%", min_val=0.0, max_val=100.0,
                special_values={0xFFFF: "pending", 0xFFFE: "break", 0xFFFD: "error"},
                description="Уровень пламени в сотых долях процента"
            ),
            # Булевы значения (флаги)
            VariableTypeDefinition(
                id=2, name="Boolean", var_type=VariableType.BOOL,
                scale=1.0, signed=False, unit=None,
                description="Булево значение (0/1)"
            ),
            # Временные параметры (секунды с масштабом 0.1)
            VariableTypeDefinition(
                id=3, name="TimeSeconds", var_type=VariableType.FLOAT,
                scale=0.1, signed=False, unit="с", min_val=0.0, max_val=6553.5,
                special_values={0xFFFF: "pending"},
                description="Время в десятых долях секунды"
            ),
            # Температура (как в КУБ-1063)
            VariableTypeDefinition(
                id=4, name="Temperature", var_type=VariableType.TEMPERATURE,
                scale=0.1, signed=True, unit="°C", min_val=-50.0, max_val=100.0,
                special_values={0x8000: "error", 0x7FFF: "pending", 0x7FFE: "break", 0x7FFD: "error"},
                description="Температурный датчик в десятых долях градуса"
            ),
            # Сопротивление датчика
            VariableTypeDefinition(
                id=5, name="Resistance", var_type=VariableType.UINT,
                scale=1.0, signed=False, unit="Ом", min_val=0.0, max_val=65535.0,
                description="Сопротивление в Омах"
            ),
            # Битовые поля (состояние реле, входы)
            VariableTypeDefinition(
                id=6, name="BitField", var_type=VariableType.BITFIELD,
                scale=1.0, signed=False, unit=None,
                description="Битовое поле состояний"
            ),
            # Режим работы (целое число)
            VariableTypeDefinition(
                id=7, name="OperationMode", var_type=VariableType.USHORT,
                scale=1.0, signed=False, unit=None, min_val=0.0, max_val=10.0,
                description="Режим работы системы"
            ),
            # Аварийные регистры (битовые поля)
            VariableTypeDefinition(
                id=8, name="AlarmRegister", var_type=VariableType.BITFIELD,
                scale=1.0, signed=False, unit=None,
                description="Регистр зарегистрированных аварий"
            ),
            # Modbus настройки
            VariableTypeDefinition(
                id=9, name="ModbusParameter", var_type=VariableType.USHORT,
                scale=1.0, signed=False, unit=None, min_val=1.0, max_val=65535.0,
                description="Параметр Modbus протокола"
            ),
            # Версия ПО
            VariableTypeDefinition(
                id=10, name="SoftwareVersion", var_type=VariableType.VERSION,
                scale=1.0, signed=False, unit=None,
                description="Версия программного обеспечения"
            ),
        ]
        
        for type_def in type_definitions:
            self._mapper.register_type(type_def)
    
    def _setup_variable_references(self):
        """Настройка ссылок на переменные в регистрах"""
        variable_references = [
            # Системная информация
            VariableReference(
                name="software_version", register_address=0x0301, type_id=10,
                description="Версия ПО КУБ-1112"
            ),
            
            # Основные параметры пламени
            VariableReference(
                name="flame_level", register_address=0x0400, type_id=1,
                description="Уровень пламени в камере, %"
            ),
            VariableReference(
                name="flame_present", register_address=0x0401, type_id=2,
                description="Пламя обнаружено (1 — да, 0 — нет)"
            ),
            
            # Настройки времени (потенциометры)
            VariableReference(
                name="min_work_time", register_address=0x0402, type_id=3,
                description="Минимальное время непрерывной работы, с"
            ),
            VariableReference(
                name="start_delay", register_address=0x0403, type_id=3,
                description="Задержка запуска после включения, с"
            ),
            VariableReference(
                name="purge_duration", register_address=0x0404, type_id=3,
                description="Длительность продувки камеры, с"
            ),
            
            # Температурный датчик
            VariableReference(
                name="temperature", register_address=0x0405, type_id=4,
                description="Температура корпуса обогревателя, °C"
            ),
            VariableReference(
                name="temp_resistance", register_address=0x0406, type_id=5,
                description="Сопротивление термодатчика корпуса, Ом"
            ),
            
            # Состояния (битовые поля)
            VariableReference(
                name="relay_state", register_address=0x0407, type_id=6,
                description="Состояние исполнительных реле"
            ),
            VariableReference(
                name="discrete_inputs", register_address=0x0408, type_id=6,
                description="Состояние дискретных входов"
            ),
            
            # Режим работы
            VariableReference(
                name="operation_mode", register_address=0x0409, type_id=7,
                description="Активный режим работы обогревателя"
            ),
            
            # Аварийные регистры
            VariableReference(
                name="registered_alarms_0", register_address=0x0410, type_id=8,
                description="Зарегистрированные аварии (биты 0-15)"
            ),
            VariableReference(
                name="registered_alarms_1", register_address=0x0411, type_id=8,
                description="Зарегистрированные аварии (биты 16-31)"
            ),
            VariableReference(
                name="registered_alarms_2", register_address=0x0412, type_id=8,
                description="Зарегистрированные аварии (биты 32-47)"
            ),
            VariableReference(
                name="registered_alarms_3", register_address=0x0413, type_id=8,
                description="Зарегистрированные аварии (биты 48-63)"
            ),
            
            # Настройки Modbus
            VariableReference(
                name="modbus_address", register_address=0x0220, type_id=9,
                description="Адрес устройства Modbus", function_code=3
            ),
            VariableReference(
                name="modbus_baudrate", register_address=0x0221, type_id=9,
                description="Скорость передачи Modbus", function_code=3
            ),
        ]
        
        for var_ref in variable_references:
            self._mapper.register_variable(var_ref)
    
    def create_device_manager(self, device_id: int) -> DeviceVariableManager:
        """Создание менеджера переменных для устройства КУБ-1112"""
        manager = DeviceVariableManager(device_id, self.device_type, self._mapper)
        self._device_managers[device_id] = manager
        return manager

    def _get_or_create_manager(self, device_id: int) -> DeviceVariableManager:
        return self._device_managers.get(device_id) or self.create_device_manager(device_id)

    def _device_data_to_register_map(self, data: DeviceData) -> Dict[int, int]:
        register_map: Dict[int, int] = {}
        for name, raw_value in data.raw_registers.items():
            var_ref = self._mapper.get_variable_by_name(name)
            if var_ref:
                register_map[var_ref.register_address] = raw_value
        return register_map

    def _ensure_device_manager(
        self, source: Union[DeviceVariableManager, DeviceData, None]
    ) -> Optional[DeviceVariableManager]:
        if isinstance(source, DeviceVariableManager):
            return source
        if isinstance(source, DeviceData):
            manager = self._device_managers.get(source.device_id)
            if manager is None:
                manager = self.create_device_manager(source.device_id)
            register_payload = self._device_data_to_register_map(source)
            if register_payload:
                manager.update_from_registers(register_payload)
            return manager
        return None

    def get_register_addresses(self) -> List[int]:
        """Список регистров формируем из Variable System."""
        return sorted(self._mapper.get_all_register_addresses())

    def parse_device_data(self, device_id: int, raw_registers: Dict[int, int]) -> DeviceData:
        """Парсинг данных через Variable System менеджер."""
        device_manager = self._get_or_create_manager(device_id)
        device_manager.update_from_registers(raw_registers)

        registers = device_manager.get_all_values()
        statuses = device_manager.get_all_statuses()

        discrete_value = registers.get("discrete_inputs")
        discrete_status = statuses.get("discrete_inputs")
        if discrete_value is not None:
            if discrete_status == "ok":
                registers["discrete_inputs_state"] = self._format_discrete_inputs_text(int(discrete_value))
                statuses["discrete_inputs_state"] = "ok"
            else:
                registers["discrete_inputs_state"] = discrete_status or "unknown"
                statuses["discrete_inputs_state"] = discrete_status or "unknown"

        raw_named: Dict[str, int] = {}
        for name, ref in self._mapper.variable_references.items():
            if ref.register_address in raw_registers:
                raw_named[name] = raw_registers[ref.register_address]

        return DeviceData(
            device_id=device_id,
            device_type=self.device_type,
            registers=registers,
            raw_registers=raw_named,
            status=statuses,
        )

    def format_for_display(self, data: Union[DeviceVariableManager, DeviceData]) -> str:
        """Форматирование данных КУБ-1112 для отображения в Telegram"""
        device_manager = self._ensure_device_manager(data)
        if device_manager is None:
            return "Нет данных для отображения"
        lines = []
        device_id = device_manager.device_id
        
        # Заголовок
        lines.append(f"🔥 <b>КУБ-1112 (ID: {device_id})</b>")
        lines.append("=" * 30)
        
        # Состояние пламени
        lines.append("\n🔥 <b>ПЛАМЯ:</b>")
        
        flame_present = device_manager.get_variable_value("flame_present")
        if flame_present is not None:
            flame_status = device_manager.get_variable_status("flame_present")
            if flame_status == "ok":
                status_icon = "🟢" if flame_present else "🔴"
                status_text = "ЕСТЬ" if flame_present else "НЕТ"
                lines.append(f"  • Статус: {status_icon} <code>{status_text}</code>")
            else:
                lines.append(f"  • Статус: ⚠️ <code>{flame_status}</code>")
        
        flame_level = device_manager.get_variable_value("flame_level")
        if flame_level is not None:
            flame_status = device_manager.get_variable_status("flame_level")
            if flame_status == "ok":
                lines.append(f"  • Уровень: <code>{flame_level:.2f}%</code>")
            else:
                lines.append(f"  • Уровень: ⚠️ <code>{flame_status}</code>")
        
        # Температура
        lines.append("\n🌡️ <b>ТЕМПЕРАТУРА:</b>")
        temp = device_manager.get_variable_value("temperature")
        if temp is not None:
            temp_status = device_manager.get_variable_status("temperature")
            if temp_status == "ok":
                lines.append(f"  • Датчик: <code>{temp:.1f}°C</code>")
            elif temp_status == "error":
                lines.append("  • Датчик: ❌ <code>Ошибка измерения</code>")
            else:
                lines.append(f"  • Датчик: ⚠️ <code>{temp_status}</code>")
        
        temp_resistance = device_manager.get_variable_value("temp_resistance")
        if temp_resistance is not None:
            lines.append(f"  • Сопротивление: <code>{temp_resistance} Ом</code>")
        
        # Режим работы
        lines.append("\n⚙️ <b>РЕЖИМ РАБОТЫ:</b>")
        mode = device_manager.get_variable_value("operation_mode")
        if mode is not None:
            mode_status = device_manager.get_variable_status("operation_mode")
            if mode_status == "ok":
                mode_names = {
                    0: "Не выбран",
                    1: "Авто обогрев + авто вентиляция",
                    2: "Непрерывный обогрев", 
                    3: "Непрерывная вентиляция",
                    4: "Авто обогрев + непрерывная вентиляция"
                }
                mode_name = mode_names.get(mode, f"Режим {mode}")
                lines.append(f"  • Режим: <code>{mode_name}</code>")
            else:
                lines.append(f"  • Режим: ⚠️ <code>{mode_status}</code>")
        
        # Настройки времени
        lines.append("\n⏱️ <b>НАСТРОЙКИ ВРЕМЕНИ:</b>")
        time_params = [
            ("min_work_time", "Мин. время работы"),
            ("start_delay", "Задержка пуска"),
            ("purge_duration", "Продувка")
        ]
        
        for param_name, display_name in time_params:
            value = device_manager.get_variable_value(param_name)
            if value is not None:
                status = device_manager.get_variable_status(param_name)
                if status == "ok":
                    lines.append(f"  • {display_name}: <code>{value:.1f} с</code>")
                elif status == "pending":
                    lines.append(f"  • {display_name}: ⏳ <code>Загрузка...</code>")
        
        # Состояние реле
        lines.append("\n🔌 <b>РЕЛЕ:</b>")
        relay_state = device_manager.get_variable_value("relay_state")
        if relay_state is not None:
            relay_status = device_manager.get_variable_status("relay_state")
            if relay_status == "ok":
                relay_names = [
                    ("Клапан газа", 0),
                    ("Розжиг", 1),
                    ("Основной вентилятор", 2),
                    ("Доп. вентилятор", 3),
                    ("Авария", 4)
                ]
                
                for name, bit in relay_names:
                    state = "🟢 ВКЛ" if (relay_state & (1 << bit)) else "🔴 ВЫКЛ"
                    lines.append(f"  • {name}: {state}")
        
        # Дискретные входы
        lines.append("\n📥 <b>ВХОДЫ:</b>")
        inputs = device_manager.get_variable_value("discrete_inputs")
        inputs_status = device_manager.get_variable_status("discrete_inputs")
        if inputs is None or inputs_status != "ok":
            lines.append(f"  • Состояние: {inputs_status or '—'}")
        else:
            for name, bit, on_text, off_text in DISCRETE_INPUTS_MAP:
                active = bool(inputs & (1 << bit))
                icon = "🟢" if active else "🔴"
                state = on_text if active else off_text
                lines.append(f"  • {name}: {icon} <code>{state}</code>")
        
        # Версия ПО
        sw_version = device_manager.get_variable_value("software_version")
        if sw_version is not None:
            lines.append(f"\n🔧 <b>Версия ПО:</b> <code>{sw_version}</code>")
        
        return "\n".join(lines)
    
    def get_critical_alarms(
        self, data: Union[DeviceVariableManager, DeviceData]
    ) -> List[str]:
        """Критичные аварии КУБ-1112"""
        device_manager = self._ensure_device_manager(data)
        if device_manager is None:
            return []
        alarms = []
        
        # Проверяем аварийные регистры
        alarm_registers = ["registered_alarms_0", "registered_alarms_1", "registered_alarms_2", "registered_alarms_3"]
        for reg_name in alarm_registers:
            alarm_value = device_manager.get_variable_value(reg_name)
            if alarm_value is not None and alarm_value > 0:
                # Декодируем специфичные аварии
                critical_bits = self._decode_critical_alarms(reg_name, alarm_value)
                alarms.extend(critical_bits)
        
        # Проверяем отсутствие пламени в режиме обогрева
        flame_present = device_manager.get_variable_value("flame_present")
        mode = device_manager.get_variable_value("operation_mode")
        relay_state = device_manager.get_variable_value("relay_state")
        discrete_inputs = device_manager.get_variable_value("discrete_inputs")
        flame_status_ok = device_manager.get_variable_status("flame_present") == "ok"
        mode_status_ok = device_manager.get_variable_status("operation_mode") == "ok"
        relay_status_ok = device_manager.get_variable_status("relay_state") == "ok"
        di_status_ok = device_manager.get_variable_status("discrete_inputs") == "ok"
        heating_command = False
        if relay_state is not None and relay_status_ok:
            heating_command = bool(relay_state & (1 << 0))  # бит 0 — клапан газа (обогрев)
        if discrete_inputs is not None and di_status_ok:
            heating_command = heating_command or bool(discrete_inputs & (1 << 5))  # бит 5 «Нагрев: Запуск»
        if (
            flame_present is not None
            and mode is not None
            and flame_status_ok
            and mode_status_ok
        ):
            heating_mode = mode in [1, 2, 4]
            if (heating_mode and heating_command) and not flame_present:
                alarms.append("🚨 Нет пламени при включенном обогреве")
        
        # Проверяем температурный датчик
        temp_status = device_manager.get_variable_status("temperature")
        if temp_status == "error":
            alarms.append("❌ Ошибка датчика температуры")
        
        return alarms
    
    def get_warnings(
        self, data: Union[DeviceVariableManager, DeviceData]
    ) -> List[str]:
        """Предупреждения КУБ-1112"""
        device_manager = self._ensure_device_manager(data)
        if device_manager is None:
            return []
        warnings = []
        
        # Проверяем неготовые измерения
        all_variables = [
            "flame_level", "flame_present", "min_work_time", "start_delay", 
            "purge_duration", "temperature", "operation_mode"
        ]
        
        for var_name in all_variables:
            status = device_manager.get_variable_status(var_name)
            if status == "pending":
                warnings.append(f"⏳ {var_name}: измерение не готово")
            elif status in ["break", "error"] and status != "disabled":
                warnings.append(f"⚠️ {var_name}: {status}")
        
        # Проверяем низкое давление газа
        inputs = device_manager.get_variable_value("discrete_inputs")
        if (inputs is not None and 
            device_manager.get_variable_status("discrete_inputs") == "ok"):
            if not (inputs & (1 << 3)):  # Бит 3 - давление газа
                warnings.append("⚠️ Низкое давление газа")
        
        return warnings
    
    def _decode_critical_alarms(self, register_name: str, alarm_value: int) -> List[str]:
        """Декодирование критичных аварий из битового поля"""
        offset = ALARM_REGISTER_OFFSETS.get(register_name)
        if offset is None:
            return []

        alarms: List[str] = []
        for bit in range(16):
            if alarm_value & (1 << bit):
                absolute_bit = offset + bit
                description = ALARM_BIT_DESCRIPTIONS.get(absolute_bit)
                if description and not description.startswith("Резерв"):
                    alarms.append(f"🚨 {description}")

        return alarms

    # Legacy methods для совместимости
    @property
    def register_map(self) -> Dict[str, RegisterInfo]:
        """Формируем legacy карту регистров для UniversalModbusReader."""
        legacy_map: Dict[str, RegisterInfo] = {}
        value_type_map = {
            VariableType.TEMPERATURE: ValueType.TEMPERATURE,
            VariableType.PERCENTAGE: ValueType.PERCENTAGE,
            VariableType.FLOAT: ValueType.FLOAT,
            VariableType.BOOL: ValueType.BOOLEAN,
            VariableType.BITFIELD: ValueType.BITFIELD,
            VariableType.VERSION: ValueType.VERSION,
            VariableType.SHORT: ValueType.INTEGER,
            VariableType.USHORT: ValueType.INTEGER,
            VariableType.INT: ValueType.INTEGER,
            VariableType.UINT: ValueType.INTEGER,
            VariableType.BYTE: ValueType.INTEGER,
        }

        for var_name, var_ref in self._mapper.variable_references.items():
            type_def = self._mapper.type_definitions.get(var_ref.type_id)
            if not type_def:
                continue

            register_type = RegisterType.INPUT if var_ref.function_code == 4 else RegisterType.HOLDING

            legacy_map[var_name] = RegisterInfo(
                address=var_ref.register_address,
                name=var_name,
                value_type=value_type_map.get(type_def.var_type, ValueType.INTEGER),
                unit=type_def.unit,
                scale=type_def.scale,
                signed=type_def.signed,
                description=type_def.description,
                special_values=type_def.special_values,
                register_type=register_type,
            )

        legacy_map["discrete_inputs_state"] = RegisterInfo(
            address=-1,
            name="discrete_inputs_state",
            value_type=ValueType.STATUS,
            description="Состояние дискретных входов (текст)",
            register_type=RegisterType.INPUT,
        )

        return legacy_map
    
    def parse_register_value(self, register_name: str, raw_value: int) -> tuple[Any, str]:
        """Парсинг сырого значения регистра (legacy compatibility)."""
        var_ref = self._mapper.variable_references.get(register_name)
        if not var_ref:
            return raw_value, "error"

        type_def = self._mapper.type_definitions.get(var_ref.type_id)
        if not type_def:
            return raw_value, "error"

        return self._mapper.parse_raw_value(raw_value, type_def)
    
    def format_for_display_legacy(self, data: DeviceData) -> str:
        """Legacy метод - используйте format_for_display с DeviceVariableManager"""
        return "Используйте новый Variable System API"

    def _format_discrete_inputs_text(self, value: int) -> str:
        parts: List[str] = []
        for name, bit, on_text, off_text in DISCRETE_INPUTS_MAP:
            active = bool(value & (1 << bit))
            icon = "🟢" if active else "🔴"
            parts.append(f"{icon} {name}: {on_text if active else off_text}")
        return "; ".join(parts)
