#!/usr/bin/env python3
"""
RS485 Communication Module for Stienen Controllers
Модуль коммуникации RS485 для контроллеров Stienen
Реализует функциональность StienenMethods из C#
"""

import asyncio
import threading
import time
import logging
from queue import Queue, Empty
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import IntEnum
import serial
import serial.tools.list_ports

from .rs485_protocol import (
    RS485Protocol, StienenPacket, StienenHeader, DataItem,
    BusState, StienenProtocolCmd
)

@dataclass
class SendMessageQueueItem:
    """Элемент очереди отправки сообщений (аналог C# SendMessageQueueItem)"""
    packet_data: bytes
    timeout_callback: Optional[Callable[['StienenMessage'], None]] = None
    priority: int = 0
    retries: int = 0
    max_retries: int = 3
    already_sent: bool = False
    created_at: float = field(default_factory=time.time)

class MessageTimeoutCallback:
    """Callback для обработки таймаутов сообщений"""
    def __init__(self, callback: Callable, timeout_seconds: float = 5.0):
        self.callback = callback
        self.timeout_seconds = timeout_seconds

class RS485Communication:
    """
    Основной класс коммуникации RS485 (аналог StienenMethods из C#)
    Обеспечивает надежную связь с контроллерами Stienen
    """
    
    # Адреса (из C# кода)
    ADDRESS_PC485 = 254
    ADDRESS_BROADCAST = 255
    
    def __init__(self, port: str, baudrate: int = 38400, timeout: float = 1.0):
        """
        Инициализация RS485 коммуникации
        
        Args:
            port: COM порт (например 'COM1' или '/dev/ttyUSB0')
            baudrate: Скорость передачи данных
            timeout: Таймаут чтения
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        
        # Протокол
        self.protocol = RS485Protocol()
        
        # Очереди сообщений (как в C#)
        self.send_queue: List[SendMessageQueueItem] = []
        self.receive_queue: Queue = Queue()
        
        # Синхронизация
        self.queue_lock = threading.Lock()
        self.receive_lock = threading.Lock()
        
        # Потоки
        self.message_handler_thread: Optional[threading.Thread] = None
        self.timeout_timer_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # Состояние
        self.active = False
        self.receive_all = False
        self.serial_connection: Optional[serial.Serial] = None
        
        # Таймауты и повторы
        self.default_timeout = 5.0
        self.message_timeouts: Dict[int, MessageTimeoutCallback] = {}
        
        # Логирование
        self.logger = logging.getLogger(__name__)
        
        # Callbacks
        self.message_sent_callback: Optional[Callable] = None
        self.message_received_callback: Optional[Callable] = None
        self.error_callback: Optional[Callable[[str], None]] = None
    
    def initialize(self, receive_all: bool = False) -> bool:
        """
        Инициализация соединения (аналог Init из C#)
        
        Args:
            receive_all: Принимать все сообщения или только адресованные PC485
        """
        self.receive_all = receive_all
        
        try:
            # Открываем последовательный порт
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS
            )
            
            if not self.serial_connection.is_open:
                self.serial_connection.open()
            
            self.active = True
            
            # Запускаем потоки обработки
            self.start_threads()
            
            self.logger.info(f"RS485 соединение установлено на {self.port}")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка инициализации RS485: {e}")
            if self.error_callback:
                self.error_callback(f"Ошибка инициализации: {e}")
            return False
    
    def start_threads(self):
        """Запуск рабочих потоков"""
        self.stop_event.clear()
        
        # Поток обработки сообщений
        self.message_handler_thread = threading.Thread(
            target=self._message_handler_loop,
            name="RS485MessageHandler"
        )
        self.message_handler_thread.daemon = False
        self.message_handler_thread.start()
        
        # Поток чтения из порта
        read_thread = threading.Thread(
            target=self._serial_read_loop,
            name="RS485Reader"
        )
        read_thread.daemon = False
        read_thread.start()
        
        # Поток обработки таймаутов
        self.timeout_timer_thread = threading.Thread(
            target=self._timeout_handler_loop,
            name="RS485TimeoutHandler"
        )
        self.timeout_timer_thread.daemon = False
        self.timeout_timer_thread.start()
    
    def stop(self):
        """Остановка коммуникации"""
        self.active = False
        self.stop_event.set()
        
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
        
        # Ждем завершения потоков
        if self.message_handler_thread:
            self.message_handler_thread.join(timeout=2.0)
        if self.timeout_timer_thread:
            self.timeout_timer_thread.join(timeout=2.0)
    
    def send_message(self, dest: int, cmd: StienenProtocolCmd, 
                    payload: bytes = b'', source: int = None,
                    timeout_callback: Optional[Callable] = None,
                    priority: int = 0) -> int:
        """
        Отправка сообщения (аналог Send из C#)
        
        Returns:
            message_id: ID отправленного сообщения
        """
        if source is None:
            source = self.ADDRESS_PC485
        
        # Создаем пакет
        packet_data = self.protocol.build_packet(dest, source, cmd, payload)
        
        # Извлекаем message_id из созданного пакета
        parsed = self.protocol.parse_packet(packet_data)
        if not parsed:
            return 0
        
        message_id = parsed.header.msg_id
        
        # Добавляем в очередь
        queue_item = SendMessageQueueItem(
            packet_data=packet_data,
            timeout_callback=timeout_callback,
            priority=priority
        )
        
        with self.queue_lock:
            # Проверяем, нет ли уже такого сообщения в очереди
            duplicate_found = False
            for item in self.send_queue:
                existing_packet = self.protocol.parse_packet(item.packet_data)
                if (existing_packet and 
                    existing_packet.header.dest == dest and
                    existing_packet.header.cmd == cmd and
                    existing_packet.header.source == source):
                    duplicate_found = True
                    break
            
            if not duplicate_found:
                # Добавляем с учетом приоритета
                self._add_message_to_queue(queue_item)
                
                # Регистрируем таймаут если нужен
                if timeout_callback:
                    self.message_timeouts[message_id] = MessageTimeoutCallback(
                        timeout_callback, self.default_timeout
                    )
                
                self.logger.info(f"Сообщение добавлено в очередь [cmd: {cmd.name} dest: {dest}]")
            else:
                self.logger.info(f"Сообщение уже в очереди [cmd: {cmd.name} dest: {dest}]")
        
        # Пытаемся отправить следующее сообщение
        self._process_send_queue()
        
        return message_id
    
    def _add_message_to_queue(self, item: SendMessageQueueItem):
        """Добавление сообщения в очередь с учетом приоритета"""
        if not self.send_queue:
            self.send_queue.append(item)
            return
        
        # Ищем позицию для вставки по приоритету
        insert_pos = len(self.send_queue)
        for i, existing_item in enumerate(self.send_queue):
            if existing_item.priority > item.priority:
                insert_pos = i
                break
        
        self.send_queue.insert(insert_pos, item)
    
    def _process_send_queue(self):
        """Обработка очереди отправки"""
        with self.queue_lock:
            if not self.send_queue:
                return
            
            first_item = self.send_queue[0]
            
            if not first_item.already_sent:
                success = self._write_to_serial(first_item.packet_data)
                if success:
                    first_item.already_sent = True
                    
                    # Проверяем, нужен ли ответ
                    parsed = self.protocol.parse_packet(first_item.packet_data)
                    if (parsed and 
                        parsed.header.dest == self.ADDRESS_BROADCAST):
                        # Broadcast сообщение - убираем сразу
                        self.send_queue.pop(0)
                    
                    if self.message_sent_callback:
                        self.message_sent_callback()
                else:
                    self.logger.warning("Не удалось отправить сообщение - нет соединения")
    
    def _write_to_serial(self, data: bytes) -> bool:
        """Запись данных в последовательный порт"""
        if not self.serial_connection or not self.serial_connection.is_open:
            return False
        
        try:
            self.serial_connection.write(data)
            self.serial_connection.flush()
            
            # Логируем отправленное сообщение
            parsed = self.protocol.parse_packet(data)
            if parsed:
                h = parsed.header
                self.logger.info(f"OUT: {h.bus_state.name} {h.dest} {h.source} {h.data_len} {h.cmd.name} {h.msg_id}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка записи в порт: {e}")
            if self.error_callback:
                self.error_callback(f"Ошибка записи: {e}")
            return False
    
    def _serial_read_loop(self):
        """Поток чтения данных из последовательного порта"""
        buffer = b''
        
        while not self.stop_event.is_set() and self.active:
            try:
                if self.serial_connection and self.serial_connection.is_open:
                    # Читаем доступные данные
                    if self.serial_connection.in_waiting > 0:
                        data = self.serial_connection.read(self.serial_connection.in_waiting)
                        buffer += data
                        
                        # Пытаемся найти и распарсить пакеты
                        packets = self.protocol.parse_message_from_buffer(buffer)
                        
                        for packet in packets:
                            # Очищаем обработанные данные из буфера
                            packet_size = len(packet.raw_data)
                            packet_start = buffer.find(packet.raw_data)
                            if packet_start >= 0:
                                buffer = buffer[packet_start + packet_size:]
                            
                            self._handle_received_packet(packet)
                
                time.sleep(0.01)  # 10ms как в C#
                
            except Exception as e:
                self.logger.error(f"Ошибка чтения из порта: {e}")
                if self.error_callback:
                    self.error_callback(f"Ошибка чтения: {e}")
                time.sleep(0.1)
    
    def _handle_received_packet(self, packet: StienenPacket):
        """Обработка принятого пакета (аналог Stream_Read из C#)"""
        if not self.active:
            return
        
        header = packet.header
        
        # Проверяем CRC
        header_crc_ok, data_crc_ok = self.protocol.verify_crc(packet)
        if not header_crc_ok or not data_crc_ok:
            self.logger.warning(f"CRC ошибка: header={header_crc_ok}, data={data_crc_ok}")
            return
        
        # Логируем принятое сообщение
        self.logger.info(f"IN : {header.bus_state.name} {header.dest} {header.source} {header.data_len} {header.cmd.name} {header.msg_id}")
        
        # Проверяем адресацию
        if (self.receive_all or 
            header.dest == self.ADDRESS_PC485 or 
            header.dest == self.ADDRESS_BROADCAST):
            
            # Обрабатываем ответы на наши запросы
            self._handle_response(packet)
            
            # Добавляем в очередь для обработки приложением
            with self.receive_lock:
                self.receive_queue.put(packet)
            
            if self.message_received_callback:
                self.message_received_callback()
    
    def _handle_response(self, packet: StienenPacket):
        """Обработка ответов на наши запросы (аналог логики из C# Stream_Read)"""
        header = packet.header
        
        with self.queue_lock:
            if self.send_queue:
                first_item = self.send_queue[0]
                sent_packet = self.protocol.parse_packet(first_item.packet_data)
                
                if (sent_packet and 
                    sent_packet.header.msg_id == header.msg_id):
                    
                    # Это ответ на наш запрос
                    if header.bus_state != BusState.FREE:
                        # Еще ждем окончательного ответа
                        pass
                    else:
                        # Сообщение завершено успешно
                        self.logger.info(f"Сообщение завершено успешно [cmd: {header.cmd.name} src: {header.source}]")
                        
                        # Убираем таймаут
                        if header.msg_id in self.message_timeouts:
                            del self.message_timeouts[header.msg_id]
                        
                        # Убираем из очереди
                        self.send_queue.pop(0)
                        
                        # Отправляем следующее сообщение
                        self._process_send_queue()
    
    def _message_handler_loop(self):
        """Поток обработки принятых сообщений (аналог MessageHandlerThreadHandler из C#)"""
        while not self.stop_event.is_set():
            try:
                # Обрабатываем все сообщения в очереди
                processed_any = False
                
                while True:
                    try:
                        packet = self.receive_queue.get_nowait()
                        self._dispatch_message(packet)
                        processed_any = True
                    except Empty:
                        break
                
                # Если ничего не обработали, небольшая пауза
                if not processed_any:
                    time.sleep(0.01)  # 10ms
                    
            except Exception as e:
                self.logger.error(f"Ошибка в обработчике сообщений: {e}")
                time.sleep(0.1)
    
    def _dispatch_message(self, packet: StienenPacket):
        """Диспетчеризация сообщений по командам (аналог HandleMessage из C#)"""
        try:
            header = packet.header
            cmd = header.cmd
            
            # Вызываем соответствующий обработчик
            handler_name = f"rx_{cmd.name.lower()}"
            handler = getattr(self, handler_name, None)
            
            if handler and callable(handler):
                handler(packet)
            else:
                self.logger.warning(f"Нет обработчика для команды {cmd.name}")
                
        except Exception as e:
            self.logger.error(f"Ошибка диспетчеризации сообщения: {e}")
    
    def _timeout_handler_loop(self):
        """Поток обработки таймаутов сообщений"""
        while not self.stop_event.is_set():
            try:
                current_time = time.time()
                expired_timeouts = []
                
                # Ищем истекшие таймауты
                for msg_id, timeout_info in self.message_timeouts.items():
                    with self.queue_lock:
                        for item in self.send_queue:
                            packet = self.protocol.parse_packet(item.packet_data)
                            if (packet and 
                                packet.header.msg_id == msg_id and
                                current_time - item.created_at > timeout_info.timeout_seconds):
                                expired_timeouts.append((msg_id, item, timeout_info))
                                break
                
                # Обрабатываем таймауты
                for msg_id, item, timeout_info in expired_timeouts:
                    self._handle_timeout(msg_id, item, timeout_info)
                
                time.sleep(0.1)  # Проверяем таймауты каждые 100ms
                
            except Exception as e:
                self.logger.error(f"Ошибка в обработчике таймаутов: {e}")
                time.sleep(1.0)
    
    def _handle_timeout(self, msg_id: int, item: SendMessageQueueItem, 
                       timeout_info: MessageTimeoutCallback):
        """Обработка таймаута сообщения"""
        packet = self.protocol.parse_packet(item.packet_data)
        if not packet:
            return
        
        with self.queue_lock:
            if item.retries < item.max_retries:
                # Повторная отправка
                item.retries += 1
                item.already_sent = False
                item.created_at = time.time()
                
                self.logger.warning(f"Таймаут, повтор {item.retries} [cmd: {packet.header.cmd.name} dest: {packet.header.dest}]")
                
                # Отправляем снова
                self._process_send_queue()
            else:
                # Превышено количество повторов
                self.logger.error(f"Превышено количество повторов [cmd: {packet.header.cmd.name} dest: {packet.header.dest}]")
                
                # Убираем из очереди
                if item in self.send_queue:
                    self.send_queue.remove(item)
                
                # Убираем таймаут
                if msg_id in self.message_timeouts:
                    del self.message_timeouts[msg_id]
                
                # Вызываем callback
                if timeout_info.callback:
                    timeout_info.callback(packet)
                
                # Обрабатываем следующее сообщение
                self._process_send_queue()
    
    # Обработчики команд (виртуальные методы как в C#)
    # Переопределяются в дочерних классах
    
    def rx_init(self, packet: StienenPacket):
        """Обработка команды Init"""
        pass
    
    def rx_nack(self, packet: StienenPacket):
        """Обработка команды Nack"""
        pass
    
    def rx_identification_req(self, packet: StienenPacket):
        """Обработка запроса идентификации"""
        pass
    
    def rx_identification_rsp(self, packet: StienenPacket):
        """Обработка ответа идентификации"""
        pass
    
    def rx_info_req(self, packet: StienenPacket):
        """Обработка запроса информации"""
        pass
    
    def rx_info_rsp(self, packet: StienenPacket):
        """Обработка ответа информации"""
        self.logger.info(f"RX_Info от устройства {packet.header.source}")
    
    def rx_get_data_req(self, packet: StienenPacket):
        """Обработка запроса получения данных"""
        pass
    
    def rx_get_data_rsp(self, packet: StienenPacket):
        """Обработка ответа получения данных"""
        pass
    
    def rx_set_data_req(self, packet: StienenPacket):
        """Обработка запроса установки данных"""
        pass
    
    def rx_set_data_rsp(self, packet: StienenPacket):
        """Обработка ответа установки данных"""
        pass
    
    def rx_get_changed_data_req(self, packet: StienenPacket):
        """Обработка запроса изменившихся данных"""
        pass
    
    def rx_get_changed_data_rsp(self, packet: StienenPacket):
        """Обработка ответа изменившихся данных"""
        pass
    
    # Вспомогательные методы
    
    def get_available_ports(self) -> List[str]:
        """Получение списка доступных COM портов"""
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]
    
    def is_connected(self) -> bool:
        """Проверка состояния соединения"""
        return (self.serial_connection and 
                self.serial_connection.is_open and 
                self.active)
    
    def clear_queues(self):
        """Очистка всех очередей"""
        with self.queue_lock:
            self.send_queue.clear()
        
        with self.receive_lock:
            while not self.receive_queue.empty():
                try:
                    self.receive_queue.get_nowait()
                except Empty:
                    break
        
        self.message_timeouts.clear()
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Получение статуса очередей"""
        with self.queue_lock:
            return {
                'send_queue_size': len(self.send_queue),
                'receive_queue_size': self.receive_queue.qsize(),
                'active_timeouts': len(self.message_timeouts),
                'connected': self.is_connected()
            }

# Пример использования
if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(level=logging.INFO)
    
    # Создаем коммуникацию
    comm = RS485Communication('/dev/ttyUSB0')  # Или 'COM1' на Windows
    
    try:
        # Инициализация
        if comm.initialize():
            print("RS485 соединение установлено")
            
            # Отправляем запрос идентификации
            msg_id = comm.send_message(
                dest=1, 
                cmd=StienenProtocolCmd.IDENTIFICATION_REQ
            )
            
            # Ждем немного
            time.sleep(2)
            
            # Проверяем статус
            status = comm.get_queue_status()
            print(f"Статус очередей: {status}")
        
        # Работаем...
        time.sleep(10)
        
    finally:
        comm.stop()
        print("RS485 соединение закрыто")
