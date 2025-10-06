#!/usr/bin/env python3
"""
SCADA Integration Module
Модуль интеграции со SCADA системами
Реализует экспорт данных через различные протоколы (HTTP/REST, MQTT, OPC-UA)
"""

import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
import asyncio
import aiohttp
from typing import Dict, List, Optional, Any, Protocol
from dataclasses import dataclass, asdict
from datetime import datetime
from abc import ABC, abstractmethod
import logging

from .variable_mapping import VariableValue, DeviceVariableManager

@dataclass
class ScadaDataPoint:
    """Точка данных для передачи в SCADA"""
    device_id: str
    variable_name: str
    value: Any
    timestamp: datetime
    quality: str = "GOOD"  # GOOD, BAD, UNCERTAIN
    
class ScadaExporter(ABC):
    """Базовый класс для экспорта данных в SCADA"""
    
    @abstractmethod
    async def export_values(self, data_points: List[ScadaDataPoint]) -> bool:
        """Экспорт значений в SCADA"""
        pass
    
    @abstractmethod
    async def import_values(self, requests: List[Dict[str, Any]]) -> List[ScadaDataPoint]:
        """Импорт значений из SCADA"""
        pass

class RestScadaExporter(ScadaExporter):
    """
    Экспортер данных через REST API
    Аналог веб-сервисов из C# (IDataExchange)
    """
    
    def __init__(self, base_url: str, auth_token: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.auth_token = auth_token
        self.session: Optional[aiohttp.ClientSession] = None
        self.logger = logging.getLogger(__name__)
    
    async def __aenter__(self):
        headers = {'Content-Type': 'application/json'}
        if self.auth_token:
            headers['Authorization'] = f'Bearer {self.auth_token}'
        
        self.session = aiohttp.ClientSession(headers=headers)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def export_values(self, data_points: List[ScadaDataPoint]) -> bool:
        """Экспорт данных через REST API"""
        if not self.session:
            return False
        
        try:
            # Группируем по устройствам
            devices_data = {}
            for point in data_points:
                if point.device_id not in devices_data:
                    devices_data[point.device_id] = []
                
                devices_data[point.device_id].append({
                    'name': point.variable_name,
                    'value': point.value,
                    'timestamp': point.timestamp.isoformat(),
                    'quality': point.quality
                })
            
            # Отправляем данные по устройствам
            success_count = 0
            for device_id, variables in devices_data.items():
                payload = {
                    'device_id': device_id,
                    'timestamp': datetime.now().isoformat(),
                    'variables': variables
                }
                
                async with self.session.post(
                    f'{self.base_url}/api/devices/{device_id}/values',
                    json=payload
                ) as response:
                    if response.status == 200:
                        success_count += 1
                        self.logger.debug(f"Данные устройства {device_id} отправлены")
                    else:
                        self.logger.error(f"Ошибка отправки данных устройства {device_id}: {response.status}")
            
            return success_count == len(devices_data)
            
        except Exception as e:
            self.logger.error(f"Ошибка экспорта через REST: {e}")
            return False
    
    async def import_values(self, requests: List[Dict[str, Any]]) -> List[ScadaDataPoint]:
        """Импорт данных через REST API"""
        if not self.session:
            return []
        
        data_points = []
        
        try:
            for request in requests:
                device_id = request.get('device_id')
                variables = request.get('variables', [])
                
                if not device_id:
                    continue
                
                # Запрашиваем данные устройства
                async with self.session.get(
                    f'{self.base_url}/api/devices/{device_id}/values'
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        for var_data in data.get('variables', []):
                            if not variables or var_data['name'] in variables:
                                point = ScadaDataPoint(
                                    device_id=device_id,
                                    variable_name=var_data['name'],
                                    value=var_data['value'],
                                    timestamp=datetime.fromisoformat(var_data['timestamp']),
                                    quality=var_data.get('quality', 'GOOD')
                                )
                                data_points.append(point)
                    else:
                        self.logger.error(f"Ошибка получения данных устройства {device_id}: {response.status}")
        
        except Exception as e:
            self.logger.error(f"Ошибка импорта через REST: {e}")
        
        return data_points

class XmlScadaExporter(ScadaExporter):
    """
    Экспортер данных в XML формате
    Аналог XML сериализации из C#
    """
    
    def __init__(self, export_path: str):
        self.export_path = export_path
        self.logger = logging.getLogger(__name__)
    
    async def export_values(self, data_points: List[ScadaDataPoint]) -> bool:
        """Экспорт в XML файл"""
        try:
            # Создаем корневой элемент
            root = ET.Element('StienenData')
            root.set('timestamp', datetime.now().isoformat())
            root.set('xmlns', 'http://stienenbe.nl/')
            
            # Группируем по устройствам
            devices_data = {}
            for point in data_points:
                if point.device_id not in devices_data:
                    devices_data[point.device_id] = []
                devices_data[point.device_id].append(point)
            
            # Создаем XML структуру
            for device_id, points in devices_data.items():
                device_elem = ET.SubElement(root, 'Device')
                device_elem.set('id', device_id)
                
                variables_elem = ET.SubElement(device_elem, 'Variables')
                
                for point in points:
                    var_elem = ET.SubElement(variables_elem, 'Variable')
                    var_elem.set('name', point.variable_name)
                    var_elem.set('timestamp', point.timestamp.isoformat())
                    var_elem.set('quality', point.quality)
                    var_elem.text = str(point.value)
            
            # Форматируем XML
            rough_string = ET.tostring(root, 'unicode')
            reparsed = minidom.parseString(rough_string)
            pretty_xml = reparsed.toprettyxml(indent='  ')
            
            # Записываем в файл
            with open(self.export_path, 'w', encoding='utf-8') as f:
                f.write(pretty_xml)
            
            self.logger.info(f"XML экспорт завершен: {len(data_points)} точек в {self.export_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка XML экспорта: {e}")
            return False
    
    async def import_values(self, requests: List[Dict[str, Any]]) -> List[ScadaDataPoint]:
        """Импорт из XML файла"""
        data_points = []
        
        try:
            tree = ET.parse(self.export_path)
            root = tree.getroot()
            
            for device_elem in root.findall('Device'):
                device_id = device_elem.get('id')
                
                for var_elem in device_elem.findall('.//Variable'):
                    variable_name = var_elem.get('name')
                    timestamp_str = var_elem.get('timestamp')
                    quality = var_elem.get('quality', 'GOOD')
                    value = var_elem.text
                    
                    # Пытаемся определить тип значения
                    if value.lower() in ['true', 'false']:
                        value = value.lower() == 'true'
                    elif '.' in value:
                        try:
                            value = float(value)
                        except ValueError:
                            pass
                    else:
                        try:
                            value = int(value)
                        except ValueError:
                            pass
                    
                    point = ScadaDataPoint(
                        device_id=device_id,
                        variable_name=variable_name,
                        value=value,
                        timestamp=datetime.fromisoformat(timestamp_str),
                        quality=quality
                    )
                    data_points.append(point)
            
            self.logger.info(f"XML импорт завершен: {len(data_points)} точек")
            
        except Exception as e:
            self.logger.error(f"Ошибка XML импорта: {e}")
        
        return data_points

class MqttScadaExporter(ScadaExporter):
    """
    Экспортер данных через MQTT
    Современная альтернатива для IoT/SCADA интеграции
    """
    
    def __init__(self, broker_host: str, broker_port: int = 1883,
                 username: Optional[str] = None, password: Optional[str] = None,
                 topic_prefix: str = "stienen"):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self.topic_prefix = topic_prefix
        self.client = None
        self.logger = logging.getLogger(__name__)
    
    async def export_values(self, data_points: List[ScadaDataPoint]) -> bool:
        """Экспорт через MQTT"""
        try:
            # Для MQTT нужна библиотека paho-mqtt
            # pip install paho-mqtt
            import paho.mqtt.client as mqtt
            
            client = mqtt.Client()
            if self.username and self.password:
                client.username_pw_set(self.username, self.password)
            
            # Подключение
            client.connect(self.broker_host, self.broker_port, 60)
            client.loop_start()
            
            # Отправляем каждую точку данных
            for point in data_points:
                topic = f"{self.topic_prefix}/{point.device_id}/{point.variable_name}"
                
                payload = {
                    'value': point.value,
                    'timestamp': point.timestamp.isoformat(),
                    'quality': point.quality
                }
                
                result = client.publish(topic, json.dumps(payload), qos=1)
                if result.rc != mqtt.MQTT_ERR_SUCCESS:
                    self.logger.error(f"Ошибка отправки MQTT: {topic}")
                    return False
            
            client.loop_stop()
            client.disconnect()
            
            self.logger.info(f"MQTT экспорт завершен: {len(data_points)} точек")
            return True
            
        except ImportError:
            self.logger.error("Требуется установка paho-mqtt: pip install paho-mqtt")
            return False
        except Exception as e:
            self.logger.error(f"Ошибка MQTT экспорта: {e}")
            return False
    
    async def import_values(self, requests: List[Dict[str, Any]]) -> List[ScadaDataPoint]:
        """Импорт через MQTT (подписка на топики)"""
        # Для импорта через MQTT нужна более сложная реализация с подписками
        # Здесь базовая заглушка
        self.logger.warning("MQTT импорт требует дополнительной реализации")
        return []

class CsvScadaExporter(ScadaExporter):
    """
    Экспортер данных в CSV формат
    Аналог Export.cs из C# для табличных данных
    """
    
    def __init__(self, export_path: str):
        self.export_path = export_path
        self.logger = logging.getLogger(__name__)
    
    async def export_values(self, data_points: List[ScadaDataPoint]) -> bool:
        """Экспорт в CSV файл"""
        try:
            import csv
            
            with open(self.export_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['device_id', 'variable_name', 'value', 'timestamp', 'quality']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for point in data_points:
                    writer.writerow({
                        'device_id': point.device_id,
                        'variable_name': point.variable_name,
                        'value': point.value,
                        'timestamp': point.timestamp.isoformat(),
                        'quality': point.quality
                    })
            
            self.logger.info(f"CSV экспорт завершен: {len(data_points)} точек в {self.export_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка CSV экспорта: {e}")
            return False
    
    async def import_values(self, requests: List[Dict[str, Any]]) -> List[ScadaDataPoint]:
        """Импорт из CSV файла"""
        data_points = []
        
        try:
            import csv
            
            with open(self.export_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                
                for row in reader:
                    # Конвертируем значение в правильный тип
                    value = row['value']
                    if value.lower() in ['true', 'false']:
                        value = value.lower() == 'true'
                    elif '.' in value:
                        try:
                            value = float(value)
                        except ValueError:
                            pass
                    else:
                        try:
                            value = int(value)
                        except ValueError:
                            pass
                    
                    point = ScadaDataPoint(
                        device_id=row['device_id'],
                        variable_name=row['variable_name'],
                        value=value,
                        timestamp=datetime.fromisoformat(row['timestamp']),
                        quality=row['quality']
                    )
                    data_points.append(point)
            
            self.logger.info(f"CSV импорт завершен: {len(data_points)} точек")
            
        except Exception as e:
            self.logger.error(f"Ошибка CSV импорта: {e}")
        
        return data_points

class ScadaIntegrationManager:
    """
    Менеджер интеграции со SCADA
    Объединяет несколько экспортеров и управляет потоком данных
    """
    
    def __init__(self):
        self.exporters: List[ScadaExporter] = []
        self.device_managers: Dict[str, DeviceVariableManager] = {}
        self.logger = logging.getLogger(__name__)
        
        # Кэш для оптимизации отправки
        self.last_exported_values: Dict[str, Any] = {}
        self.export_interval = 1.0  # Секунды между экспортами
        self.only_changed = True    # Отправлять только изменившиеся значения
    
    def add_exporter(self, exporter: ScadaExporter):
        """Добавление экспортера SCADA"""
        self.exporters.append(exporter)
        self.logger.info(f"Добавлен экспортер: {type(exporter).__name__}")
    
    def register_device_manager(self, device_id: str, manager: DeviceVariableManager):
        """Регистрация менеджера устройства"""
        self.device_managers[device_id] = manager
        self.logger.info(f"Зарегистрировано устройство: {device_id}")
    
    async def export_all_current_values(self) -> bool:
        """Экспорт всех текущих значений во все SCADA системы"""
        if not self.exporters:
            self.logger.warning("Нет зарегистрированных экспортеров")
            return False
        
        # Собираем данные со всех устройств
        all_data_points = []
        
        for device_id, manager in self.device_managers.items():
            current_values = manager.get_all_current_values()
            
            for var_name, value in current_values.items():
                # Проверяем, изменилось ли значение
                cache_key = f"{device_id}:{var_name}"
                
                if not self.only_changed or self.last_exported_values.get(cache_key) != value:
                    point = ScadaDataPoint(
                        device_id=device_id,
                        variable_name=var_name,
                        value=value,
                        timestamp=datetime.now()
                    )
                    all_data_points.append(point)
                    
                    # Обновляем кэш
                    self.last_exported_values[cache_key] = value
        
        if not all_data_points:
            self.logger.debug("Нет изменившихся данных для экспорта")
            return True
        
        # Экспортируем во все системы
        success_count = 0
        for exporter in self.exporters:
            try:
                success = await exporter.export_values(all_data_points)
                if success:
                    success_count += 1
                else:
                    self.logger.error(f"Ошибка экспорта через {type(exporter).__name__}")
            except Exception as e:
                self.logger.error(f"Исключение в экспортере {type(exporter).__name__}: {e}")
        
        self.logger.info(f"Экспортировано {len(all_data_points)} точек через {success_count}/{len(self.exporters)} экспортеров")
        return success_count > 0
    
    async def export_specific_variables(self, device_id: str, variable_names: List[str]) -> bool:
        """Экспорт конкретных переменных устройства"""
        manager = self.device_managers.get(device_id)
        if not manager:
            self.logger.error(f"Устройство {device_id} не зарегистрировано")
            return False
        
        data_points = []
        for var_name in variable_names:
            value = manager.get_variable_value(var_name)
            if value is not None:
                point = ScadaDataPoint(
                    device_id=device_id,
                    variable_name=var_name,
                    value=value,
                    timestamp=datetime.now()
                )
                data_points.append(point)
        
        # Экспортируем
        success_count = 0
        for exporter in self.exporters:
            try:
                success = await exporter.export_values(data_points)
                if success:
                    success_count += 1
            except Exception as e:
                self.logger.error(f"Ошибка экспорта через {type(exporter).__name__}: {e}")
        
        return success_count > 0
    
    async def import_and_update_values(self, import_requests: List[Dict[str, Any]]):
        """Импорт данных из SCADA и обновление локальных значений"""
        for exporter in self.exporters:
            try:
                imported_points = await exporter.import_values(import_requests)
                
                # Обновляем локальные значения
                for point in imported_points:
                    manager = self.device_managers.get(point.device_id)
                    if manager:
                        success = manager.set_variable_value(point.variable_name, point.value)
                        if success:
                            self.logger.debug(f"Обновлена переменная {point.device_id}:{point.variable_name} = {point.value}")
                        else:
                            self.logger.warning(f"Не удалось обновить {point.device_id}:{point.variable_name}")
                
            except Exception as e:
                self.logger.error(f"Ошибка импорта через {type(exporter).__name__}: {e}")
    
    async def start_periodic_export(self):
        """Запуск периодического экспорта"""
        self.logger.info(f"Запущен периодический экспорт с интервалом {self.export_interval}с")
        
        while True:
            try:
                await self.export_all_current_values()
                await asyncio.sleep(self.export_interval)
            except Exception as e:
                self.logger.error(f"Ошибка в периодическом экспорте: {e}")
                await asyncio.sleep(5.0)  # Пауза при ошибке

# Конфигурационные классы

@dataclass
class ScadaConfig:
    """Конфигурация SCADA интеграции"""
    rest_api_url: Optional[str] = None
    rest_auth_token: Optional[str] = None
    xml_export_path: Optional[str] = None
    mqtt_broker_host: Optional[str] = None
    mqtt_broker_port: int = 1883
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    export_interval: float = 1.0
    only_changed_values: bool = True

class ScadaIntegrationFactory:
    """Фабрика для создания SCADA интеграции"""
    
    @staticmethod
    def create_integration(config: ScadaConfig) -> ScadaIntegrationManager:
        """Создание менеджера интеграции по конфигурации"""
        manager = ScadaIntegrationManager()
        manager.export_interval = config.export_interval
        manager.only_changed = config.only_changed_values
        
        # Добавляем экспортеры по конфигурации
        if config.rest_api_url:
            rest_exporter = RestScadaExporter(
                config.rest_api_url, 
                config.rest_auth_token
            )
            manager.add_exporter(rest_exporter)
        
        if config.xml_export_path:
            xml_exporter = XmlScadaExporter(config.xml_export_path)
            manager.add_exporter(xml_exporter)
        
        if config.mqtt_broker_host:
            mqtt_exporter = MqttScadaExporter(
                config.mqtt_broker_host,
                config.mqtt_broker_port,
                config.mqtt_username,
                config.mqtt_password
            )
            manager.add_exporter(mqtt_exporter)
        
        return manager

# Пример использования
if __name__ == "__main__":
    async def main():
        # Конфигурация
        config = ScadaConfig(
            rest_api_url="http://localhost:8080",
            xml_export_path="/tmp/stienen_export.xml",
            mqtt_broker_host="localhost",
            export_interval=2.0
        )
        
        # Создаем интеграцию
        scada_manager = ScadaIntegrationFactory.create_integration(config)
        
        # Пример экспорта данных
        test_data = [
            ScadaDataPoint("device1", "temperature", 25.5, datetime.now()),
            ScadaDataPoint("device1", "humidity", 60.2, datetime.now()),
            ScadaDataPoint("device2", "pressure", 1013.25, datetime.now()),
        ]
        
        # Экспортируем
        for exporter in scada_manager.exporters:
            if isinstance(exporter, (XmlScadaExporter, CsvScadaExporter)):
                success = await exporter.export_values(test_data)
                print(f"Экспорт через {type(exporter).__name__}: {'OK' if success else 'FAIL'}")
    
    asyncio.run(main())
