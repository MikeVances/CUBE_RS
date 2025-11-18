#!/usr/bin/env python3
"""
Тесты для улучшенного Modbus протокола
Тестируем ModbusMessageBuilder и типизированные Request/Response классы
"""

import pytest
from modbus.protocol import (
    ModbusMessageBuilder,
    ByteOrder,
    ReadHoldingRegistersRequest,
    ReadHoldingRegistersResponse,
    WriteSingleRegisterRequest,
    WriteSingleRegisterResponse,
    ModbusExceptionCode,
)


class TestModbusMessageBuilder:
    """Тесты для Fluent Interface builder'а"""

    def test_fluent_interface_chain(self):
        """Тест цепочки вызовов"""
        builder = ModbusMessageBuilder(slave_id=1)

        # Проверяем что методы возвращают self
        result = builder.write_uint8(0x03)
        assert result is builder

        result = builder.write_uint16(0x1000)
        assert result is builder

    def test_build_read_holding_registers(self):
        """Тест построения Read Holding Registers запроса"""
        message = (ModbusMessageBuilder(slave_id=1)
            .set_function(0x03)
            .write_uint16(0x1000)  # start address
            .write_uint16(10)       # count
            .finalize_with_crc())

        # Проверяем структуру сообщения (без CRC)
        assert message[0] == 0x01  # slave_id
        assert message[1] == 0x03  # function code
        assert message[2:4] == b'\x10\x00'  # start address (big-endian)
        assert message[4:6] == b'\x00\x0A'  # count = 10

        # Проверяем длину (6 bytes данных + 2 bytes CRC)
        assert len(message) == 8

    def test_build_write_single_register(self):
        """Тест построения Write Single Register запроса"""
        message = (ModbusMessageBuilder(slave_id=1)
            .set_function(0x06)
            .write_uint16(0x2000)   # address
            .write_uint16(0x1234)   # value
            .finalize_with_crc())

        assert message[0] == 0x01  # slave_id
        assert message[1] == 0x06  # function code
        assert message[2:4] == b'\x20\x00'  # address
        assert message[4:6] == b'\x12\x34'  # value
        assert len(message) == 8

    def test_crc16_calculation(self):
        """Тест расчета CRC-16"""
        builder = ModbusMessageBuilder(slave_id=1)
        builder.write_uint8(0x03)
        builder.write_uint16(0x0000)
        builder.write_uint16(0x0001)

        # Известный CRC для этого сообщения
        crc = builder.calculate_crc16()
        assert isinstance(crc, int)
        assert 0 <= crc <= 0xFFFF

    def test_crc_validation(self):
        """Тест валидации CRC ответа"""
        # Создаем сообщение с известным CRC
        builder = ModbusMessageBuilder(slave_id=1)
        builder.write_uint8(0x03)
        builder.write_uint8(0x04)  # byte count
        builder.write_uint16(0x1234)
        builder.write_uint16(0x5678)

        # Добавляем CRC
        message = builder.finalize_with_crc()

        # Валидация должна пройти
        assert builder.validate_response_crc(message) is True

        # Испорченное сообщение не пройдет валидацию
        corrupted = bytearray(message)
        corrupted[2] = 0xFF  # Портим данные
        assert builder.validate_response_crc(bytes(corrupted)) is False

    def test_cannot_modify_finalized(self):
        """Тест что нельзя изменить финализированное сообщение"""
        builder = ModbusMessageBuilder(slave_id=1)
        builder.finalize_with_crc()

        with pytest.raises(RuntimeError, match="Cannot modify finalized message"):
            builder.write_uint8(0x01)

    def test_byte_order_big_endian(self):
        """Тест Big-Endian порядка байтов"""
        builder = ModbusMessageBuilder(byte_order=ByteOrder.BIG_ENDIAN)
        builder.write_uint16(0x1234)

        data = builder.get_bytes()
        assert data == b'\x12\x34'

    def test_byte_order_little_endian(self):
        """Тест Little-Endian порядка байтов"""
        builder = ModbusMessageBuilder(byte_order=ByteOrder.LITTLE_ENDIAN)
        builder.write_uint16(0x1234)

        data = builder.get_bytes()
        assert data == b'\x34\x12'


class TestReadHoldingRegistersRequest:
    """Тесты для ReadHoldingRegistersRequest"""

    def test_create_request(self):
        """Тест создания запроса"""
        request = ReadHoldingRegistersRequest(
            slave_id=1,
            start_address=0x1000,
            count=10
        )

        assert request.slave_id == 1
        assert request.start_address == 0x1000
        assert request.count == 10
        assert request.get_function_code() == 0x03

    def test_build_message(self):
        """Тест построения сообщения"""
        request = ReadHoldingRegistersRequest(
            slave_id=1,
            start_address=0x1000,
            count=10
        )

        message = request.build()

        # Проверяем структуру
        assert message[0] == 0x01  # slave_id
        assert message[1] == 0x03  # function
        assert message[2:4] == b'\x10\x00'  # address
        assert message[4:6] == b'\x00\x0A'  # count
        assert len(message) == 8  # 6 bytes + 2 CRC

    def test_validation_slave_id(self):
        """Тест валидации slave_id"""
        with pytest.raises(ValueError, match="Invalid slave_id"):
            ReadHoldingRegistersRequest(
                slave_id=300,  # Недопустимое значение
                start_address=0,
                count=1
            )

    def test_validation_count(self):
        """Тест валидации count"""
        with pytest.raises(ValueError, match="Invalid count"):
            ReadHoldingRegistersRequest(
                slave_id=1,
                start_address=0,
                count=200  # Максимум 125
            )

    def test_repr(self):
        """Тест строкового представления"""
        request = ReadHoldingRegistersRequest(
            slave_id=1,
            start_address=0x1000,
            count=10
        )

        repr_str = repr(request)
        assert "ReadHoldingRegistersRequest" in repr_str
        assert "slave_id=1" in repr_str
        assert "0x1000" in repr_str


class TestReadHoldingRegistersResponse:
    """Тесты для ReadHoldingRegistersResponse"""

    def test_parse_successful_response(self):
        """Тест парсинга успешного ответа"""
        # Формат: [Slave][Func][ByteCount][Data...][CRC]
        # Slave=1, Func=3, ByteCount=4, Registers=[0x1234, 0x5678]
        response_data = bytes([
            0x01,  # slave_id
            0x03,  # function
            0x04,  # byte count
            0x12, 0x34,  # register 1
            0x56, 0x78,  # register 2
            0x00, 0x00   # CRC (игнорируем для теста)
        ])

        response = ReadHoldingRegistersResponse.parse(response_data)

        assert response.slave_id == 1
        assert response.function_code == 0x03
        assert response.is_success() is True
        assert len(response.registers) == 2
        assert response.registers[0] == 0x1234
        assert response.registers[1] == 0x5678

    def test_parse_exception_response(self):
        """Тест парсинга ответа с exception"""
        # Формат exception: [Slave][Func|0x80][Exception Code][CRC]
        response_data = bytes([
            0x01,  # slave_id
            0x83,  # function | 0x80 (exception)
            0x02,  # exception code (Illegal Data Address)
            0x00, 0x00  # CRC
        ])

        response = ReadHoldingRegistersResponse.parse(response_data)

        assert response.slave_id == 1
        assert response.is_exception() is True
        assert response.is_success() is False
        assert response.exception_code == 0x02
        assert len(response.registers) == 0

    def test_get_register(self):
        """Тест получения значения регистра по индексу"""
        response = ReadHoldingRegistersResponse(
            slave_id=1,
            function_code=0x03,
            registers=[100, 200, 300]
        )

        assert response.get_register(0) == 100
        assert response.get_register(1) == 200
        assert response.get_register(2) == 300
        assert response.get_register(3) is None  # Нет такого индекса

    def test_to_dict(self):
        """Тест сериализации в dict"""
        response = ReadHoldingRegistersResponse(
            slave_id=1,
            function_code=0x03,
            registers=[100, 200]
        )

        data = response.to_dict()

        assert data['slave_id'] == 1
        assert data['function_code'] == '0x03'
        assert data['registers'] == [100, 200]
        assert data['register_count'] == 2
        assert data['success'] is True


class TestWriteSingleRegisterRequest:
    """Тесты для WriteSingleRegisterRequest"""

    def test_create_request(self):
        """Тест создания запроса"""
        request = WriteSingleRegisterRequest(
            slave_id=1,
            address=0x2000,
            value=0x1234
        )

        assert request.slave_id == 1
        assert request.address == 0x2000
        assert request.value == 0x1234
        assert request.get_function_code() == 0x06

    def test_build_message(self):
        """Тест построения сообщения"""
        request = WriteSingleRegisterRequest(
            slave_id=1,
            address=0x2000,
            value=0x1234
        )

        message = request.build()

        assert message[0] == 0x01  # slave_id
        assert message[1] == 0x06  # function
        assert message[2:4] == b'\x20\x00'  # address
        assert message[4:6] == b'\x12\x34'  # value
        assert len(message) == 8

    def test_validation(self):
        """Тест валидации параметров"""
        with pytest.raises(ValueError, match="Invalid value"):
            WriteSingleRegisterRequest(
                slave_id=1,
                address=0,
                value=0x10000  # Больше 16 бит
            )


class TestWriteSingleRegisterResponse:
    """Тесты для WriteSingleRegisterResponse"""

    def test_parse_successful_response(self):
        """Тест парсинга успешного ответа (echo)"""
        # Формат: [Slave][Func][Addr][Value][CRC]
        response_data = bytes([
            0x01,  # slave_id
            0x06,  # function
            0x20, 0x00,  # address
            0x12, 0x34,  # value
            0x00, 0x00   # CRC
        ])

        response = WriteSingleRegisterResponse.parse(response_data)

        assert response.slave_id == 1
        assert response.function_code == 0x06
        assert response.address == 0x2000
        assert response.value == 0x1234
        assert response.is_success() is True

    def test_parse_exception_response(self):
        """Тест парсинга exception ответа"""
        response_data = bytes([
            0x01,  # slave_id
            0x86,  # function | 0x80
            0x03,  # exception code (Illegal Data Value)
            0x00, 0x00  # CRC
        ])

        response = WriteSingleRegisterResponse.parse(response_data)

        assert response.is_exception() is True
        assert response.is_success() is False
        assert response.exception_code == 0x03


class TestModbusExceptionCode:
    """Тесты для Modbus exception codes"""

    def test_get_description(self):
        """Тест получения описания exception кода"""
        desc = ModbusExceptionCode.get_description(0x01)
        assert "Illegal Function" in desc

        desc = ModbusExceptionCode.get_description(0x02)
        assert "Illegal Data Address" in desc

        desc = ModbusExceptionCode.get_description(0xFF)
        assert "Unknown" in desc


class TestIntegration:
    """Интеграционные тесты Request → Response"""

    def test_read_holding_registers_roundtrip(self):
        """Тест полного цикла Read Holding Registers"""
        # 1. Создаем запрос
        request = ReadHoldingRegistersRequest(
            slave_id=1,
            start_address=0x1000,
            count=2
        )

        # 2. Строим сообщение
        message = request.build()
        assert len(message) == 8

        # 3. Симулируем ответ устройства
        simulated_response = bytes([
            0x01,  # slave_id
            0x03,  # function
            0x04,  # byte count
            0xAA, 0xBB,  # register 1
            0xCC, 0xDD,  # register 2
            0x00, 0x00   # CRC (игнорируем)
        ])

        # 4. Парсим ответ
        response = ReadHoldingRegistersResponse.parse(simulated_response)

        # 5. Проверяем
        assert response.is_success()
        assert len(response.registers) == 2
        assert response.registers[0] == 0xAABB
        assert response.registers[1] == 0xCCDD

    def test_write_single_register_roundtrip(self):
        """Тест полного цикла Write Single Register"""
        # 1. Создаем запрос
        request = WriteSingleRegisterRequest(
            slave_id=1,
            address=0x2000,
            value=0x5555
        )

        # 2. Строим сообщение
        message = request.build()

        # 3. Симулируем echo ответ
        simulated_response = bytes([
            0x01,  # slave_id
            0x06,  # function
            0x20, 0x00,  # address
            0x55, 0x55,  # value
            0x00, 0x00   # CRC
        ])

        # 4. Парсим ответ
        response = WriteSingleRegisterResponse.parse(simulated_response)

        # 5. Проверяем
        assert response.is_success()
        assert response.address == 0x2000
        assert response.value == 0x5555
