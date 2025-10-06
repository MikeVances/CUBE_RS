#!/usr/bin/env python3
"""
RS485 Protocol Implementation for Stienen Controllers
Реализация протокола RS485 для контроллеров Stienen
Исправленная версия - полностью соответствует оригинальному C# коду
"""

import struct
import crcmod
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import IntEnum

class BusState(IntEnum):
    """Состояния шины (из C# кода)"""
    FREE = 0
    BUSY = 1
    ERROR = 2
    RESERVED = 3

class StienenProtocolCmd(IntEnum):
    """Команды протокола Stienen (расширенный набор из C#)"""
    # Основные команды
    INIT = 0x00
    NACK = 0x01
    IDENTIFICATION_REQ = 0x02
    IDENTIFICATION_RSP = 0x03
    INFO_REQ = 0x04
    INFO_RSP = 0x05
    GET_CHANGED_DATA_REQ = 0x06
    GET_CHANGED_DATA_RSP = 0x07
    GET_DATA_REQ = 0x08
    GET_DATA_RSP = 0x09
    SET_DATA_REQ = 0x0A
    SET_DATA_RSP = 0x0B
    
    # Резервное копирование
    BACKUP_REQ = 0x0C
    BACKUP_RSP = 0x0D
    RESTORE_REQ = 0x0E
    RESTORE_RSP = 0x0F
    
    # Логи событий и тревог
    EVENT_LOG_REQ = 0x10
    EVENT_LOG_RSP = 0x11
    ALARM_LOG_REQ = 0x12
    ALARM_LOG_RSP = 0x13
    
    # Дополнительные команды
    GET_STORED_DATA_REQ = 0x14
    GET_STORED_DATA_RSP = 0x15
    DATE_TIME_REQ = 0x16
    DATE_TIME_RSP = 0x17
    
    # PC485 специфичные команды
    PC485_INFO_REQ = 0x20
    PC485_INFO_RSP = 0x21
    PC485_SET_INFO_CHANGED_FILTER_REQ = 0x22
    PC485_SET_INFO_CHANGED_FILTER_RSP = 0x23
    PC485_FILTER_MESSAGES_REQ = 0x24
    PC485_FILTER_MESSAGES_RSP = 0x25

@dataclass
class StienenHeader:
    """Заголовок пакета Stienen протокола (12 байт) - ИСПРАВЛЕНО"""
    start_byte: int      # 0x0D - стартовый байт
    bus_state: BusState  # Состояние шины
    dest: int           # Адрес назначения
    source: int         # Адрес источника
    data_len: int       # Длина данных (2 байта, Big Endian)
    cmd: StienenProtocolCmd  # Команда
    version: int        # Версия протокола
    msg_id: int         # ID сообщения (2 байта, Big Endian)
    header_crc: int     # CRC заголовка (2 байта, Big Endian)
    payload: bytes = b'' # Полезная нагрузка

@dataclass
class StienenPacket:
    """Полный пакет Stienen протокола"""
    header: StienenHeader
    data_crc: int       # CRC данных (2 байта, Big Endian)
    raw_data: bytes     # Сырые данные пакета

@dataclass 
class DataItem:
    """Элемент данных в payload (соответствует C# Data class)"""
    index: int          # 4 байта, Little Endian в данных
    length: int         # 2 байта, Little Endian в данных  
    value: bytes        # Значение переменной
    last_index: bool = False

class RS485Protocol:
    """Реализация протокола RS485 для Stienen (ИСПРАВЛЕННАЯ ВЕРСИЯ)"""
    
    # Константы протокола (из C# кода)
    START_BYTE = 0x0D
    HEADER_SIZE = 12
    CRC_SIZE = 2
    
    # Адреса
    ADDRESS_PC485 = 254
    ADDRESS_BROADCAST = 255
    
    def __init__(self):
        # CRC16 функция для Stienen протокола (CrcCcitt)
        # Инициализация 0xFFFF, без XOR на выходе (как в C#)
        self.crc16 = crcmod.mkCrcFun(0x11021, initCrc=0xFFFF, xorOut=0x0000)
        self._message_id = 0
    
    def get_next_message_id(self) -> int:
        """Получение следующего ID сообщения"""
        self._message_id = (self._message_id + 1) % 65536
        return self._message_id
    
    def parse_header(self, data: bytes) -> Optional[StienenHeader]:
        """Парсинг заголовка Stienen протокола (12 байт) - ИСПРАВЛЕНО"""
        if len(data) < self.HEADER_SIZE:
            return None
        
        try:
            # ПРАВИЛЬНАЯ структура заголовка (как в C# StienenProtocol.cs):
            # Start(1) + BusState(1) + Dest(1) + Src(1) + DataLen(2) + Cmd(1) + Version(1) + MsgId(2) + HeaderCRC(2)
            header_data = struct.unpack('>BBBBHBBHH', data[:self.HEADER_SIZE])
            
            start_byte, bus_state, dest, source, data_len, cmd, version, msg_id, header_crc = header_data
            
            # Проверяем стартовый байт
            if start_byte != self.START_BYTE:
                return None
            
            # Проверяем состояние шины (должно быть < 4 согласно C# коду)
            if bus_state >= 4:
                return None
            
            # Извлекаем payload если есть данные
            payload_start = self.HEADER_SIZE
            payload_end = payload_start + data_len
            
            if len(data) >= payload_end:
                payload = data[payload_start:payload_end]
            else:
                payload = b''
            
            return StienenHeader(
                start_byte=start_byte,
                bus_state=BusState(bus_state),
                dest=dest,
                source=source,
                data_len=data_len,
                cmd=StienenProtocolCmd(cmd),
                version=version,
                msg_id=msg_id,
                header_crc=header_crc,
                payload=payload
            )
        except (struct.error, ValueError) as e:
            print(f"Ошибка парсинга заголовка: {e}")
            return None
    
    def parse_packet(self, data: bytes) -> Optional[StienenPacket]:
        """Парсинг полного пакета Stienen - ИСПРАВЛЕНО"""
        if len(data) < self.HEADER_SIZE + self.CRC_SIZE:
            return None
        
        # Парсим заголовок
        header = self.parse_header(data)
        if not header:
            return None
        
        # Проверяем минимальную длину пакета
        min_packet_size = self.HEADER_SIZE + header.data_len + self.CRC_SIZE
        if len(data) < min_packet_size:
            return None
        
        # Извлекаем CRC данных (Big Endian, как и всё в заголовке)
        data_crc_pos = self.HEADER_SIZE + header.data_len
        data_crc = struct.unpack('>H', data[data_crc_pos:data_crc_pos + self.CRC_SIZE])[0]
        
        return StienenPacket(
            header=header,
            data_crc=data_crc,
            raw_data=data[:min_packet_size]
        )
    
    def verify_crc(self, packet: StienenPacket) -> Tuple[bool, bool]:
        """Проверка CRC заголовка и данных (ИСПРАВЛЕНО согласно C#)"""
        # CRC заголовка: первые 10 байт (без поля HeaderCRC)
        header_data = packet.raw_data[:10]
        calculated_header_crc = self.crc16(header_data)
        header_crc_ok = (calculated_header_crc == packet.header.header_crc)
        
        # CRC данных: только payload
        calculated_data_crc = self.crc16(packet.header.payload)
        data_crc_ok = (calculated_data_crc == packet.data_crc)
        
        return header_crc_ok, data_crc_ok
    
    def build_packet(self, dest: int, source: int, cmd: StienenProtocolCmd, 
                    payload: bytes = b'', bus_state: BusState = BusState.FREE,
                    msg_id: Optional[int] = None) -> bytes:
        """Создание полного пакета (соответствует C# Finisch())"""
        
        if msg_id is None:
            msg_id = self.get_next_message_id()
        
        # Создаем заголовок без CRC (первые 10 байт)
        header_without_crc = struct.pack('>BBBBHBBH',
            self.START_BYTE,    # start_byte
            int(bus_state),     # bus_state  
            dest,               # dest
            source,             # source
            len(payload),       # data_len (Big Endian)
            int(cmd),           # cmd
            1,                  # version
            msg_id              # msg_id (Big Endian)
        )
        
        # Вычисляем CRC заголовка (первые 10 байт)
        header_crc = self.crc16(header_without_crc)
        
        # Вычисляем CRC данных
        data_crc = self.crc16(payload)
        
        # Собираем полный пакет
        full_packet = (
            header_without_crc +           # 10 байт
            struct.pack('>H', header_crc) + # 2 байта CRC заголовка
            payload +                       # payload
            struct.pack('>H', data_crc)     # 2 байта CRC данных
        )
        
        return full_packet
    
    def decode_data_payload(self, payload: bytes) -> List[DataItem]:
        """Декодирование payload данных (Little Endian как в C# Write методах)"""
        data_items = []
        i = 0
        
        while i + 6 <= len(payload):
            try:
                # Индекс (4 байта, Little Endian в данных!)
                index = struct.unpack('<I', payload[i:i+4])[0]
                
                # Длина (2 байта, Little Endian в данных!)
                length = struct.unpack('<H', payload[i+4:i+6])[0]
                
                # Проверяем, что есть достаточно данных
                if i + 6 + length > len(payload):
                    break
                
                # Извлекаем значение
                value = payload[i+6:i+6+length]
                
                data_items.append(DataItem(
                    index=index,
                    length=length,
                    value=value
                ))
                
                i += 6 + length
                
            except struct.error as e:
                print(f"Ошибка декодирования части данных: {e}")
                break
        
        return data_items
    
    def encode_data_payload(self, data_items: List[DataItem]) -> bytes:
        """Кодирование payload данных (Little Endian как в C#)"""
        payload = b''
        
        for item in data_items:
            # Индекс (4 байта, Little Endian)
            payload += struct.pack('<I', item.index)
            
            # Длина (2 байта, Little Endian) 
            payload += struct.pack('<H', len(item.value))
            
            # Значение
            payload += item.value
        
        return payload
    
    def get_command_name(self, cmd: Union[int, StienenProtocolCmd]) -> str:
        """Получение имени команды"""
        if isinstance(cmd, int):
            try:
                cmd = StienenProtocolCmd(cmd)
            except ValueError:
                return f"Unknown({cmd})"
        
        return cmd.name
    
    def is_valid_packet(self, data: bytes) -> bool:
        """Проверка валидности пакета"""
        packet = self.parse_packet(data)
        if not packet:
            return False
        
        header_crc_ok, data_crc_ok = self.verify_crc(packet)
        return header_crc_ok and data_crc_ok
    
    def create_identification_request(self, dest: int, source: int = ADDRESS_PC485) -> bytes:
        """Создание запроса идентификации"""
        return self.build_packet(dest, source, StienenProtocolCmd.IDENTIFICATION_REQ)
    
    def create_get_data_request(self, dest: int, data_items: List[DataItem], 
                              source: int = ADDRESS_PC485) -> bytes:
        """Создание запроса получения данных"""
        payload = self.encode_data_payload(data_items)
        return self.build_packet(dest, source, StienenProtocolCmd.GET_DATA_REQ, payload)
    
    def create_set_data_request(self, dest: int, data_items: List[DataItem],
                              source: int = ADDRESS_PC485) -> bytes:
        """Создание запроса установки данных"""
        payload = self.encode_data_payload(data_items)
        return self.build_packet(dest, source, StienenProtocolCmd.SET_DATA_REQ, payload)
    
    def parse_message_from_buffer(self, buffer: bytes) -> List[StienenPacket]:
        """Поиск и парсинг сообщений в буфере (аналог FindMessage из C#)"""
        packets = []
        offset = 0
        
        while offset < len(buffer):
            # Ищем стартовый байт
            start_pos = buffer.find(self.START_BYTE, offset)
            if start_pos == -1:
                break
            
            # Пытаемся распарсить пакет
            remaining_data = buffer[start_pos:]
            packet = self.parse_packet(remaining_data)
            
            if packet and self.is_valid_packet(remaining_data):
                packets.append(packet)
                offset = start_pos + len(packet.raw_data)
            else:
                # Переходим к следующему байту
                offset = start_pos + 1
        
        return packets

# Глобальный экземпляр протокола
protocol = RS485Protocol()

def parse_stienen_packet(data: bytes) -> Optional[StienenPacket]:
    """Удобная функция для парсинга пакета"""
    return protocol.parse_packet(data)

def verify_packet_crc(packet: StienenPacket) -> Tuple[bool, bool]:
    """Удобная функция для проверки CRC"""
    return protocol.verify_crc(packet)

def decode_payload(payload: bytes) -> List[DataItem]:
    """Удобная функция для декодирования payload"""
    return protocol.decode_data_payload(payload)

def create_packet(dest: int, source: int, cmd: StienenProtocolCmd, 
                 payload: bytes = b'') -> bytes:
    """Удобная функция для создания пакета"""
    return protocol.build_packet(dest, source, cmd, payload)

# Пример использования
if __name__ == "__main__":
    # Создаем запрос идентификации
    packet_data = protocol.create_identification_request(dest=1)
    print(f"Пакет идентификации: {packet_data.hex()}")
    
    # Парсим пакет обратно
    parsed = protocol.parse_packet(packet_data)
    if parsed:
        header_ok, data_ok = protocol.verify_crc(parsed)
        print(f"Заголовок CRC: {'OK' if header_ok else 'FAIL'}")
        print(f"Данные CRC: {'OK' if data_ok else 'FAIL'}")
        print(f"Команда: {protocol.get_command_name(parsed.header.cmd)}")
