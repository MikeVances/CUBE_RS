"""
Тесты протокола RS485
"""

import pytest
import struct
from stienen.rs485_protocol import (
    StienenProtocolCmd, BusState, DataItem, StienenHeader, 
    StienenPacket, RS485Protocol, protocol
)


class TestStienenProtocol:
    """Тесты протокола Stienen"""
    
    def test_protocol_commands(self):
        """Тест команд протокола"""
        assert StienenProtocolCmd.IDENTIFICATION_REQ == 0x02
        assert StienenProtocolCmd.IDENTIFICATION_RSP == 0x03
        assert StienenProtocolCmd.GET_DATA_REQ == 0x08
        assert StienenProtocolCmd.GET_DATA_RSP == 0x09
        assert StienenProtocolCmd.SET_DATA_REQ == 0x0A
        assert StienenProtocolCmd.SET_DATA_RSP == 0x0B
    
    def test_bus_state(self):
        """Тест состояний шины"""
        assert BusState.FREE == 0
        assert BusState.BUSY == 1
        assert BusState.ERROR == 2
        assert BusState.RESERVED == 3
    
    def test_data_item(self):
        """Тест элемента данных"""
        data_item = DataItem(index=100, length=2, value=b'\x01\x02')
        assert data_item.index == 100
        assert data_item.length == 2
        assert data_item.value == b'\x01\x02'


class TestDataItem:
    """Тесты для DataItem"""
    
    def test_data_item_creation(self):
        """Тест создания элемента данных"""
        item = DataItem(index=1000, length=4, value=b'\x00\x00\x00\x64')
        assert item.index == 1000
        assert item.length == 4
        assert len(item.value) == 4
    
    def test_data_item_validation(self):
        """Тест валидации элемента данных"""
        # Корректные данные
        item = DataItem(index=0, length=1, value=b'\x00')
        assert item.index >= 0
        assert item.length > 0
        assert len(item.value) == item.length


class TestRS485Protocol:
    """Тесты для RS485Protocol"""
    
    def setup_method(self):
        """Инициализация перед каждым тестом"""
        self.protocol = RS485Protocol()
    
    def test_constants(self):
        """Тест констант протокола"""
        assert self.protocol.START_BYTE == 0x0D
        assert self.protocol.HEADER_SIZE == 12
        assert self.protocol.CRC_SIZE == 2
        assert self.protocol.ADDRESS_PC485 == 254
        assert self.protocol.ADDRESS_BROADCAST == 255
    
    def test_message_id_increment(self):
        """Тест инкремента ID сообщения"""
        initial_id = self.protocol.get_next_message_id()
        next_id = self.protocol.get_next_message_id()
        assert next_id == (initial_id + 1) % 65536
        
        # Проверяем переполнение - сбрасываем счетчик и проверяем цикл
        self.protocol._message_id = 65534  # Устанавливаем почти максимальное значение
        id1 = self.protocol.get_next_message_id()  # Должно быть 65535
        id2 = self.protocol.get_next_message_id()  # Должно быть 0
        assert id1 == 65535
        assert id2 == 0
    
    def test_build_packet(self):
        """Тест создания пакета"""
        payload = b'\x01\x02\x03'
        packet_data = self.protocol.build_packet(
            dest=1, 
            source=254, 
            cmd=StienenProtocolCmd.IDENTIFICATION_REQ,
            payload=payload
        )
        
        # Проверяем минимальную длину
        assert len(packet_data) >= self.protocol.HEADER_SIZE + len(payload) + self.protocol.CRC_SIZE
        
        # Проверяем стартовый байт
        assert packet_data[0] == self.protocol.START_BYTE
    
    def test_parse_header(self):
        """Тест парсинга заголовка"""
        # Создаем тестовый заголовок
        header_data = struct.pack('>BBBBHBBHH',
            0x0D,  # start_byte
            0,     # bus_state
            1,     # dest
            254,   # source
            3,     # data_len
            2,     # cmd (IDENTIFICATION_REQ)
            1,     # version
            12345, # msg_id
            0x1234 # header_crc
        )
        
        header = self.protocol.parse_header(header_data + b'\x01\x02\x03')
        assert header is not None
        assert header.start_byte == 0x0D
        assert header.bus_state == BusState.FREE
        assert header.dest == 1
        assert header.source == 254
        assert header.data_len == 3
        assert header.cmd == StienenProtocolCmd.IDENTIFICATION_REQ
        assert header.version == 1
        assert header.msg_id == 12345
        assert header.header_crc == 0x1234
        assert header.payload == b'\x01\x02\x03'
    
    def test_parse_header_invalid_start_byte(self):
        """Тест парсинга заголовка с неверным стартовым байтом"""
        header_data = struct.pack('>BBBBHBBHH',
            0x0E,  # неправильный start_byte
            0,     # bus_state
            1,     # dest
            254,   # source
            0,     # data_len
            2,     # cmd
            1,     # version
            12345, # msg_id
            0x1234 # header_crc
        )
        
        header = self.protocol.parse_header(header_data)
        assert header is None
    
    def test_parse_packet(self):
        """Тест парсинга полного пакета"""
        # Создаем пакет
        payload = b'\x01\x02\x03'
        packet_data = self.protocol.build_packet(
            dest=1, 
            source=254, 
            cmd=StienenProtocolCmd.IDENTIFICATION_REQ,
            payload=payload
        )
        
        # Парсим пакет
        packet = self.protocol.parse_packet(packet_data)
        assert packet is not None
        assert packet.header.dest == 1
        assert packet.header.source == 254
        assert packet.header.cmd == StienenProtocolCmd.IDENTIFICATION_REQ
        assert packet.header.payload == payload
    
    def test_verify_crc(self):
        """Тест проверки CRC"""
        # Создаем валидный пакет
        payload = b'\x01\x02\x03'
        packet_data = self.protocol.build_packet(
            dest=1, 
            source=254, 
            cmd=StienenProtocolCmd.IDENTIFICATION_REQ,
            payload=payload
        )
        
        packet = self.protocol.parse_packet(packet_data)
        assert packet is not None
        
        header_crc_ok, data_crc_ok = self.protocol.verify_crc(packet)
        assert header_crc_ok
        assert data_crc_ok
    
    def test_verify_crc_invalid(self):
        """Тест проверки CRC с неверными данными"""
        # Создаем пакет с неправильным CRC
        header_data = struct.pack('>BBBBHBBHH',
            0x0D,  # start_byte
            0,     # bus_state
            1,     # dest
            254,   # source
            3,     # data_len
            2,     # cmd
            1,     # version
            12345, # msg_id
            0xFFFF # неправильный header_crc
        )
        
        payload = b'\x01\x02\x03'
        data_crc = struct.pack('>H', 0xFFFF)  # неправильный data_crc
        
        packet_data = header_data + payload + data_crc
        packet = self.protocol.parse_packet(packet_data)
        assert packet is not None
        
        header_crc_ok, data_crc_ok = self.protocol.verify_crc(packet)
        assert not header_crc_ok
        assert not data_crc_ok
    
    def test_decode_data_payload(self):
        """Тест декодирования payload данных"""
        # Создаем тестовые данные (Little Endian)
        payload = (
            struct.pack('<I', 1000) +  # index
            struct.pack('<H', 4) +     # length
            b'\x00\x00\x00\x64' +     # value
            struct.pack('<I', 2000) +  # index
            struct.pack('<H', 2) +     # length
            b'\x01\x02'               # value
        )
        
        data_items = self.protocol.decode_data_payload(payload)
        assert len(data_items) == 2
        
        assert data_items[0].index == 1000
        assert data_items[0].length == 4
        assert data_items[0].value == b'\x00\x00\x00\x64'
        
        assert data_items[1].index == 2000
        assert data_items[1].length == 2
        assert data_items[1].value == b'\x01\x02'
    
    def test_encode_data_payload(self):
        """Тест кодирования payload данных"""
        data_items = [
            DataItem(index=1000, length=4, value=b'\x00\x00\x00\x64'),
            DataItem(index=2000, length=2, value=b'\x01\x02')
        ]
        
        payload = self.protocol.encode_data_payload(data_items)
        
        # Декодируем обратно для проверки
        decoded_items = self.protocol.decode_data_payload(payload)
        assert len(decoded_items) == 2
        
        assert decoded_items[0].index == 1000
        assert decoded_items[0].value == b'\x00\x00\x00\x64'
        assert decoded_items[1].index == 2000
        assert decoded_items[1].value == b'\x01\x02'
    
    def test_create_identification_request(self):
        """Тест создания запроса идентификации"""
        packet_data = self.protocol.create_identification_request(dest=1)
        packet = self.protocol.parse_packet(packet_data)
        
        assert packet is not None
        assert packet.header.cmd == StienenProtocolCmd.IDENTIFICATION_REQ
        assert packet.header.dest == 1
        assert packet.header.source == self.protocol.ADDRESS_PC485
        assert packet.header.payload == b''
    
    def test_create_get_data_request(self):
        """Тест создания запроса получения данных"""
        data_items = [
            DataItem(index=1000, length=4, value=b'\x00\x00\x00\x64')
        ]
        
        packet_data = self.protocol.create_get_data_request(dest=1, data_items=data_items)
        packet = self.protocol.parse_packet(packet_data)
        
        assert packet is not None
        assert packet.header.cmd == StienenProtocolCmd.GET_DATA_REQ
        assert packet.header.dest == 1
        assert packet.header.source == self.protocol.ADDRESS_PC485
        
        # Проверяем payload
        decoded_items = self.protocol.decode_data_payload(packet.header.payload)
        assert len(decoded_items) == 1
        assert decoded_items[0].index == 1000
    
    def test_create_set_data_request(self):
        """Тест создания запроса установки данных"""
        data_items = [
            DataItem(index=1000, length=4, value=b'\x00\x00\x00\x64')
        ]
        
        packet_data = self.protocol.create_set_data_request(dest=1, data_items=data_items)
        packet = self.protocol.parse_packet(packet_data)
        
        assert packet is not None
        assert packet.header.cmd == StienenProtocolCmd.SET_DATA_REQ
        assert packet.header.dest == 1
        assert packet.header.source == self.protocol.ADDRESS_PC485
    
    def test_get_command_name(self):
        """Тест получения имени команды"""
        assert self.protocol.get_command_name(StienenProtocolCmd.IDENTIFICATION_REQ) == "IDENTIFICATION_REQ"
        assert self.protocol.get_command_name(0x02) == "IDENTIFICATION_REQ"
        assert self.protocol.get_command_name(999) == "Unknown(999)"
    
    def test_is_valid_packet(self):
        """Тест проверки валидности пакета"""
        # Валидный пакет
        packet_data = self.protocol.create_identification_request(dest=1)
        assert self.protocol.is_valid_packet(packet_data)
        
        # Невалидный пакет
        invalid_data = b'\x0D\x00\x01\xFE\x00\x02\x01\x00\x00\x00\x00\x00'
        assert not self.protocol.is_valid_packet(invalid_data)
    
    def test_parse_message_from_buffer(self):
        """Тест поиска сообщений в буфере"""
        # Создаем несколько пакетов
        packet1 = self.protocol.create_identification_request(dest=1)
        packet2 = self.protocol.create_identification_request(dest=2)
        
        # Создаем буфер с мусором и пакетами
        buffer = b'\x00\x01\x02' + packet1 + b'\xFF\xFE' + packet2 + b'\x00\x01'
        
        packets = self.protocol.parse_message_from_buffer(buffer)
        assert len(packets) == 2
        assert packets[0].header.dest == 1
        assert packets[1].header.dest == 2


class TestProtocolFunctions:
    """Тесты удобных функций протокола"""
    
    def test_parse_stienen_packet(self):
        """Тест функции parse_stienen_packet"""
        packet_data = protocol.create_identification_request(dest=1)
        packet = protocol.parse_packet(packet_data)
        assert packet is not None
        assert packet.header.cmd == StienenProtocolCmd.IDENTIFICATION_REQ
    
    def test_verify_packet_crc(self):
        """Тест функции verify_packet_crc"""
        packet_data = protocol.create_identification_request(dest=1)
        packet = protocol.parse_packet(packet_data)
        assert packet is not None
        
        header_crc_ok, data_crc_ok = protocol.verify_crc(packet)
        assert header_crc_ok
        assert data_crc_ok
    
    def test_decode_payload(self):
        """Тест функции decode_payload"""
        data_items = [
            DataItem(index=1000, length=4, value=b'\x00\x00\x00\x64')
        ]
        payload = protocol.encode_data_payload(data_items)
        decoded = protocol.decode_data_payload(payload)
        
        assert len(decoded) == 1
        assert decoded[0].index == 1000
    
    def test_create_packet(self):
        """Тест функции create_packet"""
        payload = b'\x01\x02\x03'
        packet_data = protocol.build_packet(1, 254, StienenProtocolCmd.IDENTIFICATION_REQ, payload)
        packet = protocol.parse_packet(packet_data)
        
        assert packet is not None
        assert packet.header.dest == 1
        assert packet.header.source == 254
        assert packet.header.cmd == StienenProtocolCmd.IDENTIFICATION_REQ
        assert packet.header.payload == payload


if __name__ == "__main__":
    # Запуск тестов из командной строки
    import sys
    import asyncio
    
    async def main():
        print("=== Тест протокола Stienen RS485 ===")
        
        # Тест команд
        print("\n1. Тест команд протокола:")
        print(f"   IDENTIFICATION_REQ = {StienenProtocolCmd.IDENTIFICATION_REQ}")
        print(f"   GET_DATA_REQ = {StienenProtocolCmd.GET_DATA_REQ}")
        print(f"   SET_DATA_REQ = {StienenProtocolCmd.SET_DATA_REQ}")
        
        # Тест состояний
        print("\n2. Тест состояний шины:")
        print(f"   FREE = {BusState.FREE}")
        print(f"   BUSY = {BusState.BUSY}")
        print(f"   ERROR = {BusState.ERROR}")
        
        # Тест элемента данных
        print("\n3. Тест элемента данных:")
        test_item = DataItem(index=100, length=2, value=b'\x01\x02')
        print(f"   Индекс: {test_item.index}")
        print(f"   Длина: {test_item.length}")
        print(f"   Значение: {test_item.value.hex()}")
        
        # Тест создания пакета
        print("\n4. Тест создания пакета:")
        protocol_instance = RS485Protocol()
        packet_data = protocol_instance.create_identification_request(dest=1)
        print(f"   Размер пакета: {len(packet_data)} байт")
        print(f"   Данные пакета: {packet_data.hex()}")
        
        # Тест парсинга пакета
        print("\n5. Тест парсинга пакета:")
        packet = protocol_instance.parse_packet(packet_data)
        if packet:
            header_ok, data_ok = protocol_instance.verify_crc(packet)
            print(f"   CRC заголовка: {'OK' if header_ok else 'FAIL'}")
            print(f"   CRC данных: {'OK' if data_ok else 'FAIL'}")
            print(f"   Команда: {protocol_instance.get_command_name(packet.header.cmd)}")
        
        print("\n=== Тест протокола завершен ===")
    
    asyncio.run(main()) 