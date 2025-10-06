#!/usr/bin/env python3
"""
Comprehensive Test Suite for Stienen RS485 Gateway
Комплексный набор тестов для гейтвея Stienen RS485
Проверяет корректность миграции с C# на Python
"""

import pytest
import asyncio
import struct
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock

# Импорты тестируемых модулей
from stienen.rs485_protocol import (
    RS485Protocol, StienenHeader, StienenPacket, DataItem,
    BusState, StienenProtocolCmd
)
from stienen.rs485_communication import RS485Communication
from stienen.variable_mapping import VariableMapper, FE_Type, FE_Reference, VariableType
from stienen.gateway_backend import StienenGatewayBackend, GatewayConfig

class TestRS485Protocol:
    """Тесты протокола RS485"""
    
    def setup_method(self):
        """Инициализация для каждого теста"""
        self.protocol = RS485Protocol()
    
    def test_protocol_constants(self):
        """Тест основных констант протокола"""
        assert self.protocol.START_BYTE == 0x0D
        assert self.protocol.HEADER_SIZE == 12
        assert self.protocol.ADDRESS_PC485 == 254
        assert self.protocol.ADDRESS_BROADCAST == 255
    
    def test_create_identification_packet(self):
        """Тест создания пакета идентификации"""
        packet_data = self.protocol.create_identification_request(dest=1)
        
        # Проверяем структуру пакета
        assert len(packet_data) >= 14  # 12 байт заголовок + 2 байта CRC данных
        assert packet_data[0] == 0x0D  # Стартовый байт
        assert packet_data[2] == 1     # Адрес назначения
        assert packet_data[3] == 254   # Адрес источника (PC485)
        assert packet_data[6] == StienenProtocolCmd.IDENTIFICATION_REQ  # Команда
    
    def test_parse_identification_packet(self):
        """Тест парсинга пакета идентификации"""
        # Создаем пакет
        packet_data = self.protocol.create_identification_request(dest=1)
        
        # Парсим обратно
        parsed = self.protocol.parse_packet(packet_data)
        
        assert parsed is not None
        assert parsed.header.start_byte == 0x0D
        assert parsed.header.dest == 1
        assert parsed.header.source == 254
        assert parsed.header.cmd == StienenProtocolCmd.IDENTIFICATION_REQ
        assert parsed.header.data_len == 0  # Нет payload
    
    def test_crc_verification(self):
        """Тест проверки CRC"""
        packet_data = self.protocol.create_identification_request(dest=1)
        parsed = self.protocol.parse_packet(packet_data)
        
        assert parsed is not None
        header_ok, data_ok = self.protocol.verify_crc(parsed)
        
        assert header_ok == True
        assert data_ok == True
    
    def test_data_payload_encoding_decoding(self):
        """Тест кодирования/декодирования payload данных"""
        # Создаем тестовые данные
        original_items = [
            DataItem(index=100, length=2, value=b'\x19\x01'),  # Температура
            DataItem(index=200, length=1, value=b'\x01'),      # Булево
            DataItem(index=300, length=4, value=b'\x39\x30\x00\x00'),  # Счетчик
        ]
        
        # Кодируем
        encoded_payload = self.protocol.encode_data_payload(original_items)
        
        # Декодируем
        decoded_items = self.protocol.decode_data_payload(encoded_payload)
        
        # Проверяем
        assert len(decoded_items) == len(original_items)
        
        for orig, decoded in zip(original_items, decoded_items):
            assert orig.index == decoded.index
            assert orig.length == decoded.length  
            assert orig.value == decoded.value
    
    def test_packet_with_data(self):
        """Тест создания и парсинга пакета с данными"""
        data_items = [
            DataItem(index=100, length=2, value=b'\x19\x01'),
        ]
        
        packet_data = self.protocol.create_get_data_request(dest=1, data_items=data_items)
        parsed = self.protocol.parse_packet(packet_data)
        
        assert parsed is not None
        assert parsed.header.cmd == StienenProtocolCmd.GET_DATA_REQ
        assert parsed.header.data_len > 0
        
        # Проверяем CRC
        header_ok, data_ok = self.protocol.verify_crc(parsed)
        assert header_ok and data_ok
        
        # Декодируем данные
        decoded_items = self.protocol.decode_data_payload(parsed.header.payload)
        assert len(decoded_items) == 1
        assert decoded_items[0].index == 100
        assert decoded_items[0].value == b'\x19\x01'
    
    def test_message_buffer_parsing(self):
        """Тест поиска сообщений в буфере"""
        # Создаем несколько пакетов
        packet1 = self.protocol.create_identification_request(dest=1)
        packet2 = self.protocol.create_identification_request(dest=2)
        
        # Создаем буфер с мусором
        test_buffer = b'\x00\x11\x22' + packet1 + b'\x33\x44' + packet2 + b'\x55'
        
        # Ищем пакеты
        found_packets = self.protocol.parse_message_from_buffer(test_buffer)
        
        assert len(found_packets) == 2
        assert found_packets[0].header.dest == 1
        assert found_packets[1].header.dest == 2
    
    def test_invalid_packets(self):
        """Тест обработки неверных пакетов"""
        # Неверный стартовый байт
        invalid_start = b'\xFF' + b'\x00' * 15
        assert self.protocol.parse_packet(invalid_start) is None
        
        # Слишком короткий пакет
        too_short = b'\x0D' + b'\x00' * 5
        assert self.protocol.parse_packet(too_short) is None
        
        # Неверное состояние шины
        invalid_bus_state = b'\x0D\x05' + b'\x00' * 12  # bus_state = 5 (должно быть < 4)
        assert self.protocol.parse_packet(invalid_bus_state) is None

class TestVariableMapping:
    """Тесты маппинга переменных"""
    
    def setup_method(self):
        """Инициализация для каждого теста"""
        self.mapper = VariableMapper()
        
        # Тестовые типы
        self.test_types = [
            FE_Type(
                hardware=1001, version=1, id=1, name="Temperature",
                type=VariableType.SHORT, mul=1, div=10, step=0.1,
                min_val=-500, max_val=1000
            ),
            FE_Type(
                hardware=1001, version=1, id=2, name="Boolean", 
                type=VariableType.BOOL, mul=1, div=1, step=1,
                min_val=0, max_val=1
            )
        ]
        
        # Тестовые ссылки
        self.test_references = [
            FE_Reference(
                hardware=1001, version=1, id=1, index=100, length=2,
                name="AirTemperature", type_id=1
            ),
            FE_Reference(
                hardware=1001, version=1, id=2, index=200, length=1,
                name="FanEnabled", type_id=2
            )
        ]
        
        # Регистрируем в мапере
        for fe_type in self.test_types:
            self.mapper.register_type(fe_type)
        for fe_ref in self.test_references:
            self.mapper.register_reference(fe_ref)
    
    def test_temperature_conversion(self):
        """Тест конвертации температуры"""
        # Сырые данные: 281 = 28.1°C (с делителем 10)
        raw_data = struct.pack('<h', 281)
        temp_type = self.test_types[0]  # Temperature
        
        converted = self.mapper.convert_raw_to_value(raw_data, temp_type)
        assert converted == 28.1
        
        # Обратная конвертация
        back_to_raw = self.mapper.convert_value_to_raw(28.1, temp_type)
        assert back_to_raw == raw_data
    
    def test_boolean_conversion(self):
        """Тест конвертации булевых значений"""
        bool_type = self.test_types[1]  # Boolean
        
        # True
        raw_true = b'\x01'
        converted_true = self.mapper.convert_raw_to_value(raw_true, bool_type)
        assert converted_true == True
        
        # False
        raw_false = b'\x00'
        converted_false = self.mapper.convert_raw_to_value(raw_false, bool_type)
        assert converted_false == False
        
        # Обратная конвертация
        assert self.mapper.convert_value_to_raw(True, bool_type) == raw_true
        assert self.mapper.convert_value_to_raw(False, bool_type) == raw_false
    
    def test_data_items_mapping(self):
        """Тест маппинга DataItem в переменные"""
        data_items = [
            DataItem(index=100, length=2, value=struct.pack('<h', 251)),  # 25.1°C
            DataItem(index=200, length=1, value=b'\x01'),                 # True
        ]
        
        variables = self.mapper.map_data_to_variables(
            device_id="test_device", 
            hardware=1001, 
            version=1, 
            data_items=data_items
        )
        
        assert len(variables) == 2
        
        # Проверяем температуру
        temp_var = variables[0]
        assert temp_var.index == 100
        assert temp_var.converted_value == 25.1
        
        # Проверяем булево
        bool_var = variables[1]
        assert bool_var.index == 200
        assert bool_var.converted_value == True
    
    def test_variable_validation(self):
        """Тест валидации значений переменных"""
        temp_type = self.test_types[0]  # Temperature (-50.0 to 100.0)
        bool_type = self.test_types[1]  # Boolean
        
        # Валидные значения
        assert self.mapper.validate_variable_value(25.5, temp_type) == True
        assert self.mapper.validate_variable_value(True, bool_type) == True
        assert self.mapper.validate_variable_value(False, bool_type) == True
        
        # Неверные значения
        assert self.mapper.validate_variable_value(150.0, temp_type) == False  # Вне диапазона
        assert self.mapper.validate_variable_value("not_bool", bool_type) == False  # Неверный тип

class TestRS485Communication:
    """Тесты RS485 коммуникации"""
    
    def setup_method(self):
        """Инициализация для каждого теста"""
        self.comm = RS485Communication('/dev/null')  # Фиктивный порт для тестов
    
    @patch('serial.Serial')
    def test_initialization(self, mock_serial):
        """Тест инициализации коммуникации"""
        mock_serial_instance = Mock()
        mock_serial_instance.is_open = True
        mock_serial.return_value = mock_serial_instance
        
        result = self.comm.initialize()
        assert result == True
        assert self.comm.active == True
        
        # Проверяем вызов Serial
        mock_serial.assert_called_once()
        call_args = mock_serial.call_args
        assert call_args[1]['port'] == '/dev/null'
        assert call_args[1]['baudrate'] == 38400
    
    def test_message_queue_priority(self):
        """Тест приоритезации сообщений в очереди"""
        from stienen.rs485_communication import SendMessageQueueItem
        
        # Создаем элементы с разными приоритетами
        item1 = SendMessageQueueItem(b'packet1', priority=1)
        item2 = SendMessageQueueItem(b'packet2', priority=0)  # Высший приоритет
        item3 = SendMessageQueueItem(b'packet3', priority=2)
        
        # Добавляем в очередь
        self.comm.send_queue = []
        self.comm._add_message_to_queue(item1)
        self.comm._add_message_to_queue(item2)
        self.comm._add_message_to_queue(item3)
        
        # Проверяем порядок (должен быть по приоритету: 0, 1, 2)
        assert self.comm.send_queue[0].priority == 0
        assert self.comm.send_queue[1].priority == 1  
        assert self.comm.send_queue[2].priority == 2

class TestGatewayBackend:
    """Тесты основного бэкенда гейтвея"""
    
    def setup_method(self):
        """Инициализация для каждого теста"""
        self.config = GatewayConfig(
            name="TestGateway",
            rs485_port="/dev/null",
            polling_interval=1.0
        )
        self.gateway = StienenGatewayBackend(self.config)
    
    @pytest.mark.asyncio
    @patch('stienen.rs485_communication.RS485Communication.initialize')
    async def test_gateway_initialization(self, mock_init):
        """Тест инициализации гейтвея"""
        mock_init.return_value = True
        
        result = await self.gateway.initialize()
        assert result == True
        assert self.gateway.active == True
        
        # Проверяем, что созданы нужные объекты
        assert self.gateway.rs485_comm is not None
        assert self.gateway.variable_mapper is not None
        assert self.gateway.scada_manager is not None
    
    @pytest.mark.asyncio
    async def test_add_device(self):
        """Тест добавления устройства"""
        # Мокаем RS485 коммуникацию
        self.gateway.rs485_comm = Mock()
        
        await self.gateway.add_device(address=1, name="TestDevice")
        
        # Проверяем, что устройство добавлено
        assert 1 in self.gateway.devices
        device = self.gateway.devices[1]
        assert device.name == "TestDevice"
        assert device.address == 1
        assert device.active == True
        
        # Проверяем, что создан менеджер переменных
        assert device.device_id in self.gateway.device_managers
    
    @pytest.mark.asyncio 
    @patch('stienen.rs485_communication.RS485Communication.send_message')
    async def test_set_device_variable(self, mock_send):
        """Тест установки переменной устройства"""
        mock_send.return_value = 123  # message_id
        
        # Добавляем устройство
        await self.gateway.add_device(address=1, name="TestDevice")
        
        # Настраиваем маппер переменных
        self._setup_test_variables()
        
        # Устанавливаем переменную
        result = await self.gateway.set_device_variable(1, "AirTemperature", 25.5)
        
        assert result == True
        mock_send.assert_called_once()
        
        # Проверяем аргументы вызова
        call_args = mock_send.call_args
        assert call_args[1]['dest'] == 1
        assert call_args[1]['cmd'] == StienenProtocolCmd.SET_DATA_REQ
    
    def _setup_test_variables(self):
        """Настройка тестовых переменных"""
        # Добавляем тестовые типы и ссылки
        temp_type = FE_Type(
            hardware=1001, version=1, id=1, name="Temperature",
            type=VariableType.SHORT, mul=1, div=10, step=0.1,
            min_val=-500, max_val=1000
        )
        
        temp_ref = FE_Reference(
            hardware=1001, version=1, id=1, index=100, length=2,
            name="AirTemperature", type_id=1
        )
        
        self.gateway.variable_mapper.register_type(temp_type)
        self.gateway.variable_mapper.register_reference(temp_ref)

class TestScadaIntegration:
    """Тесты SCADA интеграции"""
    
    @pytest.mark.asyncio
    async def test_xml_export(self):
        """Тест XML экспорта"""
        from stienen.scada_integration import XmlScadaExporter, ScadaDataPoint
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as tmp:
            exporter = XmlScadaExporter(tmp.name)
            
            test_data = [
                ScadaDataPoint("device1", "temperature", 25.5, datetime.now()),
                ScadaDataPoint("device1", "humidity", 60.2, datetime.now()),
            ]
            
            result = await exporter.export_values(test_data)
            assert result == True
            
            # Проверяем, что файл создан и содержит данные
            import xml.etree.ElementTree as ET
            tree = ET.parse(tmp.name)
            root = tree.getroot()
            
            assert root.tag == 'StienenData'
            devices = root.findall('Device')
            assert len(devices) == 1
            assert devices[0].get('id') == 'device1'
            
            variables = devices[0].findall('.//Variable')
            assert len(variables) == 2
    
    @pytest.mark.asyncio
    async def test_csv_export(self):
        """Тест CSV экспорта"""
        from stienen.scada_integration import CsvScadaExporter, ScadaDataPoint
        import tempfile
        import csv
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp:
            exporter = CsvScadaExporter(tmp.name)
            
            test_data = [
                ScadaDataPoint("device1", "temperature", 25.5, datetime.now()),
                ScadaDataPoint("device2", "pressure", 1013.25, datetime.now()),
            ]
            
            result = await exporter.export_values(test_data)
            assert result == True
            
            # Проверяем содержимое CSV
            with open(tmp.name, 'r') as csvfile:
                reader = csv.DictReader(csvfile)
                rows = list(reader)
                
                assert len(rows) == 2
                assert rows[0]['device_id'] == 'device1'
                assert rows[0]['variable_name'] == 'temperature'
                assert float(rows[0]['value']) == 25.5

class TestEndToEndScenarios:
    """Комплексные сценарии тестирования"""
    
    @pytest.mark.asyncio
    async def test_device_communication_flow(self):
        """Тест полного цикла коммуникации с устройством"""
        # Мокаем RS485 коммуникацию
        with patch('stienen.rs485_communication.RS485Communication') as MockComm:
            mock_comm_instance = Mock()
            mock_comm_instance.initialize.return_value = True
            mock_comm_instance.is_connected.return_value = True
            mock_comm_instance.send_message.return_value = 123
            MockComm.return_value = mock_comm_instance
            
            # Создаем гейтвей
            config = GatewayConfig(name="TestGateway", rs485_port="/dev/null")
            gateway = StienenGatewayBackend(config)
            
            # Инициализируем
            result = await gateway.initialize()
            assert result == True
            
            # Добавляем устройство
            await gateway.add_device(address=1, name="TestDevice")
            
            # Проверяем, что устройство добавлено
            assert 1 in gateway.devices
            device = gateway.devices[1]
            assert device.name == "TestDevice"
            
            # Проверяем вызовы коммуникации
            mock_comm_instance.send_message.assert_called()
    
    @pytest.mark.asyncio
    async def test_data_flow_through_system(self):
        """Тест прохождения данных через всю систему"""
        # Создаем тестовый пакет ответа с данными
        protocol = RS485Protocol()
        
        # Создаем данные температуры 25.1°C
        temp_data = struct.pack('<h', 251)  # 25.1 с делителем 10
        data_items = [DataItem(index=100, length=2, value=temp_data)]
        
        response_packet = protocol.build_packet(
            dest=254,  # PC485
            source=1,  # Устройство 1
            cmd=StienenProtocolCmd.GET_DATA_RSP,
            payload=protocol.encode_data_payload(data_items)
        )
        
        # Проверяем, что пакет валиден
        parsed = protocol.parse_packet(response_packet)
        assert parsed is not None
        assert protocol.is_valid_packet(response_packet)
        
        # Декодируем данные
        decoded_items = protocol.decode_data_payload(parsed.header.payload)
        assert len(decoded_items) == 1
        assert decoded_items[0].index == 100
        assert decoded_items[0].value == temp_data

class TestRealWorldScenarios:
    """Тесты реальных сценариев использования"""
    
    @pytest.mark.asyncio
    async def test_multiple_devices_polling(self):
        """Тест опроса нескольких устройств"""
        config = GatewayConfig(name="TestGateway", rs485_port="/dev/null", polling_interval=0.1)
        gateway = StienenGatewayBackend(config)
        
        # Мокаем коммуникацию
        with patch.object(gateway, 'rs485_comm') as mock_comm:
            mock_comm.initialize.return_value = True
            mock_comm.is_connected.return_value = True
            mock_comm.send_message.return_value = 123
            
            await gateway.initialize()
            
            # Добавляем несколько устройств
            await gateway.add_device(1, "Device1")
            await gateway.add_device(2, "Device2")
            await gateway.add_device(3, "Device3")
            
            assert len(gateway.devices) == 3
            
            # Проверяем, что все устройства в очереди опроса
            assert len(gateway.polling_queue) == 3
    
    def test_error_handling(self):
        """Тест обработки ошибок"""
        protocol = RS485Protocol()
        
        # Тест с поврежденными данными
        corrupted_data = b'\x0D\x00\x01\xFE\x00\x04\x02\x01\x00\x7B\xFF\xFF\x11\x22\x33\x44'
        
        packet = protocol.parse_packet(corrupted_data)
        if packet:
            header_ok, data_ok = protocol.verify_crc(packet)
            # Ожидаем, что CRC не пройдет проверку
            assert not (header_ok and data_ok)
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Тест обработки таймаутов"""
        from stienen.rs485_communication import SendMessageQueueItem
        import time
        
        comm = RS485Communication('/dev/null')
        
        # Создаем элемент с истекшим таймаутом
        old_item = SendMessageQueueItem(
            packet_data=b'\x0D\x00\x01\xFE\x00\x00\x02\x01\x00\x7B\x12\x34\x56\x78',
            created_at=time.time() - 10.0  # 10 секунд назад
        )
        
        comm.send_queue = [old_item]
        
        # Мокаем timeout callback
        timeout_callback = Mock()
        
        # Симулируем обработку таймаута
        await comm._handle_timeout(123, old_item, Mock(callback=timeout_callback, timeout_seconds=5.0))
        
        # Проверяем, что повторная попытка была выполнена
        assert old_item.retries == 1

# Benchmark тесты для производительности

class TestPerformance:
    """Тесты производительности"""
    
    def test_protocol_parsing_speed(self):
        """Тест скорости парсинга протокола"""
        protocol = RS485Protocol()
        
        # Создаем тестовый пакет
        packet_data = protocol.create_identification_request(dest=1)
        
        import time
        start_time = time.time()
        
        # Парсим 1000 раз
        for _ in range(1000):
            parsed = protocol.parse_packet(packet_data)
            assert parsed is not None
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        # Должно быть быстрее 1 секунды
        assert elapsed < 1.0
        print(f"Парсинг 1000 пакетов: {elapsed:.3f} сек ({1000/elapsed:.0f} пакетов/сек)")
    
    def test_crc_calculation_speed(self):
        """Тест скорости расчета CRC"""
        protocol = RS485Protocol()
        
        # Тестовые данные
        test_data = b'\x0D\x00\x01\xFE\x00\x00\x02\x01'
        
        import time
        start_time = time.time()
        
        # Считаем CRC 10000 раз
        for _ in range(10000):
            crc = protocol.crc16(test_data)
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        # Должно быть быстрее 1 секунды
        assert elapsed < 1.0
        print(f"Расчет 10000 CRC: {elapsed:.3f} сек ({10000/elapsed:.0f} CRC/сек)")

# Утилиты для тестирования

class MockStienenDevice:
    """Мок устройства Stienen для тестирования"""
    
    def __init__(self, address: int, hardware: int = 1001, version: int = 1):
        self.address = address
        self.hardware = hardware
        self.version = version
        self.protocol = RS485Protocol()
        
        # Симулируемые переменные
        self.variables = {
            100: b'\x19\x01',  # Температура 28.1°C
            200: b'\x01',      # Вентилятор включен
            300: b'\x39\x30\x00\x00',  # Счетчик 12345
        }
    
    def handle_identification_request(self, packet: StienenPacket) -> bytes:
        """Обработка запроса идентификации"""
        # Создаем ответ идентификации
        return self.protocol.build_packet(
            dest=packet.header.source,
            source=self.address,
            cmd=StienenProtocolCmd.IDENTIFICATION_RSP,
            msg_id=packet.header.msg_id
        )
    
    def handle_get_data_request(self, packet: StienenPacket) -> bytes:
        """Обработка запроса получения данных"""
        # Парсим запрошенные переменные
        requested_items = self.protocol.decode_data_payload(packet.header.payload)
        
        # Формируем ответ
        response_items = []
        for item in requested_items:
            if item.index in self.variables:
                response_items.append(DataItem(
                    index=item.index,
                    length=len(self.variables[item.index]),
                    value=self.variables[item.index]
                ))
        
        response_payload = self.protocol.encode_data_payload(response_items)
        
        return self.protocol.build_packet(
            dest=packet.header.source,
            source=self.address,
            cmd=StienenProtocolCmd.GET_DATA_RSP,
            payload=response_payload,
            msg_id=packet.header.msg_id
        )

# Интеграционные тесты

class TestIntegration:
    """Интеграционные тесты"""
    
    @pytest.mark.asyncio
    async def test_full_communication_cycle(self):
        """Тест полного цикла коммуникации"""
        # Создаем мок устройство
        mock_device = MockStienenDevice(address=1)
        
        # Создаем запрос идентификации
        protocol = RS485Protocol()
        id_request = protocol.create_identification_request(dest=1)
        
        # Устройство обрабатывает запрос
        parsed_request = protocol.parse_packet(id_request)
        assert parsed_request is not None
        
        id_response = mock_device.handle_identification_request(parsed_request)
        
        # Проверяем ответ
        parsed_response = protocol.parse_packet(id_response)
        assert parsed_response is not None
        assert parsed_response.header.cmd == StienenProtocolCmd.IDENTIFICATION_RSP
        assert parsed_response.header.source == 1
    
    @pytest.mark.asyncio
    async def test_data_exchange_cycle(self):
        """Тест цикла обмена данными"""
        mock_device = MockStienenDevice(address=1)
        protocol = RS485Protocol()
        
        # Запрос данных
        data_items = [
            DataItem(index=100, length=2, value=b''),  # Запрос температуры
            DataItem(index=200, length=1, value=b''),  # Запрос состояния вентилятора
        ]
        
        data_request = protocol.create_get_data_request(dest=1, data_items=data_items)
        parsed_request = protocol.parse_packet(data_request)
        
        # Устройство отвечает
        data_response = mock_device.handle_get_data_request(parsed_request)
        parsed_response = protocol.parse_packet(data_response)
        
        # Проверяем ответ
        assert parsed_response is not None
        assert parsed_response.header.cmd == StienenProtocolCmd.GET_DATA_RSP
        
        # Декодируем полученные данные
        received_items = protocol.decode_data_payload(parsed_response.header.payload)
        assert len(received_items) == 2
        
        # Проверяем температуру
        temp_item = next(item for item in received_items if item.index == 100)
        assert temp_item.value == b'\x19\x01'  # 28.1°C
        
        # Проверяем вентилятор
        fan_item = next(item for item in received_items if item.index == 200)
        assert fan_item.value == b'\x01'  # Включен

# Запуск всех тестов
if __name__ == "__main__":
    import sys
    
    # Настройка логирования для тестов
    logging.basicConfig(level=logging.DEBUG)
    
    # Запуск pytest
    exit_code = pytest.main([
        __file__,
        "-v",           # Подробный вывод
        "--tb=short",   # Короткие traceback
        "--durations=10" # Топ 10 самых медленных тестов
    ])
    
    sys.exit(exit_code)
