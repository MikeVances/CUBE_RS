"""
Интеграционные тесты протокола RS485
Проверяют полный цикл работы протокола с реальными данными
"""

import pytest
import struct
from stienen.rs485_protocol import (
    RS485Protocol, StienenProtocolCmd, BusState, DataItem
)


class TestProtocolIntegration:
    """Интеграционные тесты протокола"""
    
    def setup_method(self):
        """Инициализация перед каждым тестом"""
        self.protocol = RS485Protocol()
    
    def test_full_identification_cycle(self):
        """Полный цикл идентификации устройства"""
        # 1. Создаем запрос идентификации
        request = self.protocol.create_identification_request(dest=1)
        
        # 2. Парсим запрос
        parsed_request = self.protocol.parse_packet(request)
        assert parsed_request is not None
        assert parsed_request.header.cmd == StienenProtocolCmd.IDENTIFICATION_REQ
        assert parsed_request.header.dest == 1
        assert parsed_request.header.source == self.protocol.ADDRESS_PC485
        
        # 3. Проверяем CRC
        header_crc_ok, data_crc_ok = self.protocol.verify_crc(parsed_request)
        assert header_crc_ok
        assert data_crc_ok
        
        # 4. Создаем ответ (имитируем ответ устройства)
        response = self.protocol.build_packet(
            dest=self.protocol.ADDRESS_PC485,
            source=1,
            cmd=StienenProtocolCmd.IDENTIFICATION_RSP,
            payload=b'Device_001'  # Имитируем данные устройства
        )
        
        # 5. Парсим ответ
        parsed_response = self.protocol.parse_packet(response)
        assert parsed_response is not None
        assert parsed_response.header.cmd == StienenProtocolCmd.IDENTIFICATION_RSP
        assert parsed_response.header.dest == self.protocol.ADDRESS_PC485
        assert parsed_response.header.source == 1
        assert parsed_response.header.payload == b'Device_001'
        
        # 6. Проверяем CRC ответа
        header_crc_ok, data_crc_ok = self.protocol.verify_crc(parsed_response)
        assert header_crc_ok
        assert data_crc_ok
    
    def test_full_data_exchange_cycle(self):
        """Полный цикл обмена данными"""
        # 1. Создаем запрос получения данных
        data_items = [
            DataItem(index=1000, length=4, value=b'\x00\x00\x00\x64'),  # 100
            DataItem(index=2000, length=2, value=b'\x01\x02')           # 258
        ]
        
        request = self.protocol.create_get_data_request(dest=1, data_items=data_items)
        
        # 2. Парсим запрос
        parsed_request = self.protocol.parse_packet(request)
        assert parsed_request is not None
        assert parsed_request.header.cmd == StienenProtocolCmd.GET_DATA_REQ
        
        # 3. Декодируем payload запроса
        request_items = self.protocol.decode_data_payload(parsed_request.header.payload)
        assert len(request_items) == 2
        assert request_items[0].index == 1000
        assert request_items[1].index == 2000
        
        # 4. Создаем ответ с данными (имитируем ответ устройства)
        response_items = [
            DataItem(index=1000, length=4, value=b'\x00\x00\x00\xC8'),  # 200
            DataItem(index=2000, length=2, value=b'\x03\x04')           # 772
        ]
        
        response_payload = self.protocol.encode_data_payload(response_items)
        response = self.protocol.build_packet(
            dest=self.protocol.ADDRESS_PC485,
            source=1,
            cmd=StienenProtocolCmd.GET_DATA_RSP,
            payload=response_payload
        )
        
        # 5. Парсим ответ
        parsed_response = self.protocol.parse_packet(response)
        assert parsed_response is not None
        assert parsed_response.header.cmd == StienenProtocolCmd.GET_DATA_RSP
        
        # 6. Декодируем payload ответа
        response_items_decoded = self.protocol.decode_data_payload(parsed_response.header.payload)
        assert len(response_items_decoded) == 2
        assert response_items_decoded[0].index == 1000
        assert response_items_decoded[0].value == b'\x00\x00\x00\xC8'
        assert response_items_decoded[1].index == 2000
        assert response_items_decoded[1].value == b'\x03\x04'
    
    def test_set_data_cycle(self):
        """Цикл установки данных"""
        # 1. Создаем запрос установки данных
        set_items = [
            DataItem(index=1000, length=4, value=b'\x00\x00\x00\xFF'),  # 255
            DataItem(index=2000, length=2, value=b'\xFF\xFF')           # 65535
        ]
        
        request = self.protocol.create_set_data_request(dest=1, data_items=set_items)
        
        # 2. Парсим запрос
        parsed_request = self.protocol.parse_packet(request)
        assert parsed_request is not None
        assert parsed_request.header.cmd == StienenProtocolCmd.SET_DATA_REQ
        
        # 3. Декодируем payload
        request_items = self.protocol.decode_data_payload(parsed_request.header.payload)
        assert len(request_items) == 2
        assert request_items[0].index == 1000
        assert request_items[0].value == b'\x00\x00\x00\xFF'
        assert request_items[1].index == 2000
        assert request_items[1].value == b'\xFF\xFF'
        
        # 4. Создаем подтверждение (имитируем ответ устройства)
        ack_response = self.protocol.build_packet(
            dest=self.protocol.ADDRESS_PC485,
            source=1,
            cmd=StienenProtocolCmd.SET_DATA_RSP,
            payload=b''  # Пустой payload для подтверждения
        )
        
        # 5. Парсим подтверждение
        parsed_ack = self.protocol.parse_packet(ack_response)
        assert parsed_ack is not None
        assert parsed_ack.header.cmd == StienenProtocolCmd.SET_DATA_RSP
        assert parsed_ack.header.payload == b''
    
    def test_buffer_parsing_with_multiple_packets(self):
        """Тест парсинга буфера с несколькими пакетами"""
        # Создаем несколько пакетов
        packet1 = self.protocol.create_identification_request(dest=1)
        packet2 = self.protocol.create_get_data_request(dest=2, data_items=[
            DataItem(index=1000, length=4, value=b'\x00\x00\x00\x01')
        ])
        packet3 = self.protocol.create_set_data_request(dest=3, data_items=[
            DataItem(index=2000, length=2, value=b'\x01\x02')
        ])
        
        # Создаем буфер с мусором и пакетами
        buffer = (
            b'\x00\x01\x02\x03' +  # Мусор в начале
            packet1 +               # Первый пакет
            b'\xFF\xFE\xFD' +      # Мусор между пакетами
            packet2 +               # Второй пакет
            b'\xAA\xBB' +          # Мусор между пакетами
            packet3 +               # Третий пакет
            b'\xCC\xDD\xEE'        # Мусор в конце
        )
        
        # Парсим все пакеты из буфера
        packets = self.protocol.parse_message_from_buffer(buffer)
        
        assert len(packets) == 3
        
        # Проверяем первый пакет (идентификация)
        assert packets[0].header.cmd == StienenProtocolCmd.IDENTIFICATION_REQ
        assert packets[0].header.dest == 1
        
        # Проверяем второй пакет (получение данных)
        assert packets[1].header.cmd == StienenProtocolCmd.GET_DATA_REQ
        assert packets[1].header.dest == 2
        
        # Проверяем третий пакет (установка данных)
        assert packets[2].header.cmd == StienenProtocolCmd.SET_DATA_REQ
        assert packets[2].header.dest == 3
        
        # Проверяем CRC всех пакетов
        for packet in packets:
            header_crc_ok, data_crc_ok = self.protocol.verify_crc(packet)
            assert header_crc_ok
            assert data_crc_ok
    
    def test_error_handling(self):
        """Тест обработки ошибок"""
        # 1. Тест с неполными данными
        incomplete_data = b'\x0D\x00\x01\xFE\x00\x02\x01'
        packet = self.protocol.parse_packet(incomplete_data)
        assert packet is None
        
        # 2. Тест с неправильным стартовым байтом
        wrong_start = b'\x0E\x00\x01\xFE\x00\x02\x01\x01\x00\x00\x00\x00'
        packet = self.protocol.parse_packet(wrong_start)
        assert packet is None
        
        # 3. Тест с неправильным CRC - создаем валидный пакет и портим CRC
        valid_packet = self.protocol.create_identification_request(dest=1)
        # Порт CRC заголовка (последние 2 байта заголовка)
        invalid_packet = valid_packet[:-4] + b'\xFF\xFF' + valid_packet[-2:]
        packet = self.protocol.parse_packet(invalid_packet)
        assert packet is not None
        header_crc_ok, data_crc_ok = self.protocol.verify_crc(packet)
        assert not header_crc_ok
    
    def test_data_types_encoding_decoding(self):
        """Тест кодирования/декодирования различных типов данных"""
        # Тестируем различные типы данных
        test_cases = [
            (1000, b'\x00\x00\x00\x64'),      # 100
            (2000, b'\x00\x00\x00\xC8'),      # 200
            (3000, b'\x00\x00\x00\x01'),      # 1
            (4000, b'\xFF\xFF\xFF\xFF'),      # -1 (как unsigned)
            (5000, b'\x01\x02\x03\x04'),      # Произвольные данные
        ]
        
        data_items = [
            DataItem(index=index, length=len(value), value=value)
            for index, value in test_cases
        ]
        
        # Кодируем
        payload = self.protocol.encode_data_payload(data_items)
        
        # Декодируем
        decoded_items = self.protocol.decode_data_payload(payload)
        
        # Проверяем
        assert len(decoded_items) == len(test_cases)
        
        for i, (expected_index, expected_value) in enumerate(test_cases):
            assert decoded_items[i].index == expected_index
            assert decoded_items[i].value == expected_value
            assert decoded_items[i].length == len(expected_value)
    
    def test_message_id_uniqueness(self):
        """Тест уникальности ID сообщений"""
        ids = set()
        
        # Генерируем много ID и проверяем уникальность
        for _ in range(1000):
            msg_id = self.protocol.get_next_message_id()
            assert msg_id not in ids
            ids.add(msg_id)
        
        # Проверяем, что все ID в правильном диапазоне
        assert all(0 <= msg_id < 65536 for msg_id in ids)
    
    def test_protocol_constants_consistency(self):
        """Тест консистентности констант протокола"""
        # Проверяем, что константы соответствуют спецификации
        assert self.protocol.START_BYTE == 0x0D
        assert self.protocol.HEADER_SIZE == 12
        assert self.protocol.CRC_SIZE == 2
        
        # Проверяем адреса
        assert self.protocol.ADDRESS_PC485 == 254
        assert self.protocol.ADDRESS_BROADCAST == 255
        
        # Проверяем, что размер заголовка соответствует структуре
        # Start(1) + BusState(1) + Dest(1) + Src(1) + DataLen(2) + 
        # Cmd(1) + Version(1) + MsgId(2) + HeaderCRC(2) = 12 байт
        expected_header_size = 1 + 1 + 1 + 1 + 2 + 1 + 1 + 2 + 2
        assert self.protocol.HEADER_SIZE == expected_header_size


if __name__ == "__main__":
    # Запуск интеграционных тестов
    import asyncio
    
    async def main():
        print("=== Интеграционные тесты протокола Stienen RS485 ===")
        
        protocol = RS485Protocol()
        
        print("\n1. Тест полного цикла идентификации:")
        request = protocol.create_identification_request(dest=1)
        parsed = protocol.parse_packet(request)
        if parsed:
            header_ok, data_ok = protocol.verify_crc(parsed)
            print(f"   Запрос создан: {len(request)} байт")
            print(f"   CRC заголовка: {'OK' if header_ok else 'FAIL'}")
            print(f"   CRC данных: {'OK' if data_ok else 'FAIL'}")
        
        print("\n2. Тест обмена данными:")
        data_items = [DataItem(index=1000, length=4, value=b'\x00\x00\x00\x64')]
        request = protocol.create_get_data_request(dest=1, data_items=data_items)
        parsed = protocol.parse_packet(request)
        if parsed:
            decoded_items = protocol.decode_data_payload(parsed.header.payload)
            print(f"   Запрос данных: {len(decoded_items)} элементов")
            if decoded_items:
                print(f"   Первый элемент: индекс={decoded_items[0].index}")
        
        print("\n3. Тест парсинга буфера:")
        packet1 = protocol.create_identification_request(dest=1)
        packet2 = protocol.create_identification_request(dest=2)
        buffer = b'\x00\x01' + packet1 + b'\xFF\xFE' + packet2 + b'\x00\x01'
        packets = protocol.parse_message_from_buffer(buffer)
        print(f"   Найдено пакетов в буфере: {len(packets)}")
        
        print("\n=== Интеграционные тесты завершены ===")
    
    asyncio.run(main()) 