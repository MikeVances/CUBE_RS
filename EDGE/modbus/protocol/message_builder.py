#!/usr/bin/env python3
"""
Modbus Message Builder with Fluent Interface
Паттерн из ST_RS: StienenStream - цепочка вызовов для сериализации
"""

from enum import Enum
from typing import Optional


class ByteOrder(Enum):
    """Порядок байтов для сериализации"""
    BIG_ENDIAN = 'big'
    LITTLE_ENDIAN = 'little'


class ModbusMessageBuilder:
    """
    Fluent Interface для построения Modbus RTU сообщений

    Пример использования:
        message = (ModbusMessageBuilder(slave_id=1)
            .set_function(0x03)
            .write_uint16(0x1000)  # start address
            .write_uint16(10)       # count
            .finalize_with_crc())
    """

    def __init__(
        self,
        slave_id: Optional[int] = None,
        byte_order: ByteOrder = ByteOrder.BIG_ENDIAN
    ):
        """
        Инициализация builder'а

        Args:
            slave_id: ID устройства (если None, нужно будет установить позже)
            byte_order: Порядок байтов (по умолчанию Big-Endian для Modbus RTU)
        """
        self._buffer = bytearray()
        self.byte_order = byte_order
        self._finalized = False

        if slave_id is not None:
            self.write_uint8(slave_id)

    def write_uint8(self, value: int) -> 'ModbusMessageBuilder':
        """
        Записать unsigned 8-bit integer (1 байт)

        Args:
            value: Значение 0-255

        Returns:
            self для цепочки вызовов
        """
        if self._finalized:
            raise RuntimeError("Cannot modify finalized message")

        self._buffer.append(value & 0xFF)
        return self

    def write_int8(self, value: int) -> 'ModbusMessageBuilder':
        """
        Записать signed 8-bit integer (1 байт)

        Args:
            value: Значение -128 до 127

        Returns:
            self для цепочки вызовов
        """
        if self._finalized:
            raise RuntimeError("Cannot modify finalized message")

        # Преобразование signed в unsigned
        if value < 0:
            value = 256 + value

        self._buffer.append(value & 0xFF)
        return self

    def write_uint16(self, value: int) -> 'ModbusMessageBuilder':
        """
        Записать unsigned 16-bit integer (2 байта)

        Args:
            value: Значение 0-65535

        Returns:
            self для цепочки вызовов
        """
        if self._finalized:
            raise RuntimeError("Cannot modify finalized message")

        self._buffer.extend(
            value.to_bytes(2, byteorder=self.byte_order.value, signed=False)
        )
        return self

    def write_int16(self, value: int) -> 'ModbusMessageBuilder':
        """
        Записать signed 16-bit integer (2 байта)

        Args:
            value: Значение -32768 до 32767

        Returns:
            self для цепочки вызовов
        """
        if self._finalized:
            raise RuntimeError("Cannot modify finalized message")

        self._buffer.extend(
            value.to_bytes(2, byteorder=self.byte_order.value, signed=True)
        )
        return self

    def write_uint32(self, value: int) -> 'ModbusMessageBuilder':
        """
        Записать unsigned 32-bit integer (4 байта)

        Args:
            value: Значение 0-4294967295

        Returns:
            self для цепочки вызовов
        """
        if self._finalized:
            raise RuntimeError("Cannot modify finalized message")

        self._buffer.extend(
            value.to_bytes(4, byteorder=self.byte_order.value, signed=False)
        )
        return self

    def write_bytes(self, data: bytes) -> 'ModbusMessageBuilder':
        """
        Записать сырые байты

        Args:
            data: Байты для записи

        Returns:
            self для цепочки вызовов
        """
        if self._finalized:
            raise RuntimeError("Cannot modify finalized message")

        self._buffer.extend(data)
        return self

    def set_function(self, function_code: int) -> 'ModbusMessageBuilder':
        """
        Установить function code (обычно второй байт в Modbus)

        Args:
            function_code: Код функции Modbus (0x01-0x17)

        Returns:
            self для цепочки вызовов
        """
        return self.write_uint8(function_code)

    def get_length(self) -> int:
        """Получить текущую длину сообщения"""
        return len(self._buffer)

    def get_bytes(self) -> bytes:
        """
        Получить сырые байты сообщения (без CRC)

        Returns:
            Байты сообщения
        """
        return bytes(self._buffer)

    def calculate_crc16(self) -> int:
        """
        Рассчитать CRC-16 Modbus для текущего сообщения

        Returns:
            CRC-16 значение
        """
        crc = 0xFFFF

        for byte in self._buffer:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1

        return crc

    def finalize_with_crc(self) -> bytes:
        """
        Завершить сообщение, добавив CRC-16 (Little-Endian как в Modbus RTU)

        Returns:
            Финальное сообщение с CRC
        """
        if self._finalized:
            return self.get_bytes()

        # Рассчитываем CRC
        crc = self.calculate_crc16()

        # CRC в Little-Endian (особенность Modbus RTU)
        self._buffer.extend(crc.to_bytes(2, byteorder='little'))

        self._finalized = True
        return self.get_bytes()

    def validate_response_crc(self, response: bytes) -> bool:
        """
        Проверить CRC ответа от устройства

        Args:
            response: Ответ от устройства (включая CRC)

        Returns:
            True если CRC корректен
        """
        if len(response) < 4:
            return False

        # Отделяем данные и CRC
        data = response[:-2]
        received_crc = int.from_bytes(response[-2:], byteorder='little')

        # Рассчитываем CRC для данных
        temp_builder = ModbusMessageBuilder()
        temp_builder._buffer = bytearray(data)
        calculated_crc = temp_builder.calculate_crc16()

        return received_crc == calculated_crc

    def __repr__(self) -> str:
        """Строковое представление для отладки"""
        hex_str = self._buffer.hex(' ')
        return f"ModbusMessageBuilder(length={len(self._buffer)}, data=[{hex_str}])"


# Вспомогательная функция для быстрого создания
def build_read_holding_registers(
    slave_id: int,
    start_address: int,
    count: int
) -> bytes:
    """
    Быстрое создание запроса Read Holding Registers (Function 0x03)

    Args:
        slave_id: ID устройства
        start_address: Начальный адрес регистра
        count: Количество регистров

    Returns:
        Готовое сообщение с CRC
    """
    return (ModbusMessageBuilder(slave_id=slave_id)
        .set_function(0x03)
        .write_uint16(start_address)
        .write_uint16(count)
        .finalize_with_crc())


def build_write_single_register(
    slave_id: int,
    address: int,
    value: int
) -> bytes:
    """
    Быстрое создание запроса Write Single Register (Function 0x06)

    Args:
        slave_id: ID устройства
        address: Адрес регистра
        value: Значение для записи

    Returns:
        Готовое сообщение с CRC
    """
    return (ModbusMessageBuilder(slave_id=slave_id)
        .set_function(0x06)
        .write_uint16(address)
        .write_uint16(value)
        .finalize_with_crc())
