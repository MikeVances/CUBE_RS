#!/usr/bin/env python3
"""
Gateway Backend Module
Основной модуль бэкенда гейтвея
Реализует функциональность Backend.cs из C#
"""

import asyncio
import json
import uuid
from typing import Dict, List, Optional, Set, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import logging

from .rs485_communication import RS485Communication, StienenPacket
from .variable_mapping import VariableMapper, DeviceVariableManager, FE_Type, FE_Reference
from .scada_integration import ScadaIntegrationManager, ScadaDataPoint
from .rs485_protocol import StienenProtocolCmd, BusState, DataItem

@dataclass
class DeviceInfo:
    """Информация об устройстве (аналог DeviceEx из C#)"""
    device_id: str
    gateway_id: str
    address: int                    # Адрес на шине RS485
    module: int                     # Номер модуля
    name: str                       # Имя устройства
    description: str                # Описание
    active: bool                    # Активно ли устройство
    fc_id: int                      # FarmConnect ID
    hardware: int                   # Версия аппаратуры
    version: int                    # Версия ПО
    user_number: int = 0            # Пользовательский номер
    operation_state: int = 0        # Состояние работы
    alarm_active: bool = False      # Активна ли тревога
    alarm_code: int = 0             # Код тревоги
    last_communication: Optional[datetime] = None  # Последняя связь
    identification_in_progress: bool = False

@dataclass
class GatewayConfig:
    """Конфигурация гейтвея"""
    name: str
    rs485_port: str
    rs485_baudrate: int = 38400
    polling_interval: float = 5.0          # Интервал опроса устройств (сек)
    identification_timeout: float = 30.0   # Таймаут идентификации (сек)
    max_retries: int = 3                   # Максимум повторов
    scada_export_interval: float = 1.0     # Интервал экспорта в SCADA (сек)
    keep_alive_interval: float = 30.0      # Интервал keep-alive (сек)

class StienenGatewayBackend:
    """
    Основной класс бэкенда гейтвея Stienen
    Аналог Backend.cs из C# - центральный координатор системы
    """
    
    def __init__(self, config: GatewayConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Основные компоненты
        self.rs485_comm: Optional[RS485Communication] = None
        self.variable_mapper = VariableMapper()
        self.scada_manager = ScadaIntegrationManager()
        
        # Устройства и их менеджеры
        self.devices: Dict[int, DeviceInfo] = {}  # address -> DeviceInfo
        self.device_managers: Dict[str, DeviceVariableManager] = {}  # device_id -> Manager
        
        # Состояние системы
        self.active = False
        self.initialization_busy = True
        self.communication_master = 0
        
        # Очереди задач
        self.identification_queue: Set[int] = set()    # Устройства для идентификации
        self.backup_queue: Set[int] = set()            # Устройства для резервного копирования
        self.polling_queue: Set[int] = set()           # Устройства для опроса
        
        # Таймеры и задачи
        self.polling_task: Optional[asyncio.Task] = None
        self.keep_alive_task: Optional[asyncio.Task] = None
        self.scada_export_task: Optional[asyncio.Task] = None
        
        # Статистика
        self.stats = {
            'packets_sent': 0,
            'packets_received': 0,
            'packets_failed': 0,
            'last_activity': None,
            'devices_online': 0
        }
    
    async def initialize(self) -> bool:
        """
        Инициализация гейтвея (аналог Backend конструктора и Init)
        """
        self.logger.info(f"Инициализация гейтвея {self.config.name}")
        
        try:
            # Инициализируем RS485 коммуникацию
            self.rs485_comm = RS485Communication(
                port=self.config.rs485_port,
                baudrate=self.config.rs485_baudrate
            )
            
            # Настраиваем callbacks
            self.rs485_comm.message_received_callback = self._on_message_received
            self.rs485_comm.message_sent_callback = self._on_message_sent
            self.rs485_comm.error_callback = self._on_communication_error
            
            # Переопределяем обработчики сообщений
            self._setup_message_handlers()
            
            # Инициализируем коммуникацию
            if not self.rs485_comm.initialize(receive_all=True):
                self.logger.error("Не удалось инициализировать RS485")
                return False
            
            # Загружаем конфигурацию переменных
            await self._load_variable_configuration()
            
            # Запускаем основные задачи
            await self._start_background_tasks()
            
            self.active = True
            self.logger.info("Гейтвей успешно инициализирован")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка инициализации гейтвея: {e}")
            return False
    
    def _setup_message_handlers(self):
        """Настройка обработчиков сообщений"""
        if not self.rs485_comm:
            return
        
        # Переопределяем методы обработки
        self.rs485_comm.rx_identification_rsp = self._handle_identification_response
        self.rs485_comm.rx_info_rsp = self._handle_info_response
        self.rs485_comm.rx_get_data_rsp = self._handle_get_data_response
        self.rs485_comm.rx_get_changed_data_rsp = self._handle_get_changed_data_response
        self.rs485_comm.rx_init = self._handle_init_message
    
    async def _load_variable_configuration(self):
        """Загрузка конфигурации переменных (из БД или файлов)"""
        # В реальной системе это загружается из PostgreSQL
        # Здесь пример конфигурации
        
        # Загружаем типы переменных
        example_types = [
            {
                'hardware': 1001, 'version': 1, 'id': 1, 'name': 'Temperature',
                'type': 2, 'mul': 1, 'div': 10, 'step': 0.1, 'min': -500, 'max': 1000
            },
            {
                'hardware': 1001, 'version': 1, 'id': 2, 'name': 'Boolean',
                'type': 0, 'mul': 1, 'div': 1, 'step': 1, 'min': 0, 'max': 1
            },
            {
                'hardware': 1001, 'version': 1, 'id': 3, 'name': 'Counter',
                'type': 3, 'mul': 1, 'div': 1, 'step': 1, 'min': 0, 'max': 2147483647
            }
        ]
        
        self.variable_mapper.load_types_from_config(example_types)
        
        # Загружаем ссылки на переменные
        example_references = [
            {
                'hardware': 1001, 'version': 1, 'id': 1, 'index': 100, 'length': 2,
                'name': 'AirTemperature', 'type_id': 1
            },
            {
                'hardware': 1001, 'version': 1, 'id': 2, 'index': 200, 'length': 1,
                'name': 'FanEnabled', 'type_id': 2
            },
            {
                'hardware': 1001, 'version': 1, 'id': 3, 'index': 300, 'length': 4,
                'name': 'TotalRuntime', 'type_id': 3
            }
        ]
        
        self.variable_mapper.load_references_from_config(example_references)
        
        self.logger.info("Конфигурация переменных загружена")
    
    async def _start_background_tasks(self):
        """Запуск фоновых задач"""
        # Задача опроса устройств
        self.polling_task = asyncio.create_task(self._polling_loop())
        
        # Задача keep-alive
        self.keep_alive_task = asyncio.create_task(self._keep_alive_loop())
        
        # Задача экспорта в SCADA
        self.scada_export_task = asyncio.create_task(self._scada_export_loop())
        
        self.logger.info("Фоновые задачи запущены")
    
    async def add_device(self, address: int, name: str = "", hardware: int = 1001, version: int = 1):
        """
        Добавление устройства для мониторинга
        
        Args:
            address: Адрес устройства на шине RS485
            name: Имя устройства
            hardware: Версия аппаратуры
            version: Версия ПО
        """
        device_id = str(uuid.uuid4())
        
        device_info = DeviceInfo(
            device_id=device_id,
            gateway_id=self.config.name,
            address=address,
            module=0,
            name=name or f"Device_{address}",
            description=f"Stienen device at address {address}",
            active=True,
            fc_id=address,
            hardware=hardware,
            version=version
        )
        
        # Создаем менеджер переменных для устройства
        device_manager = DeviceVariableManager(
            device_id=device_id,
            hardware=hardware,
            version=version,
            mapper=self.variable_mapper
        )
        
        # Регистрируем устройство
        self.devices[address] = device_info
        self.device_managers[device_id] = device_manager
        self.scada_manager.register_device_manager(device_id, device_manager)
        
        # Добавляем в очереди для инициализации
        self.identification_queue.add(address)
        self.polling_queue.add(address)
        
        self.logger.info(f"Добавлено устройство {name} (адрес {address})")
        
        # Сразу запускаем идентификацию
        await self._request_device_identification(address)
    
    async def _request_device_identification(self, address: int):
        """Запрос идентификации устройства (аналог TxIdentificationReq)"""
        if not self.rs485_comm:
            return
        
        device = self.devices.get(address)
        if device:
            device.identification_in_progress = True
        
        try:
            msg_id = self.rs485_comm.send_message(
                dest=address,
                cmd=StienenProtocolCmd.IDENTIFICATION_REQ,
                timeout_callback=lambda packet: self._identification_timeout(address)
            )
            
            self.logger.info(f"Запрос идентификации устройства {address} (msg_id: {msg_id})")
            
        except Exception as e:
            self.logger.error(f"Ошибка запроса идентификации {address}: {e}")
    
    def _identification_timeout(self, address: int):
        """Обработка таймаута идентификации"""
        device = self.devices.get(address)
        if device:
            device.identification_in_progress = False
            self.logger.warning(f"Таймаут идентификации устройства {address}")
            
            # Повторная попытка через некоторое время
            asyncio.create_task(self._retry_identification_later(address))
    
    async def _retry_identification_later(self, address: int, delay: float = 10.0):
        """Повторная попытка идентификации через задержку"""
        await asyncio.sleep(delay)
        if address in self.identification_queue:
            await self._request_device_identification(address)
    
    async def _request_device_info(self, address: int):
        """Запрос информации об устройстве (аналог TxInfoReq)"""
        if not self.rs485_comm:
            return
        
        try:
            msg_id = self.rs485_comm.send_message(
                dest=address,
                cmd=StienenProtocolCmd.INFO_REQ
            )
            
            self.logger.debug(f"Запрос информации устройства {address}")
            
        except Exception as e:
            self.logger.error(f"Ошибка запроса информации {address}: {e}")
    
    async def _request_device_data(self, address: int, variable_names: List[str] = None):
        """Запрос данных устройства (аналог TxGetDataReq)"""
        if not self.rs485_comm:
            return
        
        device = self.devices.get(address)
        if not device:
            return
        
        device_manager = self.device_managers.get(device.device_id)
        if not device_manager:
            return
        
        try:
            # Определяем переменные для запроса
            if variable_names:
                data_items = device_manager.get_variables_for_read(variable_names)
            else:
                # Запрашиваем все основные переменные
                all_vars = self.variable_mapper.get_all_variables(device.hardware, device.version)
                main_vars = [var['name'] for var in all_vars[:10]]  # Ограничиваем количество
                data_items = device_manager.get_variables_for_read(main_vars)
            
            if data_items:
                payload = self.rs485_comm.protocol.encode_data_payload(data_items)
                
                msg_id = self.rs485_comm.send_message(
                    dest=address,
                    cmd=StienenProtocolCmd.GET_DATA_REQ,
                    payload=payload
                )
                
                self.logger.debug(f"Запрос данных устройства {address} ({len(data_items)} переменных)")
            
        except Exception as e:
            self.logger.error(f"Ошибка запроса данных {address}: {e}")
    
    async def _request_changed_data(self, address: int):
        """Запрос изменившихся данных (аналог TxGetChangedDataReq)"""
        if not self.rs485_comm:
            return
        
        try:
            msg_id = self.rs485_comm.send_message(
                dest=address,
                cmd=StienenProtocolCmd.GET_CHANGED_DATA_REQ
            )
            
            self.logger.debug(f"Запрос изменившихся данных устройства {address}")
            
        except Exception as e:
            self.logger.error(f"Ошибка запроса изменившихся данных {address}: {e}")
    
    # Обработчики сообщений (аналоги RX_* методов из C#)
    
    def _handle_identification_response(self, packet: StienenPacket):
        """Обработка ответа идентификации (аналог RX_IdentificationRsp)"""
        address = packet.header.source
        device = self.devices.get(address)
        
        if device:
            device.identification_in_progress = False
            device.last_communication = datetime.now()
            
            # Убираем из очереди идентификации
            self.identification_queue.discard(address)
            
            self.logger.info(f"Получена идентификация от устройства {address}")
            
            # Запрашиваем информацию об устройстве
            asyncio.create_task(self._request_device_info(address))
    
    def _handle_info_response(self, packet: StienenPacket):
        """Обработка ответа информации (аналог RX_InfoRsp)"""
        address = packet.header.source
        device = self.devices.get(address)
        
        if device:
            device.last_communication = datetime.now()
            
            # Парсим информацию об устройстве из payload
            if len(packet.header.payload) >= 10:
                try:
                    # Формат как в C# MessageInfoRsp
                    import struct
                    data = struct.unpack('<IIBB', packet.header.payload[:10])
                    
                    device.user_number = data[0]
                    device.fc_id = data[1] 
                    device.operation_state = data[2]
                    alarm_flags = data[3]
                    
                    device.alarm_active = (alarm_flags & 0x01) != 0
                    
                    self.logger.info(f"Информация устройства {address}: FC_ID={device.fc_id}, состояние={device.operation_state}")
                    
                except Exception as e:
                    self.logger.error(f"Ошибка парсинга информации устройства {address}: {e}")
            
            # Запрашиваем данные устройства
            asyncio.create_task(self._request_device_data(address))
    
    def _handle_get_data_response(self, packet: StienenPacket):
        """Обработка ответа получения данных (аналог RX_GetDataRsp)"""
        address = packet.header.source
        device = self.devices.get(address)
        
        if device:
            device.last_communication = datetime.now()
            
            # Декодируем данные
            data_items = self.rs485_comm.protocol.decode_data_payload(packet.header.payload)
            
            # Обновляем переменные устройства
            device_manager = self.device_managers.get(device.device_id)
            if device_manager:
                device_manager.update_variable_values(data_items)
                
                self.logger.debug(f"Обновлены данные устройства {address}: {len(data_items)} переменных")
                
                # Обновляем статистику
                self.stats['devices_online'] = len([d for d in self.devices.values() 
                                                   if d.last_communication and 
                                                   datetime.now() - d.last_communication < timedelta(minutes=5)])
    
    def _handle_get_changed_data_response(self, packet: StienenPacket):
        """Обработка ответа изменившихся данных (аналог RX_GetChangedDataRsp)"""
        # Аналогично _handle_get_data_response, но логируем как изменившиеся данные
        self._handle_get_data_response(packet)
        
        address = packet.header.source
        self.logger.debug(f"Получены изменившиеся данные от устройства {address}")
    
    def _handle_init_message(self, packet: StienenPacket):
        """Обработка сообщения инициализации (аналог RX_Init)"""
        address = packet.header.source
        
        self.logger.info(f"Получено сообщение инициализации от устройства {address}")
        
        # Обрабатываем очереди резервного копирования
        if address in self.backup_queue:
            asyncio.create_task(self._process_backup_queue(address))
        
        # Если ожидается инициализация
        if self.initialization_busy:
            asyncio.create_task(self._finalize_initialization())
    
    async def _process_backup_queue(self, address: int):
        """Обработка очереди резервного копирования"""
        # Здесь реализация резервного копирования
        # Пока заглушка
        self.backup_queue.discard(address)
        self.logger.info(f"Обработка резервного копирования устройства {address}")
    
    async def _finalize_initialization(self):
        """Завершение инициализации"""
        # Проверяем, завершена ли инициализация всех устройств
        pending_identifications = len(self.identification_queue)
        
        if pending_identifications == 0:
            self.initialization_busy = False
            self.logger.info("Инициализация гейтвея завершена")
    
    # Фоновые задачи
    
    async def _polling_loop(self):
        """Основной цикл опроса устройств (аналог таймеров из C#)"""
        self.logger.info("Запущен цикл опроса устройств")
        
        while self.active:
            try:
                # Опрашиваем каждое активное устройство
                for address, device in self.devices.items():
                    if not device.active:
                        continue
                    
                    # Проверяем, нужно ли опрашивать устройство
                    last_comm = device.last_communication
                    if (not last_comm or 
                        datetime.now() - last_comm > timedelta(seconds=self.config.polling_interval)):
                        
                        # Опрашиваем изменившиеся данные
                        await self._request_changed_data(address)
                
                await asyncio.sleep(self.config.polling_interval)
                
            except Exception as e:
                self.logger.error(f"Ошибка в цикле опроса: {e}")
                await asyncio.sleep(5.0)
    
    async def _keep_alive_loop(self):
        """Цикл поддержания соединения"""
        self.logger.info("Запущен цикл keep-alive")
        
        while self.active:
            try:
                # Проверяем статус соединения
                if self.rs485_comm and self.rs485_comm.is_connected():
                    # Отправляем keep-alive всем устройствам
                    for address in self.devices.keys():
                        await self._request_device_info(address)
                
                await asyncio.sleep(self.config.keep_alive_interval)
                
            except Exception as e:
                self.logger.error(f"Ошибка в keep-alive: {e}")
                await asyncio.sleep(10.0)
    
    async def _scada_export_loop(self):
        """Цикл экспорта данных в SCADA"""
        self.logger.info("Запущен цикл экспорта в SCADA")
        
        while self.active:
            try:
                # Экспортируем все текущие значения
                await self.scada_manager.export_all_current_values()
                
                await asyncio.sleep(self.config.scada_export_interval)
                
            except Exception as e:
                self.logger.error(f"Ошибка экспорта в SCADA: {e}")
                await asyncio.sleep(5.0)
    
    # Callbacks событий
    
    def _on_message_received(self):
        """Callback получения сообщения"""
        self.stats['packets_received'] += 1
        self.stats['last_activity'] = datetime.now()
    
    def _on_message_sent(self):
        """Callback отправки сообщения"""
        self.stats['packets_sent'] += 1
        self.stats['last_activity'] = datetime.now()
    
    def _on_communication_error(self, error: str):
        """Callback ошибки коммуникации"""
        self.stats['packets_failed'] += 1
        self.logger.error(f"Ошибка коммуникации: {error}")
    
    # Публичные методы управления
    
    async def set_device_variable(self, address: int, variable_name: str, value: Any) -> bool:
        """
        Установка значения переменной устройства
        
        Args:
            address: Адрес устройства
            variable_name: Имя переменной
            value: Новое значение
            
        Returns:
            True если команда отправлена успешно
        """
        device = self.devices.get(address)
        if not device:
            self.logger.error(f"Устройство с адресом {address} не найдено")
            return False
        
        device_manager = self.device_managers.get(device.device_id)
        if not device_manager:
            self.logger.error(f"Менеджер устройства {address} не найден")
            return False
        
        # Устанавливаем значение локально
        if not device_manager.set_variable_value(variable_name, value):
            return False
        
        # Создаем команду для отправки
        variables = {variable_name: value}
        data_items = device_manager.get_variables_for_write(variables)
        
        if not data_items:
            self.logger.error(f"Не удалось создать данные для записи {variable_name}")
            return False
        
        try:
            payload = self.rs485_comm.protocol.encode_data_payload(data_items)
            
            msg_id = self.rs485_comm.send_message(
                dest=address,
                cmd=StienenProtocolCmd.SET_DATA_REQ,
                payload=payload
            )
            
            self.logger.info(f"Установка {variable_name}={value} для устройства {address}")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка установки переменной {variable_name}: {e}")
            return False
    
    def get_device_variable(self, address: int, variable_name: str) -> Any:
        """Получение текущего значения переменной устройства"""
        device = self.devices.get(address)
        if not device:
            return None
        
        device_manager = self.device_managers.get(device.device_id)
        if not device_manager:
            return None
        
        return device_manager.get_variable_value(variable_name)
    
    def get_all_device_values(self, address: int) -> Dict[str, Any]:
        """Получение всех текущих значений устройства"""
        device = self.devices.get(address)
        if not device:
            return {}
        
        device_manager = self.device_managers.get(device.device_id)
        if not device_manager:
            return {}
        
        return device_manager.get_all_current_values()
    
    def get_devices_status(self) -> List[Dict[str, Any]]:
        """Получение статуса всех устройств"""
        status_list = []
        
        for address, device in self.devices.items():
            last_comm = device.last_communication
            online = (last_comm and 
                     datetime.now() - last_comm < timedelta(minutes=1))
            
            status_list.append({
                'address': address,
                'name': device.name,
                'device_id': device.device_id,
                'hardware': device.hardware,
                'version': device.version,
                'online': online,
                'last_communication': last_comm.isoformat() if last_comm else None,
                'alarm_active': device.alarm_active,
                'identification_in_progress': device.identification_in_progress
            })
        
        return status_list
    
    def get_gateway_statistics(self) -> Dict[str, Any]:
        """Получение статистики гейтвея"""
        return {
            'name': self.config.name,
            'active': self.active,
            'devices_total': len(self.devices),
            'devices_online': self.stats['devices_online'],
            'packets_sent': self.stats['packets_sent'],
            'packets_received': self.stats['packets_received'],
            'packets_failed': self.stats['packets_failed'],
            'last_activity': self.stats['last_activity'].isoformat() if self.stats['last_activity'] else None,
            'rs485_connected': self.rs485_comm.is_connected() if self.rs485_comm else False,
            'queue_status': self.rs485_comm.get_queue_status() if self.rs485_comm else {}
        }
    
    async def shutdown(self):
        """Корректное завершение работы гейтвея"""
        self.logger.info("Завершение работы гейтвея...")
        
        self.active = False
        
        # Останавливаем задачи
        tasks_to_cancel = [
            self.polling_task,
            self.keep_alive_task,
            self.scada_export_task
        ]
        
        for task in tasks_to_cancel:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Останавливаем коммуникацию
        if self.rs485_comm:
            self.rs485_comm.stop()
        
        self.logger.info("Гейтвей остановлен")

# Фабрика для создания гейтвея
class GatewayFactory:
    """Фабрика для создания и настройки гейтвея"""
    
    @staticmethod
    def create_from_config_file(config_path: str) -> StienenGatewayBackend:
        """Создание гейтвея из файла конфигурации"""
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        config = GatewayConfig(
            name=config_data['name'],
            rs485_port=config_data['rs485_port'],
            rs485_baudrate=config_data.get('rs485_baudrate', 38400),
            polling_interval=config_data.get('polling_interval', 5.0),
            identification_timeout=config_data.get('identification_timeout', 30.0),
            max_retries=config_data.get('max_retries', 3),
            scada_export_interval=config_data.get('scada_export_interval', 1.0),
            keep_alive_interval=config_data.get('keep_alive_interval', 30.0)
        )
        
        gateway = StienenGatewayBackend(config)
        
        # Добавляем устройства из конфигурации
        for device_config in config_data.get('devices', []):
            asyncio.create_task(gateway.add_device(
                address=device_config['address'],
                name=device_config.get('name', ''),
                hardware=device_config.get('hardware', 1001),
                version=device_config.get('version', 1)
            ))
        
        return gateway
    
    @staticmethod
    def create_default(port: str, name: str = "StienenGateway") -> StienenGatewayBackend:
        """Создание гейтвея с настройками по умолчанию"""
        config = GatewayConfig(
            name=name,
            rs485_port=port
        )
        
        return StienenGatewayBackend(config)

# Пример конфигурационного файла
EXAMPLE_CONFIG = {
    "name": "StienenGateway_01",
    "rs485_port": "/dev/ttyUSB0",  # или "COM1" на Windows
    "rs485_baudrate": 38400,
    "polling_interval": 5.0,
    "identification_timeout": 30.0,
    "max_retries": 3,
    "scada_export_interval": 1.0,
    "keep_alive_interval": 30.0,
    "devices": [
        {
            "address": 1,
            "name": "ClimateController_01",
            "hardware": 1001,
            "version": 1
        },
        {
            "address": 2, 
            "name": "FeedController_01",
            "hardware": 1001,
            "version": 1
        }
    ],
    "scada": {
        "rest_api_url": "http://localhost:8080",
        "xml_export_path": "/tmp/stienen_export.xml",
        "mqtt_broker": "localhost"
    }
}

# Пример использования
if __name__ == "__main__":
    async def main():
        # Настройка логирования
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Создаем гейтвей
        gateway = GatewayFactory.create_default('/dev/ttyUSB0', 'TestGateway')
        
        try:
            # Инициализируем
            if await gateway.initialize():
                print("Гейтвей инициализирован")
                
                # Добавляем устройства
                await gateway.add_device(1, "ClimateController")
                await gateway.add_device(2, "FeedController")
                
                # Работаем 30 секунд
                await asyncio.sleep(30)
                
                # Получаем статистику
                stats = gateway.get_gateway_statistics()
                print(f"Статистика: {json.dumps(stats, indent=2, default=str)}")
                
                # Статус устройств
                devices_status = gateway.get_devices_status()
                print(f"Устройства: {json.dumps(devices_status, indent=2, default=str)}")
            
        finally:
            await gateway.shutdown()
    
    asyncio.run(main())
