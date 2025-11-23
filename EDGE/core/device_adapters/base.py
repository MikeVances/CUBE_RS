#!/usr/bin/env python3
"""
Базовые классы для адаптеров устройств
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Union
from enum import Enum


class ValueType(Enum):
    """Типы значений регистров"""
    TEMPERATURE = "temperature"
    PERCENTAGE = "percentage"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    FLOAT = "float"
    BITFIELD = "bitfield"
    STATUS = "status"
    VERSION = "version"


class RegisterType(Enum):
    """Тип регистра Modbus"""
    HOLDING = "holding"  # Function Code 03 (Read Holding Registers)
    INPUT = "input"      # Function Code 04 (Read Input Registers)


@dataclass
class RegisterInfo:
    """Информация о регистре"""
    address: int
    name: str
    value_type: ValueType
    unit: Optional[str] = None
    scale: float = 1.0
    signed: bool = False
    description: Optional[str] = None
    register_type: RegisterType = RegisterType.HOLDING  # По умолчанию Holding (FC03)

    # Специальные значения для обработки
    special_values: Optional[Dict[int, str]] = None  # {0xFFFF: "not_ready", 0x8000: "error"}


@dataclass 
class DeviceData:
    """Данные устройства"""
    device_id: int
    device_type: str
    registers: Dict[str, Any]  # {register_name: parsed_value}
    raw_registers: Dict[str, int]  # {register_name: raw_value} 
    status: Dict[str, str]  # {register_name: status} - "ok", "error", "disabled", etc
    timestamp: Optional[str] = None


class DeviceAdapter(ABC):
    """Базовый класс для адаптеров устройств"""
    
    @property
    @abstractmethod
    def device_type(self) -> str:
        """Тип устройства"""
        pass
    
    @property 
    @abstractmethod
    def register_map(self) -> Dict[str, RegisterInfo]:
        """Карта регистров устройства"""
        pass
    
    @abstractmethod
    def parse_register_value(self, register_name: str, raw_value: int) -> tuple[Any, str]:
        """
        Парсинг сырого значения регистра
        
        Returns:
            tuple: (parsed_value, status)
            - parsed_value: распарсенное значение
            - status: "ok", "error", "disabled", "pending", etc
        """
        pass
    
    @abstractmethod
    def format_for_display(self, data: DeviceData) -> str:
        """Форматирование данных для отображения в боте/UI"""
        pass
    
    @abstractmethod
    def get_critical_alarms(self, data: DeviceData) -> List[str]:
        """Получение критичных аварий"""
        pass
    
    @abstractmethod
    def get_warnings(self, data: DeviceData) -> List[str]:
        """Получение предупреждений"""
        pass

    @property
    def max_batch_size(self) -> int:
        """Максимальное количество регистров в одном запросе FC03/FC04."""
        return 20
    
    def get_register_addresses(self) -> List[int]:
        """Получение списка адресов регистров для чтения"""
        return [reg.address for reg in self.register_map.values()]
    
    def get_register_by_address(self, address: int) -> Optional[RegisterInfo]:
        """Поиск регистра по адресу"""
        for reg in self.register_map.values():
            if reg.address == address:
                return reg
        return None
    
    def parse_device_data(self, device_id: int, raw_registers: Dict[int, int]) -> DeviceData:
        """
        Парсинг всех данных устройства
        
        Args:
            device_id: ID устройства
            raw_registers: {register_address: raw_value}
        
        Returns:
            DeviceData: Полные данные устройства
        """
        registers = {}
        raw_by_name = {}
        status = {}
        
        for register_name, register_info in self.register_map.items():
            if register_info.address in raw_registers:
                raw_value = raw_registers[register_info.address]
                parsed_value, value_status = self.parse_register_value(register_name, raw_value)
                
                registers[register_name] = parsed_value
                raw_by_name[register_name] = raw_value
                status[register_name] = value_status
        
        return DeviceData(
            device_id=device_id,
            device_type=self.device_type,
            registers=registers,
            raw_registers=raw_by_name,
            status=status
        )
    
    def _apply_scale_and_sign(self, raw_value: int, register_info: RegisterInfo) -> Union[int, float]:
        """Применение масштаба и знака к сырому значению"""
        # Применяем знаковость
        if register_info.signed:
            # Преобразование в знаковое 16-битное число
            if raw_value > 32767:
                raw_value = raw_value - 65536
        
        # Применяем масштаб
        if register_info.scale != 1.0:
            return raw_value * register_info.scale
        
        return raw_value
    
    def _check_special_values(self, raw_value: int, register_info: RegisterInfo) -> Optional[str]:
        """Проверка специальных значений"""
        if register_info.special_values:
            return register_info.special_values.get(raw_value)
        
        return None
