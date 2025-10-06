#!/usr/bin/env python3
"""
Variable Mapping and Data Conversion Module
Модуль маппинга переменных и конвертации данных
Реализует функциональность FE_Types, FE_References из C#
"""

import struct
import uuid
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import IntEnum
from datetime import datetime
import logging

class VariableType(IntEnum):
    """Типы переменных (расширить согласно вашей системе)"""
    BOOL = 0
    BYTE = 1
    SHORT = 2
    INT = 3
    FLOAT = 4
    STRING = 5
    DATETIME = 6
    DOUBLE = 7

@dataclass
class FE_Type:
    """Тип переменной (соответствует C# FE_Type)"""
    hardware: int               # Аппаратная версия
    version: int                # Версия ПО
    id: int                     # ID типа
    name: str                   # Имя типа
    type: VariableType          # Тип данных
    mul: int                    # Множитель
    div: int                    # Делитель  
    step: float                 # Шаг изменения
    min_val: int                # Минимальное значение
    max_val: int                # Максимальное значение
    text: Optional[int] = None  # Ссылка на текст
    acknowledge_change: bool = False  # Требуется подтверждение

@dataclass
class FE_Reference:
    """Ссылка на переменную (соответствует C# FE_Reference)"""
    hardware: int               # Аппаратная версия
    version: int                # Версия ПО  
    id: int                     # ID ссылки
    index: int                  # Индекс в данных контроллера
    length: int                 # Длина в байтах
    name: str                   # Имя переменной
    type_id: int                # Ссылка на FE_Type.id
    defop: Optional[int] = None # Операция по умолчанию

@dataclass
class VariableValue:
    """Значение переменной"""
    device_id: str              # UUID устройства
    index: int                  # Индекс данных
    timestamp: datetime         # Временная метка
    raw_data: bytes             # Сырые данные
    converted_value: Any = None # Конвертированное значение

class VariableMapper:
    """
    Класс для маппинга и конвертации переменных контроллера
    Реализует логику конвертации данных из протокола в типизированные значения
    """
    
    def __init__(self):
        self.types_cache: Dict[tuple, FE_Type] = {}      # (hardware, version, type_id) -> FE_Type
        self.references_cache: Dict[tuple, FE_Reference] = {}  # (hardware, version, ref_id) -> FE_Reference
        self.name_to_ref_cache: Dict[tuple, FE_Reference] = {} # (hardware, version, name) -> FE_Reference
        
        self.logger = logging.getLogger(__name__)
    
    def register_type(self, fe_type: FE_Type):
        """Регистрация типа переменной"""
        key = (fe_type.hardware, fe_type.version, fe_type.id)
        self.types_cache[key] = fe_type
        self.logger.debug(f"Зарегистрирован тип: {fe_type.name} ({key})")
    
    def register_reference(self, fe_ref: FE_Reference):
        """Регистрация ссылки на переменную"""
        key = (fe_ref.hardware, fe_ref.version, fe_ref.id)
        self.references_cache[key] = fe_ref
        
        name_key = (fe_ref.hardware, fe_ref.version, fe_ref.name)
        self.name_to_ref_cache[name_key] = fe_ref
        
        self.logger.debug(f"Зарегистрирована ссылка: {fe_ref.name} -> индекс {fe_ref.index}")
    
    def get_type(self, hardware: int, version: int, type_id: int) -> Optional[FE_Type]:
        """Получение типа переменной"""
        key = (hardware, version, type_id)
        return self.types_cache.get(key)
    
    def get_reference_by_name(self, hardware: int, version: int, name: str) -> Optional[FE_Reference]:
        """Получение ссылки на переменную по имени"""
        key = (hardware, version, name)
        return self.name_to_ref_cache.get(key)
    
    def get_reference_by_index(self, hardware: int, version: int, index: int) -> Optional[FE_Reference]:
        """Получение ссылки на переменную по индексу"""
        for ref in self.references_cache.values():
            if (ref.hardware == hardware and 
                ref.version == version and 
                ref.index <= index < ref.index + ref.length):
                return ref
        return None
    
    def convert_raw_to_value(self, raw_data: bytes, var_type: FE_Type) -> Any:
        """
        Конвертация сырых данных в типизированное значение
        Учитывает множители, делители и тип данных
        """
        if not raw_data:
            return None
        
        try:
            # Базовая конвертация по типу
            if var_type.type == VariableType.BOOL:
                value = raw_data[0] != 0 if raw_data else False
                
            elif var_type.type == VariableType.BYTE:
                value = raw_data[0] if raw_data else 0
                
            elif var_type.type == VariableType.SHORT:
                if len(raw_data) >= 2:
                    value = struct.unpack('<h', raw_data[:2])[0]  # Little Endian
                else:
                    value = 0
                    
            elif var_type.type == VariableType.INT:
                if len(raw_data) >= 4:
                    value = struct.unpack('<i', raw_data[:4])[0]  # Little Endian
                else:
                    value = 0
                    
            elif var_type.type == VariableType.FLOAT:
                if len(raw_data) >= 4:
                    value = struct.unpack('<f', raw_data[:4])[0]  # Little Endian
                else:
                    value = 0.0
                    
            elif var_type.type == VariableType.DOUBLE:
                if len(raw_data) >= 8:
                    value = struct.unpack('<d', raw_data[:8])[0]  # Little Endian
                else:
                    value = 0.0
                    
            elif var_type.type == VariableType.STRING:
                # Строка до первого нулевого байта
                try:
                    null_pos = raw_data.index(0)
                    value = raw_data[:null_pos].decode('ascii', errors='ignore')
                except ValueError:
                    value = raw_data.decode('ascii', errors='ignore')
                    
            elif var_type.type == VariableType.DATETIME:
                # Формат времени зависит от контроллера - нужно уточнить
                if len(raw_data) >= 4:
                    timestamp = struct.unpack('<I', raw_data[:4])[0]
                    # Обычно это секунды с эпохи 2001-01-01 (как в C# коде)
                    epoch = datetime(2001, 1, 1)
                    value = epoch.replace(second=timestamp % 60,
                                        minute=(timestamp // 60) % 60,
                                        hour=(timestamp // 3600) % 24)
                else:
                    value = datetime.now()
            else:
                # Неизвестный тип - возвращаем как есть
                value = raw_data
            
            # Применяем множители и делители (если это числовое значение)
            if isinstance(value, (int, float)) and var_type.div != 0:
                value = (value * var_type.mul) / var_type.div
            
            # Проверяем диапазон
            if isinstance(value, (int, float)):
                if value < var_type.min_val:
                    value = var_type.min_val
                elif value > var_type.max_val:
                    value = var_type.max_val
            
            return value
            
        except Exception as e:
            self.logger.error(f"Ошибка конвертации данных для типа {var_type.name}: {e}")
            return None
    
    def convert_value_to_raw(self, value: Any, var_type: FE_Type) -> bytes:
        """
        Конвертация типизированного значения в сырые данные
        Обратная операция для отправки данных в контроллер
        """
        try:
            # Применяем обратные множители/делители
            if isinstance(value, (int, float)) and var_type.mul != 0:
                raw_value = int((value * var_type.div) / var_type.mul)
            else:
                raw_value = value
            
            # Конвертация по типу
            if var_type.type == VariableType.BOOL:
                return struct.pack('B', 1 if raw_value else 0)
                
            elif var_type.type == VariableType.BYTE:
                return struct.pack('B', int(raw_value) & 0xFF)
                
            elif var_type.type == VariableType.SHORT:
                return struct.pack('<h', int(raw_value))
                
            elif var_type.type == VariableType.INT:
                return struct.pack('<i', int(raw_value))
                
            elif var_type.type == VariableType.FLOAT:
                return struct.pack('<f', float(raw_value))
                
            elif var_type.type == VariableType.DOUBLE:
                return struct.pack('<d', float(raw_value))
                
            elif var_type.type == VariableType.STRING:
                # Строка с нулевым терминатором
                str_bytes = str(raw_value).encode('ascii', errors='ignore')
                # Обрезаем или дополняем до нужной длины
                return str_bytes[:var_type.max_val] + b'\x00'
                
            elif var_type.type == VariableType.DATETIME:
                if isinstance(raw_value, datetime):
                    # Конвертируем в секунды с эпохи 2001-01-01
                    epoch = datetime(2001, 1, 1)
                    delta = raw_value - epoch
                    seconds = int(delta.total_seconds())
                    return struct.pack('<I', seconds)
                else:
                    return struct.pack('<I', 0)
            
            else:
                # Неизвестный тип
                if isinstance(raw_value, bytes):
                    return raw_value
                else:
                    return str(raw_value).encode('ascii', errors='ignore')
                    
        except Exception as e:
            self.logger.error(f"Ошибка конвертации значения {value} для типа {var_type.name}: {e}")
            return b''
    
    def map_data_to_variables(self, device_id: str, hardware: int, version: int, 
                            data_items: List['DataItem']) -> List[VariableValue]:
        """
        Маппинг данных протокола на переменные контроллера
        Конвертирует DataItem в VariableValue с типизацией
        """
        variables = []
        
        for data_item in data_items:
            # Ищем ссылку на переменную по индексу
            reference = self.get_reference_by_index(hardware, version, data_item.index)
            if not reference:
                self.logger.warning(f"Не найдена ссылка для индекса {data_item.index}")
                continue
            
            # Получаем тип переменной
            var_type = self.get_type(hardware, version, reference.type_id)
            if not var_type:
                self.logger.warning(f"Не найден тип {reference.type_id} для переменной {reference.name}")
                continue
            
            # Конвертируем значение
            converted_value = self.convert_raw_to_value(data_item.value, var_type)
            
            # Создаем VariableValue
            var_value = VariableValue(
                device_id=device_id,
                index=data_item.index,
                timestamp=datetime.now(),
                raw_data=data_item.value,
                converted_value=converted_value
            )
            
            variables.append(var_value)
            
            self.logger.debug(f"Переменная {reference.name}: {data_item.value.hex()} -> {converted_value}")
        
        return variables
    
    def create_data_items_from_variables(self, hardware: int, version: int, 
                                       variable_requests: Dict[str, Any]) -> List['DataItem']:
        """
        Создание DataItem для отправки в контроллер
        
        Args:
            variable_requests: Dict с именами переменных и их значениями
                              {"variable_name": value, ...}
        """
        from .rs485_protocol import DataItem
        
        data_items = []
        
        for var_name, value in variable_requests.items():
            # Ищем ссылку на переменную
            reference = self.get_reference_by_name(hardware, version, var_name)
            if not reference:
                self.logger.warning(f"Не найдена переменная {var_name}")
                continue
            
            # Получаем тип
            var_type = self.get_type(hardware, version, reference.type_id)
            if not var_type:
                self.logger.warning(f"Не найден тип для переменной {var_name}")
                continue
            
            # Конвертируем значение в сырые данные
            raw_data = self.convert_value_to_raw(value, var_type)
            
            # Создаем DataItem
            data_item = DataItem(
                index=reference.index,
                length=len(raw_data),
                value=raw_data
            )
            
            data_items.append(data_item)
            
            self.logger.debug(f"Переменная {var_name}: {value} -> {raw_data.hex()}")
        
        return data_items
    
    def load_types_from_config(self, types_config: List[Dict[str, Any]]):
        """
        Загрузка типов переменных из конфигурации
        
        Args:
            types_config: Список словарей с данными типов
        """
        for type_data in types_config:
            fe_type = FE_Type(
                hardware=type_data['hardware'],
                version=type_data['version'],
                id=type_data['id'],
                name=type_data['name'],
                type=VariableType(type_data['type']),
                mul=type_data.get('mul', 1),
                div=type_data.get('div', 1),
                step=type_data.get('step', 1.0),
                min_val=type_data.get('min', 0),
                max_val=type_data.get('max', 65535),
                text=type_data.get('text'),
                acknowledge_change=type_data.get('acknowledge_change', False)
            )
            self.register_type(fe_type)
    
    def load_references_from_config(self, references_config: List[Dict[str, Any]]):
        """
        Загрузка ссылок на переменные из конфигурации
        
        Args:
            references_config: Список словарей с данными ссылок
        """
        for ref_data in references_config:
            fe_ref = FE_Reference(
                hardware=ref_data['hardware'],
                version=ref_data['version'],
                id=ref_data['id'],
                index=ref_data['index'],
                length=ref_data['length'],
                name=ref_data['name'],
                type_id=ref_data['type_id'],
                defop=ref_data.get('defop')
            )
            self.register_reference(fe_ref)
    
    def get_variable_info(self, hardware: int, version: int, name: str) -> Optional[Dict[str, Any]]:
        """Получение полной информации о переменной"""
        reference = self.get_reference_by_name(hardware, version, name)
        if not reference:
            return None
        
        var_type = self.get_type(hardware, version, reference.type_id)
        if not var_type:
            return None
        
        return {
            'name': reference.name,
            'index': reference.index,
            'length': reference.length,
            'type': var_type.type.name,
            'type_name': var_type.name,
            'mul': var_type.mul,
            'div': var_type.div,
            'min': var_type.min_val,
            'max': var_type.max_val,
            'step': var_type.step
        }
    
    def get_all_variables(self, hardware: int, version: int) -> List[Dict[str, Any]]:
        """Получение списка всех переменных для указанной версии контроллера"""
        variables = []
        
        for ref in self.references_cache.values():
            if ref.hardware == hardware and ref.version == version:
                var_type = self.get_type(hardware, version, ref.type_id)
                if var_type:
                    variables.append({
                        'name': ref.name,
                        'index': ref.index,
                        'length': ref.length,
                        'type': var_type.type.name,
                        'type_name': var_type.name,
                        'description': f"{var_type.name} ({var_type.min_val}-{var_type.max_val})"
                    })
        
        return sorted(variables, key=lambda x: x['index'])
    
    def create_read_request_for_variables(self, hardware: int, version: int, 
                                        variable_names: List[str]) -> List['DataItem']:
        """
        Создание запроса на чтение указанных переменных
        Возвращает список DataItem для протокола
        """
        from .rs485_protocol import DataItem
        
        data_items = []
        
        for var_name in variable_names:
            reference = self.get_reference_by_name(hardware, version, var_name)
            if reference:
                # Для чтения достаточно указать индекс и длину
                data_item = DataItem(
                    index=reference.index,
                    length=reference.length,
                    value=b''  # Пустое значение для запроса чтения
                )
                data_items.append(data_item)
            else:
                self.logger.warning(f"Переменная {var_name} не найдена")
        
        return data_items
    
    def validate_variable_value(self, value: Any, var_type: FE_Type) -> bool:
        """Валидация значения переменной"""
        if var_type.type in [VariableType.BOOL]:
            return isinstance(value, bool)
        
        elif var_type.type in [VariableType.BYTE, VariableType.SHORT, VariableType.INT]:
            return (isinstance(value, int) and 
                   var_type.min_val <= value <= var_type.max_val)
        
        elif var_type.type in [VariableType.FLOAT, VariableType.DOUBLE]:
            return (isinstance(value, (int, float)) and 
                   var_type.min_val <= value <= var_type.max_val)
        
        elif var_type.type == VariableType.STRING:
            return isinstance(value, str) and len(value) <= var_type.max_val
        
        elif var_type.type == VariableType.DATETIME:
            return isinstance(value, datetime)
        
        return True

class DeviceVariableManager:
    """
    Менеджер переменных устройства
    Объединяет маппинг переменных с конкретным устройством
    """
    
    def __init__(self, device_id: str, hardware: int, version: int, 
                 mapper: VariableMapper):
        self.device_id = device_id
        self.hardware = hardware
        self.version = version
        self.mapper = mapper
        
        # Кэш текущих значений
        self.current_values: Dict[str, VariableValue] = {}
        
        self.logger = logging.getLogger(__name__)
    
    def update_variable_values(self, data_items: List['DataItem']):
        """Обновление значений переменных из данных протокола"""
        variables = self.mapper.map_data_to_variables(
            self.device_id, self.hardware, self.version, data_items
        )
        
        for var in variables:
            # Находим имя переменной
            ref = self.mapper.get_reference_by_index(
                self.hardware, self.version, var.index
            )
            if ref:
                self.current_values[ref.name] = var
                self.logger.debug(f"Обновлена переменная {ref.name}: {var.converted_value}")
    
    def get_variable_value(self, name: str) -> Any:
        """Получение текущего значения переменной"""
        var_value = self.current_values.get(name)
        return var_value.converted_value if var_value else None
    
    def set_variable_value(self, name: str, value: Any) -> bool:
        """
        Установка значения переменной (подготовка к отправке)
        Возвращает True если значение валидно
        """
        reference = self.mapper.get_reference_by_name(self.hardware, self.version, name)
        if not reference:
            self.logger.error(f"Переменная {name} не найдена")
            return False
        
        var_type = self.mapper.get_type(self.hardware, self.version, reference.type_id)
        if not var_type:
            self.logger.error(f"Тип для переменной {name} не найден")
            return False
        
        # Валидация
        if not self.mapper.validate_variable_value(value, var_type):
            self.logger.error(f"Неверное значение {value} для переменной {name}")
            return False
        
        # Создаем VariableValue для локального хранения
        raw_data = self.mapper.convert_value_to_raw(value, var_type)
        var_value = VariableValue(
            device_id=self.device_id,
            index=reference.index,
            timestamp=datetime.now(),
            raw_data=raw_data,
            converted_value=value
        )
        
        self.current_values[name] = var_value
        return True
    
    def get_all_current_values(self) -> Dict[str, Any]:
        """Получение всех текущих значений переменных"""
        return {name: var.converted_value 
                for name, var in self.current_values.items()}
    
    def get_variables_for_read(self, variable_names: List[str]) -> List['DataItem']:
        """Создание запроса на чтение переменных"""
        return self.mapper.create_read_request_for_variables(
            self.hardware, self.version, variable_names
        )
    
    def get_variables_for_write(self, variables: Dict[str, Any]) -> List['DataItem']:
        """Создание данных для записи переменных"""
        return self.mapper.create_data_items_from_variables(
            self.hardware, self.version, variables
        )

# Пример конфигурации переменных
EXAMPLE_TYPES_CONFIG = [
    {
        'hardware': 1001,
        'version': 1,
        'id': 1,
        'name': 'Temperature',
        'type': VariableType.SHORT,
        'mul': 1,
        'div': 10,  # Температура в десятых долях градуса
        'step': 0.1,
        'min': -500,  # -50.0°C
        'max': 1000,  # 100.0°C
    },
    {
        'hardware': 1001,
        'version': 1,
        'id': 2,
        'name': 'Boolean',
        'type': VariableType.BOOL,
        'mul': 1,
        'div': 1,
        'step': 1,
        'min': 0,
        'max': 1,
    },
    {
        'hardware': 1001,
        'version': 1,
        'id': 3,
        'name': 'Counter',
        'type': VariableType.INT,
        'mul': 1,
        'div': 1,
        'step': 1,
        'min': 0,
        'max': 2147483647,
    }
]

EXAMPLE_REFERENCES_CONFIG = [
    {
        'hardware': 1001,
        'version': 1,
        'id': 1,
        'index': 100,  # Индекс в данных контроллера
        'length': 2,   # 2 байта для SHORT
        'name': 'AirTemperature',
        'type_id': 1,  # Ссылка на Temperature тип
    },
    {
        'hardware': 1001,
        'version': 1,
        'id': 2,
        'index': 200,
        'length': 1,   # 1 байт для BOOL
        'name': 'FanEnabled',
        'type_id': 2,  # Ссылка на Boolean тип
    },
    {
        'hardware': 1001,
        'version': 1,
        'id': 3,
        'index': 300,
        'length': 4,   # 4 байта для INT
        'name': 'TotalRuntime',
        'type_id': 3,  # Ссылка на Counter тип
    }
]

# Пример использования
if __name__ == "__main__":
    # Создаем маппер
    mapper = VariableMapper()
    
    # Загружаем конфигурацию
    mapper.load_types_from_config(EXAMPLE_TYPES_CONFIG)
    mapper.load_references_from_config(EXAMPLE_REFERENCES_CONFIG)
    
    # Создаем менеджер для устройства
    device_manager = DeviceVariableManager(
        device_id=str(uuid.uuid4()),
        hardware=1001,
        version=1,
        mapper=mapper
    )
    
    # Пример установки значений
    device_manager.set_variable_value('AirTemperature', 25.5)  # 25.5°C
    device_manager.set_variable_value('FanEnabled', True)
    device_manager.set_variable_value('TotalRuntime', 12345)
    
    # Получение всех значений
    all_values = device_manager.get_all_current_values()
    print(f"Текущие значения: {all_values}")
    
    # Получение информации о переменных
    for var_name in ['AirTemperature', 'FanEnabled', 'TotalRuntime']:
        info = mapper.get_variable_info(1001, 1, var_name)
        print(f"{var_name}: {info}")
