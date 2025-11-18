#!/usr/bin/env python3
"""
Адаптер для КУБ-1063 (система вентиляции и климата)
Использует Variable System для гибкого маппинга переменных
"""

from typing import Dict, List, Any, Union
from .base import DeviceAdapter, RegisterInfo, DeviceData, ValueType
from .variable_system import (
    KUBVariableMapper, DeviceVariableManager, VariableTypeDefinition, 
    VariableReference, VariableType
)


class KUB1063Adapter(DeviceAdapter):
    """Адаптер для КУБ-1063 с Variable System"""
    
    def __init__(self):
        super().__init__()
        self._mapper = KUBVariableMapper()
        self._setup_variable_definitions()
        self._setup_variable_references()
    
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
            # Давление (знаковое)
            VariableTypeDefinition(
                id=3, name="Pressure", var_type=VariableType.FLOAT,
                scale=0.1, signed=True, unit="Па", min_val=-1000.0, max_val=1000.0,
                special_values={0x7FFF: "pending", 0x7FFE: "break", 0x7FFD: "error", 0x7FFC: "disabled"},
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
                description="Процентный выход в десятых долях"
            ),
            # Битовые поля (цифровые выходы)
            VariableTypeDefinition(
                id=7, name="DigitalOutputs", var_type=VariableType.BITFIELD,
                scale=1.0, signed=False, unit=None,
                description="Битовое поле цифровых выходов"
            ),
            # Целые числа
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
            
            # Аварии и предупреждения
            VariableReference("active_alarms", 0x00C3, 7, description="Активные аварии"),
            VariableReference("registered_alarms", 0x00C7, 7, description="Зарегистрированные аварии"),
            VariableReference("active_warnings", 0x00CB, 7, description="Активные предупреждения"),
            VariableReference("registered_warnings", 0x00CF, 7, description="Зарегистрированные предупреждения"),
            
            # Система вентиляции
            VariableReference("ventilation_target", 0x00D0, 6, description="Целевой уровень вентиляции"),
            VariableReference("ventilation_level", 0x00D1, 6, description="Фактический уровень вентиляции"),
            VariableReference("ventilation_scheme", 0x00D2, 8, description="Активная схема вентиляции"),
            VariableReference("day_counter", 0x00D3, 8, description="Счетчик дней"),
            
            # Температурная система
            VariableReference("temp_target", 0x00D4, 1, description="Целевая температура"),
            VariableReference("temp_inside", 0x00D5, 1, description="Текущая внутренняя температура"),
            VariableReference("temp_vent_activation", 0x00D6, 1, description="Температура активации вентиляции"),
        ]
        
        for var_ref in variable_references:
            self._mapper.register_variable(var_ref)
    
    def get_register_addresses(self) -> set:
        """Получение всех адресов регистров для чтения"""
        return set(self._mapper.get_all_register_addresses())
    
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
            legacy_map[var_name] = RegisterInfo(
                address=var_ref.register_address,
                name=var_name,
                value_type=value_type_map.get(type_def.var_type, ValueType.INTEGER),
                unit=type_def.unit,
                scale=type_def.scale,
                signed=type_def.signed,
                description=type_def.description,
                special_values=type_def.special_values,
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
            # Legacy DeviceData - создаем временный менеджер
            device_manager = DeviceVariableManager(data.device_id, self.device_type, self._mapper)
            # TODO: Заполнение из DeviceData - будет реализовано позже
        
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
            # Legacy DeviceData - создаем временный менеджер
            device_manager = DeviceVariableManager(data.device_id, self.device_type, self._mapper)
            # TODO: Заполнение из DeviceData - будет реализовано позже
        
        alarms = []
        
        # Проверяем активные аварии
        alarm_value = device_manager.get_variable_value("active_alarms")
        if alarm_value and alarm_value > 0:
            alarms.append(f"🚨 Активные аварии: 0x{alarm_value:04X}")
        
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
            # Legacy DeviceData - создаем временный менеджер
            device_manager = DeviceVariableManager(data.device_id, self.device_type, self._mapper)
            # TODO: Заполнение из DeviceData - будет реализовано позже
        
        warnings = []
        
        # Проверяем активные предупреждения
        warning_value = device_manager.get_variable_value("active_warnings")
        if warning_value and warning_value > 0:
            warnings.append(f"⚠️ Предупреждения: 0x{warning_value:04X}")
        
        # Проверяем отключенные датчики
        disabled_sensors = device_manager.get_variables_by_status("disabled")
        for sensor in disabled_sensors:
            warnings.append(f"🔇 {sensor}: отключен")
        
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
