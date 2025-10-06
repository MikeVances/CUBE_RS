#!/usr/bin/env python3
"""
Variable System для EDGE - вдохновлено ST_RS project
Система управления переменными устройств с поддержкой типов и автоматической конвертацией
"""

import struct
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import IntEnum
from datetime import datetime

from core.log_filter import get_secure_logger

logger = get_secure_logger(__name__)


class VariableType(IntEnum):
    """Типы переменных для КУБ устройств"""
    BOOL = 0           # Булево значение
    BYTE = 1           # 8-битное значение  
    SHORT = 2          # 16-битное знаковое
    USHORT = 3         # 16-битное беззнаковое
    INT = 4            # 32-битное знаковое
    UINT = 5           # 32-битное беззнаковое
    FLOAT = 6          # 32-битное с плавающей точкой
    TEMPERATURE = 7    # Температура (специальная обработка)
    PERCENTAGE = 8     # Процент (специальная обработка)
    BITFIELD = 9       # Битовое поле
    VERSION = 10       # Версия ПО (специальная обработка)


@dataclass
class VariableTypeDefinition:
    """Определение типа переменной"""
    id: int
    name: str
    var_type: VariableType
    scale: float = 1.0           # Масштабный коэффициент (множитель)
    signed: bool = False         # Знаковое ли значение
    unit: Optional[str] = None   # Единица измерения
    min_val: Optional[float] = None  # Минимальное значение
    max_val: Optional[float] = None  # Максимальное значение
    special_values: Optional[Dict[int, str]] = None  # {raw_value: status}
    description: Optional[str] = None


@dataclass 
class VariableReference:
    """Ссылка на переменную в регистрах устройства"""
    name: str                    # Имя переменной
    register_address: int        # Адрес регистра
    type_id: int                # ID типа переменной  
    length_bytes: int = 2       # Длина в байтах (обычно 2 для 16-бит регистров)
    function_code: int = 4      # Modbus функция (3=holding, 4=input)
    description: Optional[str] = None


@dataclass
class VariableValue:
    """Значение переменной с метаданными"""
    device_id: int
    variable_name: str
    register_address: int
    raw_value: int              # Сырое значение из регистра
    parsed_value: Any           # Обработанное значение
    status: str                 # "ok", "error", "disabled", "pending", etc
    timestamp: datetime
    unit: Optional[str] = None


class KUBVariableMapper:
    """Система маппинга переменных для КУБ устройств"""
    
    def __init__(self):
        self.type_definitions: Dict[int, VariableTypeDefinition] = {}
        self.variable_references: Dict[str, VariableReference] = {}  # name -> reference
        self.register_to_variable: Dict[int, str] = {}  # register_address -> variable_name
        
    def register_type(self, type_def: VariableTypeDefinition):
        """Регистрация типа переменной"""
        self.type_definitions[type_def.id] = type_def
        logger.debug(f"Зарегистрирован тип: {type_def.name} (ID: {type_def.id})")
        
    def register_variable(self, var_ref: VariableReference):
        """Регистрация переменной"""
        self.variable_references[var_ref.name] = var_ref
        self.register_to_variable[var_ref.register_address] = var_ref.name
        logger.debug(f"Зарегистрирована переменная: {var_ref.name} -> 0x{var_ref.register_address:04X}")
    
    def get_variable_by_register(self, register_address: int) -> Optional[VariableReference]:
        """Получение переменной по адресу регистра"""
        var_name = self.register_to_variable.get(register_address)
        return self.variable_references.get(var_name) if var_name else None
    
    def get_variable_by_name(self, name: str) -> Optional[VariableReference]:
        """Получение переменной по имени"""
        return self.variable_references.get(name)
    
    def get_type_definition(self, type_id: int) -> Optional[VariableTypeDefinition]:
        """Получение определения типа"""
        return self.type_definitions.get(type_id)
    
    def parse_raw_value(self, raw_value: int, type_def: VariableTypeDefinition) -> tuple[Any, str]:
        """
        Парсинг сырого значения в типизированное
        
        Returns:
            tuple: (parsed_value, status)
        """
        # Проверяем специальные значения
        if type_def.special_values and raw_value in type_def.special_values:
            special_status = type_def.special_values[raw_value]
            return special_status, special_status
        
        try:
            # Применяем знаковость
            if type_def.signed:
                # Преобразование в 16-битное знаковое число
                if raw_value > 32767:
                    value = raw_value - 65536
                else:
                    value = raw_value
            else:
                value = raw_value
            
            # Специальная обработка по типу
            if type_def.var_type == VariableType.BOOL:
                parsed_value = bool(value)
                
            elif type_def.var_type == VariableType.TEMPERATURE:
                # Температура обычно в десятых долях градуса
                parsed_value = float(value) * type_def.scale
                
            elif type_def.var_type == VariableType.PERCENTAGE:
                # Проценты обычно в десятых долях процента
                parsed_value = float(value) * type_def.scale
                
            elif type_def.var_type == VariableType.VERSION:
                # Версия ПО: 401 -> "4.01"
                major = value // 100
                minor = value % 100
                parsed_value = f"{major}.{minor:02d}"
                
            elif type_def.var_type == VariableType.BITFIELD:
                # Битовое поле оставляем как есть
                parsed_value = value
                
            else:
                # Обычные числовые типы
                parsed_value = float(value) * type_def.scale
            
            # Проверяем диапазон
            if (isinstance(parsed_value, (int, float)) and 
                type_def.min_val is not None and 
                type_def.max_val is not None):
                if parsed_value < type_def.min_val or parsed_value > type_def.max_val:
                    logger.warning(f"Значение {parsed_value} вне диапазона [{type_def.min_val}, {type_def.max_val}]")
            
            return parsed_value, "ok"
            
        except Exception as e:
            logger.error(f"Ошибка парсинга значения {raw_value} для типа {type_def.name}: {e}")
            return raw_value, "error"
    
    def convert_register_data(self, device_id: int, register_data: Dict[int, int]) -> List[VariableValue]:
        """
        Конвертация данных регистров в переменные
        
        Args:
            device_id: ID устройства
            register_data: {register_address: raw_value}
            
        Returns:
            List[VariableValue]: Список переменных с parsed значениями
        """
        variables = []
        timestamp = datetime.now()
        
        for register_addr, raw_value in register_data.items():
            # Находим переменную по адресу регистра
            var_ref = self.get_variable_by_register(register_addr)
            if not var_ref:
                logger.debug(f"Переменная для регистра 0x{register_addr:04X} не найдена")
                continue
            
            # Получаем определение типа
            type_def = self.get_type_definition(var_ref.type_id)
            if not type_def:
                logger.warning(f"Тип {var_ref.type_id} для переменной {var_ref.name} не найден")
                continue
            
            # Парсим значение
            parsed_value, status = self.parse_raw_value(raw_value, type_def)
            
            # Создаём VariableValue
            var_value = VariableValue(
                device_id=device_id,
                variable_name=var_ref.name,
                register_address=register_addr,
                raw_value=raw_value,
                parsed_value=parsed_value,
                status=status,
                timestamp=timestamp,
                unit=type_def.unit
            )
            
            variables.append(var_value)
            logger.debug(f"Конвертирована переменная {var_ref.name}: {raw_value} -> {parsed_value}")
        
        return variables
    
    def get_all_register_addresses(self) -> List[int]:
        """Получение всех адресов регистров для чтения"""
        return list(self.register_to_variable.keys())
    
    def get_registers_for_reading(self, variable_names: List[str]) -> List[int]:
        """Получение адресов регистров для чтения указанных переменных"""
        addresses = []
        for name in variable_names:
            var_ref = self.get_variable_by_name(name)
            if var_ref:
                addresses.append(var_ref.register_address)
            else:
                logger.warning(f"Переменная {name} не найдена")
        return addresses
    
    def get_variable_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Получение полной информации о переменной"""
        var_ref = self.get_variable_by_name(name)
        if not var_ref:
            return None
        
        type_def = self.get_type_definition(var_ref.type_id)
        if not type_def:
            return None
        
        return {
            'name': var_ref.name,
            'register_address': var_ref.register_address,
            'register_hex': f"0x{var_ref.register_address:04X}",
            'type_name': type_def.name,
            'var_type': type_def.var_type.name,
            'unit': type_def.unit,
            'scale': type_def.scale,
            'signed': type_def.signed,
            'min_val': type_def.min_val,
            'max_val': type_def.max_val,
            'description': var_ref.description or type_def.description
        }
    
    def get_all_variables_info(self) -> List[Dict[str, Any]]:
        """Получение информации обо всех переменных"""
        variables_info = []
        for var_name in self.variable_references.keys():
            info = self.get_variable_info(var_name)
            if info:
                variables_info.append(info)
        
        return sorted(variables_info, key=lambda x: x['register_address'])


class DeviceVariableManager:
    """
    Менеджер переменных конкретного устройства
    Объединяет mapper с кэшированием значений
    """
    
    def __init__(self, device_id: int, device_type: str, mapper: KUBVariableMapper):
        self.device_id = device_id
        self.device_type = device_type
        self.mapper = mapper
        
        # Кэш текущих значений переменных
        self.current_values: Dict[str, VariableValue] = {}
        
    def update_from_registers(self, register_data: Dict[int, int]):
        """Обновление переменных из данных регистров"""
        variables = self.mapper.convert_register_data(self.device_id, register_data)
        
        # Обновляем кэш
        for var_value in variables:
            self.current_values[var_value.variable_name] = var_value
            
        logger.debug(f"Обновлено {len(variables)} переменных для устройства {self.device_id}")
    
    def get_variable_value(self, name: str) -> Any:
        """Получение текущего значения переменной"""
        var_value = self.current_values.get(name)
        return var_value.parsed_value if var_value else None
    
    def get_variable_status(self, name: str) -> str:
        """Получение статуса переменной"""
        var_value = self.current_values.get(name)
        return var_value.status if var_value else "unknown"
    
    def get_all_values(self) -> Dict[str, Any]:
        """Получение всех текущих значений"""
        return {name: var.parsed_value for name, var in self.current_values.items()}
    
    def get_all_statuses(self) -> Dict[str, str]:
        """Получение всех статусов переменных"""
        return {name: var.status for name, var in self.current_values.items()}
    
    def get_registers_to_read(self) -> List[int]:
        """Получение списка регистров для чтения"""
        return self.mapper.get_all_register_addresses()
    
    def get_variables_by_status(self, status: str) -> List[str]:
        """Получение переменных с определённым статусом"""
        return [name for name, var in self.current_values.items() if var.status == status]
    
    def has_errors(self) -> bool:
        """Проверка наличия ошибок в переменных"""
        return len(self.get_variables_by_status("error")) > 0
    
    def has_disabled_sensors(self) -> bool:
        """Проверка наличия отключенных датчиков"""
        return len(self.get_variables_by_status("disabled")) > 0