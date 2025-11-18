#!/usr/bin/env python3
"""
Типизированные Modbus Request/Response классы
Паттерн из ST_RS: MessageGetDataReq/Rsp - строгая типизация сообщений
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any

from .message_builder import ModbusMessageBuilder


# ============================================================================
# Базовые классы
# ============================================================================

class ModbusRequest(ABC):
    """Базовый класс для Modbus запросов"""

    @abstractmethod
    def build(self) -> bytes:
        """Построить бинарное сообщение для отправки"""
        pass

    @abstractmethod
    def get_function_code(self) -> int:
        """Получить код функции"""
        pass


class ModbusResponse(ABC):
    """Базовый класс для Modbus ответов"""

    @classmethod
    @abstractmethod
    def parse(cls, data: bytes) -> 'ModbusResponse':
        """Распарсить бинарное сообщение"""
        pass

    @abstractmethod
    def is_success(self) -> bool:
        """Проверка успешности операции"""
        pass


# ============================================================================
# Read Holding Registers (Function 0x03)
# ============================================================================

@dataclass
class ReadHoldingRegistersRequest(ModbusRequest):
    """
    Function 0x03: Read Holding Registers
    Чтение регистров хранения (наиболее часто используемая функция)
    """
    slave_id: int
    start_address: int
    count: int

    def __post_init__(self):
        """Валидация параметров"""
        if not (0 <= self.slave_id <= 247):
            raise ValueError(f"Invalid slave_id: {self.slave_id} (must be 0-247)")

        if not (0 <= self.start_address <= 0xFFFF):
            raise ValueError(f"Invalid start_address: {self.start_address}")

        if not (1 <= self.count <= 125):
            raise ValueError(f"Invalid count: {self.count} (must be 1-125)")

    def get_function_code(self) -> int:
        return 0x03

    def build(self) -> bytes:
        """
        Построить Modbus RTU сообщение

        Формат: [Slave ID][Func][Start Addr Hi][Start Addr Lo][Count Hi][Count Lo][CRC Lo][CRC Hi]
        """
        return (ModbusMessageBuilder(slave_id=self.slave_id)
            .set_function(self.get_function_code())
            .write_uint16(self.start_address)
            .write_uint16(self.count)
            .finalize_with_crc())

    def __repr__(self) -> str:
        return (f"ReadHoldingRegistersRequest(slave_id={self.slave_id}, "
                f"start=0x{self.start_address:04X}, count={self.count})")


@dataclass
class ReadHoldingRegistersResponse(ModbusResponse):
    """
    Ответ на чтение Holding Registers

    Attributes:
        slave_id: ID устройства
        function_code: Код функции (0x03 или 0x83 при ошибке)
        registers: Список значений регистров
        timestamp: Время получения ответа
        exception_code: Код ошибки Modbus (если есть)
    """
    slave_id: int
    function_code: int
    registers: List[int] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    exception_code: Optional[int] = None

    def is_success(self) -> bool:
        """Проверка успешности (нет exception)"""
        return self.exception_code is None and (self.function_code & 0x80) == 0

    def is_exception(self) -> bool:
        """Проверка на Modbus exception"""
        return (self.function_code & 0x80) != 0

    def get_register(self, index: int) -> Optional[int]:
        """
        Получить значение регистра по индексу

        Args:
            index: Индекс регистра (0-based)

        Returns:
            Значение регистра или None
        """
        if 0 <= index < len(self.registers):
            return self.registers[index]
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь"""
        return {
            'slave_id': self.slave_id,
            'function_code': f'0x{self.function_code:02X}',
            'registers': self.registers,
            'register_count': len(self.registers),
            'timestamp': self.timestamp.isoformat(),
            'success': self.is_success(),
            'exception_code': self.exception_code
        }

    @classmethod
    def parse(cls, data: bytes) -> 'ReadHoldingRegistersResponse':
        """
        Распарсить ответ от устройства

        Формат успешного ответа:
            [Slave ID][Func][Byte Count][Data...][CRC Lo][CRC Hi]

        Формат ответа с ошибкой:
            [Slave ID][Func | 0x80][Exception Code][CRC Lo][CRC Hi]
        """
        if len(data) < 5:
            raise ValueError(f"Response too short: {len(data)} bytes")

        slave_id = data[0]
        function_code = data[1]

        # Проверка на exception
        if function_code & 0x80:
            exception_code = data[2]
            return cls(
                slave_id=slave_id,
                function_code=function_code,
                registers=[],
                exception_code=exception_code
            )

        # Нормальный ответ
        byte_count = data[2]

        if len(data) < 3 + byte_count + 2:
            raise ValueError(f"Incomplete response: expected {3 + byte_count + 2}, got {len(data)}")

        # Парсим регистры (по 2 байта каждый)
        registers = []
        for i in range(3, 3 + byte_count, 2):
            register_value = int.from_bytes(data[i:i+2], byteorder='big', signed=False)
            registers.append(register_value)

        return cls(
            slave_id=slave_id,
            function_code=function_code,
            registers=registers
        )

    def __repr__(self) -> str:
        if self.is_exception():
            return (f"ReadHoldingRegistersResponse(slave_id={self.slave_id}, "
                    f"EXCEPTION=0x{self.exception_code:02X})")
        else:
            return (f"ReadHoldingRegistersResponse(slave_id={self.slave_id}, "
                    f"registers={len(self.registers)})")


# ============================================================================
# Write Single Register (Function 0x06)
# ============================================================================

@dataclass
class WriteSingleRegisterRequest(ModbusRequest):
    """
    Function 0x06: Write Single Register
    Запись одного регистра
    """
    slave_id: int
    address: int
    value: int

    def __post_init__(self):
        """Валидация параметров"""
        if not (0 <= self.slave_id <= 247):
            raise ValueError(f"Invalid slave_id: {self.slave_id}")

        if not (0 <= self.address <= 0xFFFF):
            raise ValueError(f"Invalid address: {self.address}")

        if not (0 <= self.value <= 0xFFFF):
            raise ValueError(f"Invalid value: {self.value}")

    def get_function_code(self) -> int:
        return 0x06

    def build(self) -> bytes:
        """
        Построить Modbus RTU сообщение

        Формат: [Slave ID][Func][Addr Hi][Addr Lo][Value Hi][Value Lo][CRC Lo][CRC Hi]
        """
        return (ModbusMessageBuilder(slave_id=self.slave_id)
            .set_function(self.get_function_code())
            .write_uint16(self.address)
            .write_uint16(self.value)
            .finalize_with_crc())

    def __repr__(self) -> str:
        return (f"WriteSingleRegisterRequest(slave_id={self.slave_id}, "
                f"addr=0x{self.address:04X}, value=0x{self.value:04X})")


@dataclass
class WriteSingleRegisterResponse(ModbusResponse):
    """
    Ответ на запись одного регистра

    В случае успеха устройство возвращает echo запроса
    """
    slave_id: int
    function_code: int
    address: int
    value: int
    timestamp: datetime = field(default_factory=datetime.now)
    exception_code: Optional[int] = None

    def is_success(self) -> bool:
        """Проверка успешности"""
        return self.exception_code is None and (self.function_code & 0x80) == 0

    def is_exception(self) -> bool:
        """Проверка на Modbus exception"""
        return (self.function_code & 0x80) != 0

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь"""
        return {
            'slave_id': self.slave_id,
            'function_code': f'0x{self.function_code:02X}',
            'address': f'0x{self.address:04X}',
            'value': self.value,
            'timestamp': self.timestamp.isoformat(),
            'success': self.is_success(),
            'exception_code': self.exception_code
        }

    @classmethod
    def parse(cls, data: bytes) -> 'WriteSingleRegisterResponse':
        """
        Распарсить ответ от устройства

        Формат успешного ответа (echo запроса):
            [Slave ID][Func][Addr Hi][Addr Lo][Value Hi][Value Lo][CRC Lo][CRC Hi]

        Формат ответа с ошибкой:
            [Slave ID][Func | 0x80][Exception Code][CRC Lo][CRC Hi]
        """
        if len(data) < 5:
            raise ValueError(f"Response too short: {len(data)} bytes")

        slave_id = data[0]
        function_code = data[1]

        # Проверка на exception
        if function_code & 0x80:
            exception_code = data[2]
            return cls(
                slave_id=slave_id,
                function_code=function_code,
                address=0,
                value=0,
                exception_code=exception_code
            )

        # Нормальный ответ
        if len(data) < 8:
            raise ValueError(f"Incomplete response: expected 8, got {len(data)}")

        address = int.from_bytes(data[2:4], byteorder='big')
        value = int.from_bytes(data[4:6], byteorder='big')

        return cls(
            slave_id=slave_id,
            function_code=function_code,
            address=address,
            value=value
        )

    def __repr__(self) -> str:
        if self.is_exception():
            return (f"WriteSingleRegisterResponse(slave_id={self.slave_id}, "
                    f"EXCEPTION=0x{self.exception_code:02X})")
        else:
            return (f"WriteSingleRegisterResponse(slave_id={self.slave_id}, "
                    f"addr=0x{self.address:04X}, value=0x{self.value:04X})")


# ============================================================================
# Modbus Exception Codes
# ============================================================================

class ModbusExceptionCode:
    """Коды Modbus exceptions"""
    ILLEGAL_FUNCTION = 0x01
    ILLEGAL_DATA_ADDRESS = 0x02
    ILLEGAL_DATA_VALUE = 0x03
    SLAVE_DEVICE_FAILURE = 0x04
    ACKNOWLEDGE = 0x05
    SLAVE_DEVICE_BUSY = 0x06
    MEMORY_PARITY_ERROR = 0x08
    GATEWAY_PATH_UNAVAILABLE = 0x0A
    GATEWAY_TARGET_DEVICE_FAILED_TO_RESPOND = 0x0B

    @staticmethod
    def get_description(code: int) -> str:
        """Получить описание кода ошибки"""
        descriptions = {
            0x01: "Illegal Function - Функция не поддерживается устройством",
            0x02: "Illegal Data Address - Неверный адрес регистра",
            0x03: "Illegal Data Value - Неверное значение данных",
            0x04: "Slave Device Failure - Ошибка устройства",
            0x05: "Acknowledge - Устройство приняло запрос, но обработка займет время",
            0x06: "Slave Device Busy - Устройство занято",
            0x08: "Memory Parity Error - Ошибка памяти устройства",
            0x0A: "Gateway Path Unavailable - Шлюз недоступен",
            0x0B: "Gateway Target Device Failed to Respond - Целевое устройство не отвечает",
        }
        return descriptions.get(code, f"Unknown Exception Code: 0x{code:02X}")
