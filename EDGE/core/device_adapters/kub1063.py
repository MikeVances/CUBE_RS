#!/usr/bin/env python3
"""
Адаптер для КУБ-1063 (система вентиляции и климата)
Использует Variable System для гибкого маппинга переменных
"""

from typing import Dict, List, Any, Union, Optional, TypedDict
from .base import DeviceAdapter, RegisterInfo, DeviceData, ValueType, RegisterType
from .variable_system import (
    KUBVariableMapper, DeviceVariableManager, VariableTypeDefinition, 
    VariableReference, VariableType
)


class RelayFunctionDef(TypedDict):
    key: str
    label: str
    assign_var: str
    register_address: int
    bitfield: Optional[str]
    bit: Optional[int]
    category: str
    order: int
    require_assignment: bool
    channel_type: str


def _range_definitions(
    key_template: str,
    label_template: str,
    register_start: int,
    bitfield: Optional[str],
    bit_start: int,
    count: int,
    category: str,
    index_start: int = 1,
    channel_type: str = "relay",
) -> List[RelayFunctionDef]:
    entries: List[RelayFunctionDef] = []
    for offset in range(count):
        index_value = index_start + offset
        key = key_template.format(index=index_value)
        entries.append(
            {
                "key": key,
                "label": label_template.format(index=index_value),
                "assign_var": f"{key}_relay_channel",
                "register_address": register_start + offset,
                "bitfield": bitfield,
                "bit": bit_start + offset,
                "category": category,
                "order": 0,  # переопределяется ниже
                "require_assignment": True,
                "channel_type": channel_type,
            }
        )
    return entries


def _single_definition(
    key: str,
    label: str,
    register_address: int,
    bitfield: Optional[str],
    bit: Optional[int],
    category: str,
    assign_var: Optional[str] = None,
    channel_type: str = "relay",
) -> RelayFunctionDef:
    return {
        "key": key,
        "label": label,
        "assign_var": assign_var or f"{key}_relay_channel",
        "register_address": register_address,
        "bitfield": bitfield,
        "bit": bit,
        "category": category,
        "order": 0,
        "require_assignment": True,
        "channel_type": channel_type,
    }


def _build_relay_function_definitions() -> List[RelayFunctionDef]:
    """Составляет карту назначений реле по документации (0x0100-0x013F)."""
    specs: List[RelayFunctionDef] = []
    specs.extend(
        _range_definitions(
            key_template="gnv_base_{index}",
            label_template="ГНВ{index} (база)",
            register_start=0x0100,
            bitfield="digital_outputs_1",
            bit_start=0,
            count=8,
            category="ГНВ базовая",
        )
    )
    specs.extend(
        _range_definitions(
            key_template="gnv_tunnel_{index}",
            label_template="ГНВ{index} (туннель)",
            register_start=0x0108,
            bitfield="digital_outputs_1",
            bit_start=8,
            count=8,
            category="ГНВ туннельная",
        )
    )
    specs.extend(
        _range_definitions(
            key_template="grv_base_{index}",
            label_template="ГРВ{index} (база)",
            register_start=0x0110,
            bitfield="digital_outputs_2",
            bit_start=0,
            count=2,
            category="ГРВ",
        )
    )
    specs.append(
        _single_definition(
            key="grv_tunnel",
            label="ГРВ (туннель)",
            register_address=0x0112,
            bitfield="digital_outputs_2",
            bit=2,
            category="ГРВ",
        )
    )
    specs.append(
        _single_definition(
            key="tunnel_mode_indicator",
            label="Индикация туннеля",
            register_address=0x0113,
            bitfield="digital_outputs_2",
            bit=3,
            category="Сигналы",
        )
    )
    specs.extend(
        _range_definitions(
            key_template="heater_{index}",
            label_template="Нагреватель {index}",
            register_start=0x0114,
            bitfield="digital_outputs_2",
            bit_start=4,
            count=2,
            category="Нагреватели",
        )
    )
    specs.extend(
        _range_definitions(
            key_template="heater_{index}",
            label_template="Нагреватель {index}",
            register_start=0x0122,
            bitfield="digital_outputs_2",
            bit_start=8,
            count=2,
            category="Нагреватели",
            index_start=3,
        )
    )
    specs.append(
        _single_definition(
            key="cooler",
            label="Охладитель",
            register_address=0x0116,
            bitfield="digital_outputs_2",
            bit=6,
            category="Охлаждение",
        )
    )
    specs.append(
        _single_definition(
            key="emergency",
            label="Индикация аварии",
            register_address=0x0117,
            bitfield="digital_outputs_2",
            bit=7,
            category="Сигналы",
            assign_var="emergency_relay_channel",
        )
    )
    specs[-1]["require_assignment"] = False
    specs.extend(
        _range_definitions(
            key_template="lighting_{index}",
            label_template="Освещение {index}",
            register_start=0x0130,
            bitfield="digital_outputs_2",
            bit_start=10,
            count=4,
            category="Освещение",
        )
    )
    specs.extend(
        _range_definitions(
            key_template="timer1_{index}",
            label_template="Таймер 1 · выход {index}",
            register_start=0x0134,
            bitfield="digital_outputs_2",
            bit_start=14,
            count=2,
            category="Таймер 1",
        )
    )
    specs.extend(
        _range_definitions(
            key_template="timer1_{index}",
            label_template="Таймер 1 · выход {index}",
            register_start=0x0136,
            bitfield="digital_outputs_3",
            bit_start=0,
            count=2,
            category="Таймер 1",
            index_start=3,
        )
    )
    specs.extend(
        _range_definitions(
            key_template="timer2_{index}",
            label_template="Таймер 2 · выход {index}",
            register_start=0x0138,
            bitfield="digital_outputs_3",
            bit_start=2,
            count=4,
            category="Таймер 2",
        )
    )

    analog_input_specs = [
        ("humidity_input", "Вход датчика влажности", 0x0118),
        ("pressure_input", "Вход датчика давления", 0x0119),
        ("co2_input", "Вход датчика CO2", 0x013C),
        ("nh3_input", "Вход датчика NH3", 0x013D),
    ]
    for key, label, reg in analog_input_specs:
        specs.append(
            _single_definition(
                key=key,
                label=label,
                register_address=reg,
                bitfield=None,
                bit=None,
                category="Аналоговые входы",
                assign_var=f"{key}_channel",
                channel_type="analog_input",
            )
        )

    analog_output_specs = [
        ("grv_base_signal", "Сигнал ГРВ базовой схемы", 0x011A),
        ("grv_tunnel_signal", "Сигнал ГРВ туннельной схемы", 0x011B),
        ("damper_signal", "Сигнал демпфера", 0x011C),
        ("air_intake_1_signal", "Сигнал воздухозаборника 1", 0x011D),
        ("air_intake_2_signal", "Сигнал воздухозаборника 2", 0x011E),
        ("air_intake_tunnel_signal", "Сигнал туннельного воздухозаборника", 0x011F),
        ("air_intake_3_signal", "Сигнал воздухозаборника 3", 0x0120),
        ("air_intake_4_signal", "Сигнал воздухозаборника 4", 0x0121),
        ("lighting_1_signal", "Сигнал освещения 1", 0x0124),
        ("lighting_2_signal", "Сигнал освещения 2", 0x0125),
        ("lighting_3_signal", "Сигнал освещения 3", 0x0126),
        ("lighting_4_signal", "Сигнал освещения 4", 0x0127),
        ("timer1_1_signal", "Таймер 1 · сигнал выхода 1", 0x0128),
        ("timer1_2_signal", "Таймер 1 · сигнал выхода 2", 0x0129),
        ("timer1_3_signal", "Таймер 1 · сигнал выхода 3", 0x012A),
        ("timer1_4_signal", "Таймер 1 · сигнал выхода 4", 0x012B),
        ("timer2_1_signal", "Таймер 2 · сигнал выхода 1", 0x012C),
        ("timer2_2_signal", "Таймер 2 · сигнал выхода 2", 0x012D),
        ("timer2_3_signal", "Таймер 2 · сигнал выхода 3", 0x012E),
        ("timer2_4_signal", "Таймер 2 · сигнал выхода 4", 0x012F),
    ]
    for key, label, reg in analog_output_specs:
        specs.append(
            _single_definition(
                key=key,
                label=label,
                register_address=reg,
                bitfield=None,
                bit=None,
                category="Аналоговые выходы",
                assign_var=f"{key}_channel",
                channel_type="analog_output",
            )
        )

    # Пронумеровываем для сохранения стабильного порядка в выдаче
    for idx, spec in enumerate(specs):
        spec["order"] = idx
    return specs


RELAY_FUNCTIONS = _build_relay_function_definitions()


class KUB1063Adapter(DeviceAdapter):
    """Адаптер для КУБ-1063 с Variable System"""

    DEFAULT_DASHBOARD_METRICS = [
        "temp_inside",
        "temp_target",
        "humidity",
        "pressure",
        "ventilation_level",
        "ventilation_target",
    ]
    
    def __init__(self):
        super().__init__()
        self._mapper = KUBVariableMapper()
        self._setup_variable_definitions()
        self._setup_variable_references()

    def extra_metric_metadata(self) -> Dict[str, Dict[str, Any]]:
        return {
            "active_alarms_total": {
                "label": "Активные тревоги",
                "category": "Аварии",
            },
            "registered_alarms_total": {
                "label": "История тревог",
                "category": "Аварии",
            },
            "active_warnings_total": {
                "label": "Предупреждения",
                "category": "Аварии",
            },
            "registered_warnings_total": {
                "label": "История предупреждений",
                "category": "Аварии",
            },
        }

    def get_alarm_catalog(self) -> Dict[int, Dict[str, str]]:
        return ACTIVE_ALARM_DETAILS
    
    @property
    def device_type(self) -> str:
        return "KUB-1063"
        
    @property
    def variable_mapper(self) -> KUBVariableMapper:
        return self._mapper
    
    def _setup_variable_definitions(self):
        """Настройка определений типов переменных КУБ-1063"""
        type_definitions = [
            # Температурные датчики
            VariableTypeDefinition(
                id=1, name="Temperature", var_type=VariableType.TEMPERATURE,
                scale=0.1, signed=True, unit="°C", min_val=-50.0, max_val=100.0,
                special_values={0x7FFF: "pending", 0x7FFE: "break", 0x7FFD: "error", 0x7FFC: "disabled"},
                description="Температурный датчик в десятых долях градуса"
            ),
            # Датчики влажности и других параметров
            VariableTypeDefinition(
                id=2, name="Humidity", var_type=VariableType.PERCENTAGE,
                scale=0.1, signed=False, unit="%", min_val=0.0, max_val=100.0,
                special_values={0xFFFF: "pending", 0xFFFE: "break", 0xFFFD: "error", 0xFFFC: "disabled"},
                description="Относительная влажность в десятых долях процента"
            ),
            # Давление (беззнаковое, отрицательное давление - положительное число)
            VariableTypeDefinition(
                id=3, name="Pressure", var_type=VariableType.FLOAT,
                scale=0.1, signed=False, unit="Па", min_val=0.0, max_val=10000.0,
                special_values={0xFFFF: "pending", 0xFFFE: "break", 0xFFFD: "error", 0xFFFC: "disabled"},
                description="Отрицательное давление в десятых долях Паскаля"
            ),
            # CO2 концентрация
            VariableTypeDefinition(
                id=4, name="CO2", var_type=VariableType.USHORT,
                scale=1.0, signed=False, unit="ppm", min_val=0.0, max_val=5000.0,
                special_values={0xFFFF: "pending", 0xFFFE: "break", 0xFFFD: "error", 0xFFFC: "disabled"},
                description="Концентрация CO2 в ppm"
            ),
            # NH3 концентрация  
            VariableTypeDefinition(
                id=5, name="NH3", var_type=VariableType.FLOAT,
                scale=0.1, signed=False, unit="ppm", min_val=0.0, max_val=100.0,
                special_values={0xFFFF: "pending", 0xFFFE: "break", 0xFFFD: "error", 0xFFFC: "disabled"},
                description="Концентрация NH3 в десятых долях ppm"
            ),
            # Процентные выходы (ГРВ, воздухозаборники, освещение)
            VariableTypeDefinition(
                id=6, name="Percentage", var_type=VariableType.PERCENTAGE,
                scale=0.1, signed=False, unit="%", min_val=0.0, max_val=100.0,
                special_values={0xFFFF: "pending", 0xFFFE: "break", 0xFFFD: "error", 0xFFFC: "disabled"},
                description="Процентный выход в десятых долях"
            ),
            # Битовые поля (цифровые выходы)
            VariableTypeDefinition(
                id=7, name="DigitalOutputs", var_type=VariableType.BITFIELD,
                scale=1.0, signed=False, unit=None,
                description="Битовое поле цифровых выходов"
            ),
            # Целые числа без знака
            VariableTypeDefinition(
                id=8, name="Integer", var_type=VariableType.USHORT,
                scale=1.0, signed=False, unit=None, min_val=0.0, max_val=65535.0,
                description="Целое число без знака"
            ),
            # Версия ПО
            VariableTypeDefinition(
                id=9, name="SoftwareVersion", var_type=VariableType.VERSION,
                scale=1.0, signed=False, unit=None,
                description="Версия программного обеспечения"
            ),
            # Целые числа со знаком
            VariableTypeDefinition(
                id=10, name="SignedInteger", var_type=VariableType.SHORT,
                scale=1.0, signed=True, unit=None, min_val=-32768.0, max_val=32767.0,
                special_values={0x7FFF: "disabled"},
                description="Целое число со знаком"
            ),
            # Булевые значения/флаги
            VariableTypeDefinition(
                id=11, name="Boolean", var_type=VariableType.BOOL,
                scale=1.0, signed=False, unit=None,
                description="Логический флаг (0/1)"
            ),
        ]
        
        for type_def in type_definitions:
            self._mapper.register_type(type_def)
    
    def _setup_variable_references(self):
        """Настройка ссылок на переменные в регистрах"""
        variable_references = [
            # Системная информация
            VariableReference("software_version", 0x0301, 9, description="Версия ПО"),
            VariableReference("factory_number", 0x0302, 8, description="Заводской номер"),
            VariableReference("device_number", 0x0303, 8, description="Номер устройства"),
            
            # Цифровые выходы
            VariableReference("digital_outputs_1", 0x0081, 7, description="ГНВ базовой/туннельной вентиляции"),
            VariableReference("digital_outputs_2", 0x0082, 7, description="ГРВ, нагреватели, освещение, авария"),
            VariableReference("digital_outputs_3", 0x00A2, 7, description="Таймеры"),

            # Кривая целевой температуры вентиляции
            VariableReference(
                "vent_curve_enabled",
                0x0042,
                11,
                function_code=3,
                description="Кривая целевой температуры: включена",
            ),
            VariableReference(
                "vent_curve_points_count",
                0x0043,
                8,
                function_code=3,
                description="Количество точек кривой целевой температуры",
            ),
            
            # Основные датчики
            VariableReference("pressure", 0x0083, 3, description="Отрицательное давление"),
            VariableReference("humidity", 0x0084, 2, description="Относительная влажность"),
            VariableReference("co2", 0x0085, 4, description="Концентрация CO2"),
            VariableReference("nh3", 0x0086, 5, description="Концентрация NH3"),

            # Управляющие выходы ГРВ
            VariableReference("grv_base", 0x0087, 6, description="ГРВ базовой вентиляции"),
            VariableReference("grv_tunnel", 0x0088, 6, description="ГРВ туннельной вентиляции"),
            VariableReference("damper", 0x0089, 6, description="Демпфер"),
            
            # Воздухозаборники
            VariableReference("air_intake_1", 0x008A, 6, description="Воздухозаборник 1"),
            VariableReference("air_intake_2", 0x008B, 6, description="Воздухозаборник 2"),
            VariableReference("air_intake_tunnel", 0x008C, 6, description="Туннельный воздухозаборник"),
            VariableReference("air_intake_3", 0x0092, 6, description="Воздухозаборник 3"),
            VariableReference("air_intake_4", 0x0093, 6, description="Воздухозаборник 4"),

            # Точки кривой целевой температуры вентиляции (день/целевая температура)
        ]

        base_addr = 0x0044
        for idx in range(1, 11):
            day_addr = base_addr + (idx - 1) * 2
            temp_addr = day_addr + 1
            variable_references.append(
                VariableReference(
                    f"vent_curve_day_{idx}",
                    day_addr,
                    10,
                    function_code=3,
                    description=f"Кривая целевой температуры · точка {idx} (день)",
                )
            )
            variable_references.append(
                VariableReference(
                    f"vent_curve_temp_{idx}",
                    temp_addr,
                    1,
                    function_code=3,
                    description=f"Кривая целевой температуры · точка {idx} (температура)",
                )
            )

        variable_references.extend([
            # Температурные датчики
            VariableReference("temp_inside_1", 0x008D, 1, description="Внутренняя температура 1"),
            VariableReference("temp_inside_2", 0x008E, 1, description="Внутренняя температура 2"),
            VariableReference("temp_outside", 0x008F, 1, description="Наружная температура"),
            VariableReference("temp_inside_3", 0x0090, 1, description="Внутренняя температура 3"),
            VariableReference("temp_inside_4", 0x0091, 1, description="Внутренняя температура 4"),
            
            # Освещение
            VariableReference("lighting_1", 0x0094, 6, description="Управление освещением 1"),
            VariableReference("lighting_2", 0x0095, 6, description="Управление освещением 2"),
            VariableReference("lighting_3", 0x0096, 6, description="Управление освещением 3"),
            VariableReference("lighting_4", 0x0097, 6, description="Управление освещением 4"),
            
            # Таймеры
            VariableReference("timer_1_output_1", 0x0098, 6, description="Таймер 1, выход 1"),
            VariableReference("timer_1_output_2", 0x0099, 6, description="Таймер 1, выход 2"),
            VariableReference("timer_1_output_3", 0x009A, 6, description="Таймер 1, выход 3"),
            VariableReference("timer_1_output_4", 0x009B, 6, description="Таймер 1, выход 4"),
            VariableReference("timer_2_output_1", 0x009C, 6, description="Таймер 2, выход 1"),
            VariableReference("timer_2_output_2", 0x009D, 6, description="Таймер 2, выход 2"),
            VariableReference("timer_2_output_3", 0x009E, 6, description="Таймер 2, выход 3"),
            VariableReference("timer_2_output_4", 0x009F, 6, description="Таймер 2, выход 4"),
            
            # Аварии и предупреждения (по 4 регистра на каждую категорию)
            VariableReference("active_alarms_0", 0x00C0, 7, description="Активные аварии (часть 1)"),
            VariableReference("active_alarms_1", 0x00C1, 7, description="Активные аварии (часть 2)"),
            VariableReference("active_alarms_2", 0x00C2, 7, description="Активные аварии (часть 3)"),
            VariableReference("active_alarms_3", 0x00C3, 7, description="Активные аварии (часть 4)"),

            VariableReference("registered_alarms_0", 0x00C4, 7, description="Зарегистрированные аварии (часть 1)"),
            VariableReference("registered_alarms_1", 0x00C5, 7, description="Зарегистрированные аварии (часть 2)"),
            VariableReference("registered_alarms_2", 0x00C6, 7, description="Зарегистрированные аварии (часть 3)"),
            VariableReference("registered_alarms_3", 0x00C7, 7, description="Зарегистрированные аварии (часть 4)"),

            VariableReference("active_warnings_0", 0x00C8, 7, description="Активные предупреждения (часть 1)"),
            VariableReference("active_warnings_1", 0x00C9, 7, description="Активные предупреждения (часть 2)"),
            VariableReference("active_warnings_2", 0x00CA, 7, description="Активные предупреждения (часть 3)"),
            VariableReference("active_warnings_3", 0x00CB, 7, description="Активные предупреждения (часть 4)"),

            VariableReference("registered_warnings_0", 0x00CC, 7, description="Зарегистрированные предупреждения (часть 1)"),
            VariableReference("registered_warnings_1", 0x00CD, 7, description="Зарегистрированные предупреждения (часть 2)"),
            VariableReference("registered_warnings_2", 0x00CE, 7, description="Зарегистрированные предупреждения (часть 3)"),
            VariableReference("registered_warnings_3", 0x00CF, 7, description="Зарегистрированные предупреждения (часть 4)"),
            
            # Система вентиляции
            VariableReference("ventilation_target", 0x00D0, 6, description="Целевой уровень вентиляции"),
            VariableReference("ventilation_level", 0x00D1, 6, description="Фактический уровень вентиляции"),
            VariableReference("ventilation_scheme", 0x00D2, 8, description="Активная схема вентиляции"),
            VariableReference("day_counter", 0x00D3, 10, description="Счетчик дней"),  # Знаковое целое
            
            # Температурная система
            VariableReference("temp_target", 0x00D4, 1, description="Целевая температура"),
            VariableReference("temp_inside", 0x00D5, 1, description="Текущая внутренняя температура"),
            VariableReference("temp_vent_activation", 0x00D6, 1, description="Температура активации вентиляции"),
        ])

        for relay in RELAY_FUNCTIONS:
            variable_references.append(
                VariableReference(
                    relay["assign_var"],
                    relay["register_address"],
                    10,
                    function_code=3,
                    description=f"Номер реле для {relay['label']}",
                )
            )
        
        for var_ref in variable_references:
            self._mapper.register_variable(var_ref)
    
    def get_register_addresses(self) -> set:
        """Получение всех адресов регистров для чтения"""
        return set(self._mapper.get_all_register_addresses())

    def parse_device_data(self, device_id: int, raw_registers: Dict[int, int]) -> DeviceData:
        data = super().parse_device_data(device_id, raw_registers)
        self._inject_relay_assignments(data)
        self._inject_emergency_relay_state(data)
        self._aggregate_alarm_counters(data)
        self._inject_ventilation_curve(data)
        return data

    def _inject_relay_assignments(self, data: DeviceData) -> None:
        registers = data.registers
        assignments: List[Dict[str, Any]] = []
        for info in RELAY_FUNCTIONS:
            raw_channel = registers.get(info["assign_var"])
            channel = self._safe_int(raw_channel)
            bitfield_name = info.get("bitfield")
            bit_index = info.get("bit")
            state = None
            if bitfield_name is not None and bit_index is not None:
                state = self._read_function_state(bitfield_name, bit_index, registers)
            if channel is None and state is None:
                continue
            require_assignment = info.get("require_assignment", True)
            if require_assignment and channel is None:
                continue

            channel_type = info.get("channel_type", "relay")
            channel_label = self._format_channel_label(channel, channel_type)
            state_label, state_variant = self._format_relay_state(state, channel_type, channel)
            register_hex = f"0x{info['register_address']:04X}" if info.get("register_address") else None
            channel_display = channel_label or "Нет назначения"

            entry: Dict[str, Any] = {
                "key": info["key"],
                "label": info["label"],
                "category": info["category"],
                "channel": channel,
                "channel_label": channel_label,
                "channel_display": channel_display,
                "state": state,
                "state_label": state_label,
                "state_variant": state_variant,
                "bitfield": info["bitfield"],
                "bit": info["bit"],
                "register": info["register_address"],
                "register_hex": register_hex,
                "order": info["order"],
                "channel_type": channel_type,
            }
            assignments.append(entry)
        if assignments:
            registers["relay_assignments"] = sorted(assignments, key=lambda entry: entry.get("order", 0))

    def _aggregate_alarm_counters(self, data: DeviceData) -> None:
        """Суммирует битовые блоки аварий/предупреждений для UX."""

        registers = data.registers

        def _collect(prefix: str, parts: int = 4) -> list[int]:
            values: list[int] = []
            for idx in range(parts):
                key = f"{prefix}_{idx}"
                try:
                    values.append(int(registers.get(key) or 0))
                except Exception:
                    values.append(0)
            return values

        def _bit_count(values: list[int]) -> int:
            return sum(int(value).bit_count() for value in values)

        registers["active_alarms_total"] = _bit_count(_collect("active_alarms"))
        registers["registered_alarms_total"] = _bit_count(_collect("registered_alarms"))
        registers["active_warnings_total"] = _bit_count(_collect("active_warnings"))
        registers["registered_warnings_total"] = _bit_count(_collect("registered_warnings"))
        registers["active_alarms_list"] = self._decode_alarm_bits(_collect("active_alarms"))
        registers["active_warnings_list"] = self._decode_alarm_bits(
            _collect("active_warnings"), is_warning=True
        )

    def _inject_ventilation_curve(self, data: DeviceData) -> None:
        """Формирует структуру кривой целевой температуры вентиляции."""

        registers = data.registers
        raw_registers = getattr(data, "raw_registers", {}) or {}

        def _raw_or_parsed(name: str) -> Any:
            return raw_registers.get(name, registers.get(name))

        enabled_raw_value = _raw_or_parsed("vent_curve_enabled")
        enabled_value = self._safe_int(enabled_raw_value)
        enabled: Optional[bool]
        if enabled_value in (0, 1):
            enabled = bool(enabled_value)
        else:
            enabled = None

        points_count_register = _raw_or_parsed("vent_curve_points_count")
        points_count_raw = self._safe_int(points_count_register)
        points_count: Optional[int]
        if points_count_raw is not None and 0 <= points_count_raw <= 10:
            points_count = points_count_raw
        else:
            points_count = None

        points: List[Dict[str, Any]] = []
        for idx in range(1, 11):
            day_raw = _raw_or_parsed(f"vent_curve_day_{idx}")
            temp_raw = registers.get(f"vent_curve_temp_{idx}")
            if day_raw is None or temp_raw is None:
                continue
            day = self._safe_int(day_raw, allow_negative=True)
            temp = temp_raw
            if day is None or not (-99 <= day <= 999):
                continue
            points.append({"point": idx, "day": day, "temperature": temp})

        if enabled is None and points_count is None and not points:
            return

        resolved_count = points_count if points_count is not None else (len(points) if points else None)

        state_label: Optional[str]
        if enabled is True:
            state_label = "Кривая включена"
        elif enabled is False:
            state_label = "Кривая отключена"
        else:
            state_label = None

        registers["ventilation_curve"] = {
            "enabled": enabled,
            "enabled_raw": self._safe_int(enabled_raw_value),
            "points_count": resolved_count,
            "points_count_raw": points_count_raw,
            "points": points,
            "state_label": state_label,
        }

        # Обновляем оригинальные регистры, чтобы потребители, читающие старые ключи,
        # получали нормализованные значения без изменений на фронте.
        registers["vent_curve_enabled"] = state_label if state_label is not None else enabled
        registers["vent_curve_enabled_raw"] = self._safe_int(enabled_raw_value)
        registers["vent_curve_points_count"] = resolved_count
        registers["vent_curve_points_count_raw"] = points_count_raw
        registers["vent_curve_state_label"] = state_label

    def _inject_emergency_relay_state(self, data: DeviceData) -> None:
        """Определяет состояние аварийного реле и добавляет метаданные."""

        registers = data.registers
        relay_assignments = registers.get("relay_assignments")
        emergency_assignment: Optional[Dict[str, Any]] = None
        if isinstance(relay_assignments, list):
            for entry in relay_assignments:
                if entry.get("key") == "emergency":
                    emergency_assignment = entry
                    break

        channel: Optional[int] = None
        channel_label: Optional[str] = None
        assignment_state: Optional[bool] = None
        if isinstance(emergency_assignment, dict):
            channel = self._safe_int(emergency_assignment.get("channel"))
            channel_label = emergency_assignment.get("channel_label")
            state_raw = emergency_assignment.get("state")
            if isinstance(state_raw, bool):
                assignment_state = state_raw
            if channel_label is None:
                channel_label = self._format_channel_label(channel)

        source: Optional[str] = None
        state = assignment_state

        if state is None and channel is not None:
            state = self._read_emergency_channel_state(channel, registers)
            if state is not None:
                source = "channel_bitfield"

        if state is None:
            state = self._read_function_state("digital_outputs_2", 7, registers)
            if state is not None:
                source = "register_0x0117"

        if state is not None and source is None:
            source = "relay_assignment"

        if state is True:
            state_label = "Аварийное реле: ВКЛ"
        elif state is False:
            state_label = "Аварийное реле: ВЫКЛ"
        else:
            state_label = "Аварийное реле: —"

        registers["emergency_relay"] = {
            "state": state,
            "state_label": state_label,
            "channel": channel,
            "channel_label": channel_label,
            "source": source,
        }
        registers["emergency_relay_state"] = state
        registers["emergency_relay_state_label"] = state_label
        registers["supports_alarm_reset"] = True

    def _read_emergency_channel_state(
        self, channel: int, registers: Dict[str, Any]
    ) -> Optional[bool]:
        if channel < 0:
            return None
        if channel < 8:
            state = self._read_function_state("digital_outputs_2", channel, registers)
            if state is None:
                state = self._read_function_state("digital_outputs_1", channel, registers)
            return state
        if channel < 16:
            return self._read_function_state("digital_outputs_3", channel - 8, registers)
        return self._read_function_state("digital_outputs_3", channel - 16, registers)

    def _decode_alarm_bits(
        self, parts: list[int], *, is_warning: bool = False
    ) -> list[dict[str, Any]]:
        catalog = ACTIVE_ALARM_DETAILS if not is_warning else ACTIVE_WARNING_DETAILS
        messages: list[dict[str, Any]] = []
        for idx, value in enumerate(parts):
            mask = value or 0
            for bit in range(16):
                if mask & (1 << bit):
                    alarm_id = idx * 16 + bit
                    details = catalog.get(alarm_id)
                    if details is None:
                        if is_warning:
                            continue
                        label = f"Авария {alarm_id}"
                        severity = "alarm"
                        category = None
                    else:
                        label = details.get("label") or details.get("title") or f"Авария {alarm_id}"
                        severity = details.get("severity") or ("warning" if is_warning else "alarm")
                        category = details.get("category")
                    messages.append(
                        {
                            "id": alarm_id,
                            "label": label,
                            "severity": severity,
                            "category": category,
                        }
                    )
        return messages

    def _read_function_state(self, bitfield_name: str, bit: int, registers: Dict[str, Any]) -> Optional[bool]:
        value = registers.get(bitfield_name)
        if value is None:
            return None
        try:
            mask = int(value)
        except (TypeError, ValueError):
            return None
        return bool(mask & (1 << bit))

    @staticmethod
    def _safe_int(value: Any, allow_negative: bool = False) -> Optional[int]:
        try:
            result = int(value)
        except (TypeError, ValueError):
            return None
        if not allow_negative and result < 0:
            return None
        return result

    @staticmethod
    def _format_channel_label(channel: Optional[int], channel_type: str = "relay") -> Optional[str]:
        if channel is None:
            return None
        if channel_type == "analog_input":
            return f"AI{channel + 1}"
        if channel_type == "analog_output":
            return f"AO{channel + 1}"
        return f"K{channel + 1}"

    @staticmethod
    def _format_relay_state(
        state: Optional[bool], channel_type: str, channel: Optional[int]
    ) -> tuple[str, str]:
        if state is True:
            return "ВКЛ", "on"
        if state is False:
            return "ВЫКЛ", "off"
        if channel_type.startswith("analog") and channel is not None:
            return "Назначено", "assigned"
        return "Н/Д", "unknown"

    @property
    def register_map(self) -> Dict[str, RegisterInfo]:
        """Карта регистров (legacy compatibility)"""
        # Создаем legacy карту регистров из Variable System
        legacy_map = {}
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
            type_def = self._mapper.type_definitions[var_ref.type_id]
            reg_type = RegisterType.INPUT if getattr(var_ref, "function_code", 4) == 4 else RegisterType.HOLDING

            legacy_map[var_name] = RegisterInfo(
                address=var_ref.register_address,
                name=var_name,
                value_type=value_type_map.get(type_def.var_type, ValueType.INTEGER),
                unit=type_def.unit,
                scale=type_def.scale,
                signed=type_def.signed,
                description=type_def.description,
                special_values=type_def.special_values,
                register_type=reg_type,
            )

        return legacy_map
    
    def parse_register_value(self, register_name: str, raw_value: int) -> tuple[Any, str]:
        """Парсинг сырого значения регистра (legacy compatibility)"""
        # Используем Variable System для парсинга
        if register_name not in self._mapper.variable_references:
            return raw_value, "error"
        
        var_ref = self._mapper.variable_references[register_name]
        type_def = self._mapper.type_definitions[var_ref.type_id]
        
        return self._mapper.parse_raw_value(raw_value, type_def)
    
    def create_device_manager(self, device_id: int) -> DeviceVariableManager:
        """Создание менеджера переменных для конкретного устройства"""
        return DeviceVariableManager(device_id, self.device_type, self._mapper)
    
    def format_for_display(self, data: Union[DeviceVariableManager, DeviceData]) -> str:
        """Форматирование данных КУБ-1063 для отображения в боте"""
        # Поддержка двух форматов данных
        if isinstance(data, DeviceVariableManager):
            device_manager = data
        else:
            device_manager = DeviceVariableManager(data.device_id, self.device_type, self._mapper)
            register_data: Dict[int, int] = {}
            raw = data.raw_registers or {}
            for name, value in raw.items():
                var_ref = self._mapper.get_variable_by_name(name)
                if var_ref:
                    register_data[var_ref.register_address] = value
            if register_data:
                device_manager.update_from_registers(register_data)
        
        lines = []
        lines.append("🔧 <b>КУБ-1063 СТАТУС:</b>")
        
        # Температурные датчики
        lines.append("\n🌡️ <b>ТЕМПЕРАТУРА:</b>")
        temp_sensors = [
            ("temp_inside_1", "Внутри 1"),
            ("temp_inside_2", "Внутри 2"), 
            ("temp_inside_3", "Внутри 3"),
            ("temp_inside_4", "Внутри 4"),
            ("temp_outside", "Снаружи")
        ]
        
        for var_name, label in temp_sensors:
            value = device_manager.get_variable_value(var_name)
            status = device_manager.get_variable_status(var_name)
            if value is not None:
                formatted = self._format_sensor_value(value, "°C", status, True)
                lines.append(f"  • {label}: {formatted}")
        
        # Другие датчики
        other_sensors = [
            ("pressure", "Давление", "Па"),
            ("humidity", "Влажность", "%"),
            ("co2", "CO2", "ppm"),
            ("nh3", "NH3", "ppm")
        ]
        
        for var_name, label, unit in other_sensors:
            value = device_manager.get_variable_value(var_name)
            status = device_manager.get_variable_status(var_name)
            if value is not None:
                formatted = self._format_sensor_value(value, unit, status, var_name == "pressure")
                lines.append(f"  • {label}: {formatted}")
        
        # Вентиляция
        lines.append("\n💨 <b>ВЕНТИЛЯЦИЯ:</b>")
        level = device_manager.get_variable_value("ventilation_level")
        if level is not None:
            lines.append(f"  • Уровень: <code>{level:.1f}%</code>")
        
        scheme = device_manager.get_variable_value("ventilation_scheme")
        if scheme is not None:
            scheme_name = "Базовая" if scheme == 0 else "Туннельная" if scheme == 1 else f"Схема {scheme}"
            lines.append(f"  • Режим: <code>{scheme_name}</code>")
        
        # Воздухозаборники
        lines.append("\n🌪️ <b>ВОЗДУХОЗАБОРНИКИ:</b>")
        air_intakes = [
            ("air_intake_1", "Приток 1"),
            ("air_intake_2", "Приток 2"),
            ("air_intake_tunnel", "Туннель")
        ]
        
        for var_name, label in air_intakes:
            value = device_manager.get_variable_value(var_name)
            if value is not None:
                lines.append(f"  • {label}: <code>{value:.1f}%</code>")
        
        return "\n".join(lines)
    
    def get_critical_alarms(self, data: Union[DeviceVariableManager, DeviceData]) -> List[str]:
        """Критичные аварии КУБ-1063"""
        # Поддержка двух форматов данных
        if isinstance(data, DeviceVariableManager):
            device_manager = data
        else:
            device_manager = DeviceVariableManager(data.device_id, self.device_type, self._mapper)
            register_data: Dict[int, int] = {}
            raw = data.raw_registers or {}
            for name, value in raw.items():
                var_ref = self._mapper.get_variable_by_name(name)
                if var_ref:
                    register_data[var_ref.register_address] = value
            if register_data:
                device_manager.update_from_registers(register_data)
        
        alarms = []

        # Проверяем активные аварии (4 регистра)
        alarm_hex_values = []
        for i in range(4):
            alarm_val = device_manager.get_variable_value(f"active_alarms_{i}")
            if not alarm_val:
                continue
            if alarm_val > 0:
                for bit in range(16):
                    if alarm_val & (1 << bit):
                        bit_index = i * 16 + bit
                        description = ACTIVE_ALARM_DESCRIPTIONS.get(bit_index)
                        if description:
                            alarms.append(f"🚨 {description}")
                        else:
                            alarm_hex_values.append(f"бит {bit_index}")
        if alarm_hex_values and not alarms:
            alarms.append(
                "🚨 Активные аварии: " + ", ".join(alarm_hex_values)
            )
        
        # Проверяем статусы критичных сенсоров
        critical_sensors = ["temp_inside_1", "temp_inside_2", "pressure"]
        for sensor in critical_sensors:
            status = device_manager.get_variable_status(sensor)
            if status in ["break", "error"]:
                alarms.append(f"❌ {sensor}: {status}")
        
        return alarms
    
    def get_warnings(self, data: Union[DeviceVariableManager, DeviceData]) -> List[str]:
        """Предупреждения КУБ-1063"""
        # Поддержка двух форматов данных
        if isinstance(data, DeviceVariableManager):
            device_manager = data
        else:
            device_manager = DeviceVariableManager(data.device_id, self.device_type, self._mapper)
            register_data: Dict[int, int] = {}
            raw = data.raw_registers or {}
            for name, value in raw.items():
                var_ref = self._mapper.get_variable_by_name(name)
                if var_ref:
                    register_data[var_ref.register_address] = value
            if register_data:
                device_manager.update_from_registers(register_data)
        
        warnings = []

        # Проверяем активные предупреждения (4 регистра)
        warning_values = []
        for i in range(4):
            warning_val = device_manager.get_variable_value(f"active_warnings_{i}")
            if warning_val and warning_val > 0:
                warning_values.append(f"0x{warning_val:04X}")

        if warning_values:
            warnings.append(f"⚠️ Предупреждения: {', '.join(warning_values)}")
        
        # Не включаем отключенные датчики в список предупреждений — они отображаются
        # через статус переменных и не должны создавать шумных сообщений.
        
        return warnings
    
    # Новые методы для Variable System (не legacy)
    def format_device_manager_display(self, device_manager: DeviceVariableManager) -> str:
        """Форматирование DeviceVariableManager для отображения (новая архитектура)"""
        return self.format_for_display(device_manager)
    
    def get_device_manager_alarms(self, device_manager: DeviceVariableManager) -> List[str]:
        """Получение аварий из DeviceVariableManager (новая архитектура)"""
        return self.get_critical_alarms(device_manager)
    
    def get_device_manager_warnings(self, device_manager: DeviceVariableManager) -> List[str]:
        """Получение предупреждений из DeviceVariableManager (новая архитектура)"""
        return self.get_warnings(device_manager)
    
    def _format_sensor_value(self, value: Any, unit: str, status: str, is_temperature: bool = False) -> str:
        """Форматирование значения датчика с эмодзи статуса"""
        if status != "ok":
            status_map = {
                "pending": "⏳ ожидание измерения",
                "break": "❌ обрыв датчика",
                "error": "⚠️ ошибка измерения", 
                "disabled": "🔇 отключен в настройках"
            }
            return status_map.get(status, f"❓ {status}")
        
        if is_temperature:
            return f"<code>{value:.1f}{unit}</code>"
        else:
            return f"<code>{value:.1f}{unit}</code>"
ACTIVE_ALARM_DETAILS = {
    26: {
        "title": "Аварийный режим воздухозаборника 3",
        "recommendation": "Проверьте назначение выхода и привод воздухозаборника 3. После устранения верните управление в автоматический режим.",
    },
    27: {
        "title": "Аварийный режим воздухозаборника 4",
        "recommendation": "Проверьте подключение воздухозаборника 4 и его уставки.",
    },
    28: {
        "title": "Низкое напряжение питания",
        "recommendation": "Проверьте питание контроллера (220 В/24 В), состояние ИБП и клемм.",
    },
    30: {
        "title": "Не установлены дата и время",
        "recommendation": "Установите актуальные дату и время на панели КУБ-1063.",
    },
    33: {
        "title": "Перегрузка системы",
        "recommendation": "Перезапустите контроллер и проверьте число фоновых задач/таймеров.",
    },
    34: {
        "title": "Требуется первичная настройка",
        "recommendation": "Запустите мастер начальной настройки и задайте базовые параметры.",
    },
    35: {
        "title": "Превышена максимальная внутренняя температура",
        "recommendation": "Увеличьте вентиляцию/охлаждение, проверьте уставки температуры.",
    },
    36: {
        "title": "Низкая внутренняя температура",
        "recommendation": "Проверьте нагреватели, реле и целевые значения температуры.",
    },
    37: {
        "title": "Высокая влажность",
        "recommendation": "Проверьте работу осушения/вентиляции и корректность датчика влажности.",
    },
    38: {
        "title": "Высокое отрицательное давление",
        "recommendation": "Проверьте заслонки, каналы и датчик давления.",
    },
    39: {
        "title": "Низкое отрицательное давление",
        "recommendation": "Проверьте вентиляторы и точность датчика давления.",
    },
    40: {
        "title": "Обрыв датчика влажности",
        "recommendation": "Проверить проводку датчика влажности и заменить при необходимости.",
    },
    41: {
        "title": "Обрыв датчика отрицательного давления",
        "recommendation": "Проверить соединение датчика давления и калибровку.",
    },
    42: {
        "title": "Обрыв датчика внутренней температуры 1",
        "recommendation": "Проверить датчик T1, кабель и клеммник.",
    },
    43: {
        "title": "Обрыв датчика внутренней температуры 2",
        "recommendation": "Проверить датчик T2 и проводку.",
    },
    44: {
        "title": "Обрыв датчика наружной температуры",
        "recommendation": "Осмотреть наружный датчик, восстановить проводку/заменить.",
    },
    45: {
        "title": "Аварийный режим вентиляции по температуре",
        "recommendation": "Проверить датчики температуры и параметры вентиляции, вернуть автоматический режим.",
    },
    46: {
        "title": "Аварийный режим контроля влажности",
        "recommendation": "Проверить датчик влажности и уставки управления.",
    },
    47: {
        "title": "Аварийный режим управления охладителем",
        "recommendation": "Проверить охладитель, реле и конфигурацию выхода.",
    },
    51: {
        "title": "Аварийный режим воздухозаборника 1",
        "recommendation": "Проверить привод воздухозаборника 1 и привязанный выход.",
    },
    52: {
        "title": "Аварийный режим воздухозаборника 2",
        "recommendation": "Проверить привод воздухозаборника 2.",
    },
    53: {
        "title": "Аварийный режим нагревателя 1",
        "recommendation": "Проверить контактор/реле нагревателя 1 и цепь питания.",
    },
    54: {
        "title": "Аварийный режим нагревателя 2",
        "recommendation": "Проверить нагреватель 2 и его цепь управления.",
    },
    55: {
        "title": "Аварийный режим демпфера",
        "recommendation": "Проверить привод демпфера и сигнал управления.",
    },
    56: {
        "title": "Неправильные уставки",
        "recommendation": "Проверьте заданные значения температуры, влажности и давления, скорректируйте их по технологической карте.",
    },
    57: {
        "title": "Высокая внутренняя температура",
        "recommendation": "Проверьте вентиляцию/охлаждение, уменьшите уставку или увеличьте скорость вентиляторов.",
    },
    58: {
        "title": "Аварийный режим туннельного воздухозаборника",
        "recommendation": "Проверить привод туннельного воздухозаборника и настройки канала.",
    },
    59: {
        "title": "Обрыв датчика температуры",
        "recommendation": "Проверить универсальный температурный датчик и кабель.",
    },
    60: {
        "title": "Обрыв датчика внутренней температуры 3",
        "recommendation": "Проверить датчик T3 и соединения.",
    },
    61: {
        "title": "Обрыв датчика внутренней температуры 4",
        "recommendation": "Проверить датчик T4 и соединения.",
    },
    62: {
        "title": "Аварийный режим нагревателя 3",
        "recommendation": "Проверить цепь нагревателя 3.",
    },
    63: {
        "title": "Аварийный режим нагревателя 4",
        "recommendation": "Проверить цепь нагревателя 4.",
    },
}

ACTIVE_ALARM_DESCRIPTIONS = {bit: data["title"] for bit, data in ACTIVE_ALARM_DETAILS.items()}
ACTIVE_WARNING_DETAILS: Dict[int, Dict[str, Any]] = {}
