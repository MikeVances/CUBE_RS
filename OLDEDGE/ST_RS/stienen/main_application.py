#!/usr/bin/env python3
"""
Main Application for Stienen RS485 Gateway
Основное приложение для гейтвея Stienen RS485
Миграция с C# на Python - полная система
"""

import asyncio
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import argparse

# Импорты наших модулей
from .rs485_protocol import RS485Protocol, StienenProtocolCmd
from .rs485_communication import RS485Communication
from .variable_mapping import VariableMapper
from .scada_integration import (
    ScadaIntegrationManager, RestScadaExporter, 
    XmlScadaExporter, CsvScadaExporter, ScadaConfig
)
from .gateway_backend import StienenGatewayBackend, GatewayConfig, GatewayFactory

class ConfigurationManager:
    """
    Менеджер конфигурации
    Загружает настройки из JSON файлов и переменных окружения
    """
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.logger = logging.getLogger(__name__)
        
        # Конфигурация по умолчанию
        self.default_config = {
            "gateway": {
                "name": "StienenGateway",
                "rs485_port": "/dev/ttyUSB0",  # Linux: /dev/ttyUSB0, Windows: COM1
                "rs485_baudrate": 38400,
                "polling_interval": 5.0,
                "identification_timeout": 30.0,
                "max_retries": 3,
                "scada_export_interval": 1.0,
                "keep_alive_interval": 30.0
            },
            "devices": [
                {
                    "address": 1,
                    "name": "ClimateController_01",
                    "hardware": 1001,
                    "version": 1,
                    "enabled": True
                }
            ],
            "scada": {
                "rest_api_url": None,
                "rest_auth_token": None,
                "xml_export_path": "./exports/stienen_data.xml",
                "csv_export_path": "./exports/stienen_data.csv",
                "mqtt_broker_host": None,
                "mqtt_broker_port": 1883,
                "mqtt_username": None,
                "mqtt_password": None,
                "export_interval": 1.0,
                "only_changed_values": True
            },
            "variables": {
                "config_file": "./config/variables.json",
                "auto_discovery": True
            },
            "logging": {
                "level": "INFO",
                "file": "./logs/gateway.log",
                "max_size_mb": 10,
                "backup_count": 5
            }
        }
    
    def load_config(self) -> Dict:
        """Загрузка конфигурации"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                
                # Объединяем с конфигурацией по умолчанию
                config = self._deep_merge(self.default_config, user_config)
                self.logger.info(f"Конфигурация загружена из {self.config_path}")
                return config
            else:
                self.logger.warning(f"Файл конфигурации {self.config_path} не найден, используются настройки по умолчанию")
                self.save_config(self.default_config)
                return self.default_config
                
        except Exception as e:
            self.logger.error(f"Ошибка загрузки конфигурации: {e}")
            return self.default_config
    
    def save_config(self, config: Dict):
        """Сохранение конфигурации"""
        try:
            # Создаем директорию если не существует
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Конфигурация сохранена в {self.config_path}")
            
        except Exception as e:
            self.logger.error(f"Ошибка сохранения конфигурации: {e}")
    
    def _deep_merge(self, default: Dict, user: Dict) -> Dict:
        """Глубокое объединение словарей"""
        result = default.copy()
        
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result

class StienenGatewayApplication:
    """
    Главное приложение гейтвея Stienen
    Координирует все компоненты системы
    """
    
    def __init__(self, config_path: str = "config.json"):
        self.config_manager = ConfigurationManager(config_path)
        self.config = self.config_manager.load_config()
        
        # Настройка логирования
        self._setup_logging()
        
        self.logger = logging.getLogger(__name__)
        
        # Основные компоненты
        self.gateway_backend: Optional[StienenGatewayBackend] = None
        self.scada_manager: Optional[ScadaIntegrationManager] = None
        
        # Обработка сигналов для корректного завершения
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.shutdown_event = asyncio.Event()
    
    def _setup_logging(self):
        """Настройка системы логирования"""
        log_config = self.config.get('logging', {})
        
        # Уровень логирования
        log_level = getattr(logging, log_config.get('level', 'INFO').upper())
        
        # Формат логов
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Консольный обработчик
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        # Файловый обработчик
        log_file = log_config.get('file', './logs/gateway.log')
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=log_config.get('max_size_mb', 10) * 1024 * 1024,
                backupCount=log_config.get('backup_count', 5),
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
        
        # Настройка root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        root_logger.addHandler(console_handler)
        if log_file:
            root_logger.addHandler(file_handler)
    
    def _signal_handler(self, signum, frame):
        """Обработчик сигналов для корректного завершения"""
        self.logger.info(f"Получен сигнал {signum}, завершение работы...")
        self.shutdown_event.set()
    
    async def initialize(self) -> bool:
        """Инициализация всех компонентов приложения"""
        self.logger.info("=== Инициализация Stienen Gateway ===")
        
        try:
            # Создаем конфигурацию гейтвея
            gateway_config = GatewayConfig(
                name=self.config['gateway']['name'],
                rs485_port=self.config['gateway']['rs485_port'],
                rs485_baudrate=self.config['gateway']['rs485_baudrate'],
                polling_interval=self.config['gateway']['polling_interval'],
                identification_timeout=self.config['gateway']['identification_timeout'],
                max_retries=self.config['gateway']['max_retries'],
                scada_export_interval=self.config['gateway']['scada_export_interval'],
                keep_alive_interval=self.config['gateway']['keep_alive_interval']
            )
            
            # Создаем бэкенд гейтвея
            self.gateway_backend = StienenGatewayBackend(gateway_config)
            
            # Инициализируем гейтвей
            if not await self.gateway_backend.initialize():
                self.logger.error("Не удалось инициализировать гейтвей")
                return False
            
            # Добавляем устройства из конфигурации
            await self._setup_devices()
            
            # Настраиваем SCADA интеграцию
            await self._setup_scada_integration()
            
            self.logger.info("=== Инициализация завершена ===")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка инициализации приложения: {e}")
            return False
    
    async def _setup_devices(self):
        """Настройка устройств из конфигурации"""
        devices_config = self.config.get('devices', [])
        
        for device_config in devices_config:
            if not device_config.get('enabled', True):
                continue
            
            await self.gateway_backend.add_device(
                address=device_config['address'],
                name=device_config.get('name', f"Device_{device_config['address']}"),
                hardware=device_config.get('hardware', 1001),
                version=device_config.get('version', 1)
            )
            
            self.logger.info(f"Добавлено устройство: {device_config['name']} (адрес {device_config['address']})")
    
    async def _setup_scada_integration(self):
        """Настройка SCADA интеграции"""
        scada_config_data = self.config.get('scada', {})
        
        # Создаем SCADA конфигурацию
        scada_config = ScadaConfig(
            rest_api_url=scada_config_data.get('rest_api_url'),
            rest_auth_token=scada_config_data.get('rest_auth_token'),
            xml_export_path=scada_config_data.get('xml_export_path'),
            mqtt_broker_host=scada_config_data.get('mqtt_broker_host'),
            mqtt_broker_port=scada_config_data.get('mqtt_broker_port', 1883),
            mqtt_username=scada_config_data.get('mqtt_username'),
            mqtt_password=scada_config_data.get('mqtt_password'),
            export_interval=scada_config_data.get('export_interval', 1.0),
            only_changed_values=scada_config_data.get('only_changed_values', True)
        )
        
        # Создаем SCADA менеджер через фабрику
        from .scada_integration import ScadaIntegrationFactory
        scada_manager = ScadaIntegrationFactory.create_integration(scada_config)
        
        # Регистрируем устройства в SCADA менеджере
        for device_id, device_manager in self.gateway_backend.device_managers.items():
            scada_manager.register_device_manager(device_id, device_manager)
        
        # Добавляем SCADA менеджер в гейтвей
        self.gateway_backend.scada_manager = scada_manager
        
        self.logger.info("SCADA интеграция настроена")
    
    async def run(self):
        """Основной цикл работы приложения"""
        self.logger.info("=== Запуск Stienen Gateway ===")
        
        try:
            # Ждем сигнала завершения или ошибки
            await self.shutdown_event.wait()
            
        except KeyboardInterrupt:
            self.logger.info("Получен сигнал прерывания")
        except Exception as e:
            self.logger.error(f"Ошибка в основном цикле: {e}")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Корректное завершение работы"""
        self.logger.info("=== Завершение работы Stienen Gateway ===")
        
        if self.gateway_backend:
            await self.gateway_backend.shutdown()
        
        # Сохраняем финальную конфигурацию
        self.config_manager.save_config(self.config)
        
        self.logger.info("Завершение работы completed")

# CLI интерфейс
def create_cli_parser() -> argparse.ArgumentParser:
    """Создание парсера командной строки"""
    parser = argparse.ArgumentParser(
        description="Stienen RS485 Gateway - система мониторинга контроллеров",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  %(prog)s --config config.json                    # Запуск с конфигурацией
  %(prog)s --port /dev/ttyUSB0 --devices 1,2,3     # Быстрый запуск
  %(prog)s --list-ports                             # Список доступных портов
  %(prog)s --test-protocol                          # Тест протокола
        """
    )
    
    parser.add_argument(
        '--config', '-c',
        default='config.json',
        help='Путь к файлу конфигурации (по умолчанию: config.json)'
    )
    
    parser.add_argument(
        '--port', '-p',
        help='COM порт для RS485 (переопределяет конфигурацию)'
    )
    
    parser.add_argument(
        '--devices', '-d',
        help='Адреса устройств через запятую (например: 1,2,3)'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Уровень логирования'
    )
    
    parser.add_argument(
        '--list-ports',
        action='store_true',
        help='Показать доступные COM порты и выйти'
    )
    
    parser.add_argument(
        '--test-protocol',
        action='store_true',
        help='Запустить тест протокола и выйти'
    )
    
    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Запуск в режиме демона (без вывода в консоль)'
    )
    
    return parser

def list_available_ports():
    """Вывод списка доступных COM портов"""
    import serial.tools.list_ports
    
    ports = serial.tools.list_ports.comports()
    
    print("Доступные COM порты:")
    print("-" * 50)
    
    if not ports:
        print("Нет доступных портов")
        return
    
    for port in ports:
        print(f"  {port.device}")
        print(f"    Описание: {port.description}")
        print(f"    Производитель: {port.manufacturer or 'Неизвестен'}")
        if hasattr(port, 'serial_number') and port.serial_number:
            print(f"    Серийный номер: {port.serial_number}")
        print()

def test_protocol():
    """Тест протокола RS485"""
    print("=== Тест протокола Stienen RS485 ===")
    
    from .rs485_protocol import RS485Protocol, StienenProtocolCmd, DataItem
    
    protocol = RS485Protocol()
    
    # Тест 1: Создание и парсинг пакета идентификации
    print("\n1. Тест пакета идентификации:")
    packet_data = protocol.create_identification_request(dest=1)
    print(f"   Созданный пакет: {packet_data.hex()}")
    
    parsed = protocol.parse_packet(packet_data)
    if parsed:
        header_ok, data_ok = protocol.verify_crc(parsed)
        print(f"   Парсинг: {'OK' if parsed else 'FAIL'}")
        print(f"   CRC заголовка: {'OK' if header_ok else 'FAIL'}")
        print(f"   CRC данных: {'OK' if data_ok else 'FAIL'}")
        print(f"   Команда: {protocol.get_command_name(parsed.header.cmd)}")
        print(f"   Адрес назначения: {parsed.header.dest}")
        print(f"   Адрес источника: {parsed.header.source}")
    else:
        print("   ОШИБКА: Не удалось распарсить пакет")
    
    # Тест 2: Создание пакета с данными
    print("\n2. Тест пакета с данными:")
    test_data_items = [
        DataItem(index=100, length=2, value=b'\x19\x01'),  # Температура 28.1°C
        DataItem(index=200, length=1, value=b'\x01'),       # Булево значение True
    ]
    
    data_packet = protocol.create_get_data_request(dest=1, data_items=test_data_items)
    print(f"   Пакет с данными: {data_packet.hex()}")
    
    parsed_data = protocol.parse_packet(data_packet)
    if parsed_data:
        decoded_items = protocol.decode_data_payload(parsed_data.header.payload)
        print(f"   Декодировано элементов: {len(decoded_items)}")
        for i, item in enumerate(decoded_items):
            print(f"     Элемент {i}: индекс={item.index}, длина={item.length}, данные={item.value.hex()}")
    
    # Тест 3: Поиск пакетов в буфере
    print("\n3. Тест поиска пакетов в буфере:")
    test_buffer = b'\x00\x11\x22' + packet_data + b'\x33\x44' + data_packet + b'\x55'
    found_packets = protocol.parse_message_from_buffer(test_buffer)
    print(f"   Найдено пакетов в буфере: {len(found_packets)}")
    
    for i, packet in enumerate(found_packets):
        print(f"     Пакет {i}: команда={protocol.get_command_name(packet.header.cmd)}, размер={len(packet.raw_data)}")
    
    print("\n=== Тест протокола завершен ===")

async def main():
    """Главная функция приложения"""
    parser = create_cli_parser()
    args = parser.parse_args()
    
    # Обработка специальных команд
    if args.list_ports:
        list_available_ports()
        return
    
    if args.test_protocol:
        test_protocol()
        return
    
    # Создаем приложение
    app = StienenGatewayApplication(args.config)
    
    # Переопределяем настройки из командной строки
    if args.port:
        app.config['gateway']['rs485_port'] = args.port
    
    if args.devices:
        # Парсим адреса устройств
        addresses = [int(addr.strip()) for addr in args.devices.split(',')]
        app.config['devices'] = [
            {
                'address': addr,
                'name': f'Device_{addr}',
                'hardware': 1001,
                'version': 1,
                'enabled': True
            }
            for addr in addresses
        ]
    
    # Настройка уровня логирования
    if args.log_level:
        logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    try:
        # Инициализация
        if await app.initialize():
            # Основной цикл работы
            await app.run()
        else:
            print("Ошибка инициализации приложения")
            return 1
            
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        return 1
    
    return 0

# Утилиты для разработки и отладки

class ProtocolDebugger:
    """Отладчик протокола для анализа пакетов"""
    
    @staticmethod
    def analyze_packet(data: bytes) -> Dict:
        """Детальный анализ пакета"""
        from .rs485_protocol import RS485Protocol
        
        protocol = RS485Protocol()
        result = {
            'raw_data': data.hex(),
            'length': len(data),
            'valid': False,
            'analysis': {}
        }
        
        packet = protocol.parse_packet(data)
        if packet:
            header_ok, data_ok = protocol.verify_crc(packet)
            
            result['valid'] = header_ok and data_ok
            result['analysis'] = {
                'header': {
                    'start_byte': f"0x{packet.header.start_byte:02X}",
                    'bus_state': packet.header.bus_state.name,
                    'dest': packet.header.dest,
                    'source': packet.header.source,
                    'data_len': packet.header.data_len,
                    'cmd': packet.header.cmd.name,
                    'version': packet.header.version,
                    'msg_id': packet.header.msg_id,
                    'header_crc': f"0x{packet.header.header_crc:04X}",
                    'header_crc_ok': header_ok
                },
                'data': {
                    'payload': packet.header.payload.hex() if packet.header.payload else '',
                    'data_crc': f"0x{packet.data_crc:04X}",
                    'data_crc_ok': data_ok
                }
            }
            
            # Декодируем payload если это команда с данными
            if packet.header.payload and packet.header.cmd in [
                StienenProtocolCmd.GET_DATA_RSP,
                StienenProtocolCmd.SET_DATA_REQ,
                StienenProtocolCmd.GET_CHANGED_DATA_RSP
            ]:
                decoded_items = protocol.decode_data_payload(packet.header.payload)
                result['analysis']['decoded_data'] = [
                    {
                        'index': item.index,
                        'length': item.length,
                        'value': item.value.hex()
                    }
                    for item in decoded_items
                ]
        
        return result

# Структура проекта Python
PROJECT_STRUCTURE = """
stienen_gateway/
├── main.py                     # Точка входа приложения
├── config.json                 # Конфигурация
├── requirements.txt            # Зависимости Python
├── setup.py                   # Установочный скрипт
├── 
├── stienen/                   # Основной пакет
│   ├── __init__.py
│   ├── rs485_protocol.py      # Протокол RS485
│   ├── rs485_communication.py # Коммуникация RS485
│   ├── variable_mapping.py    # Маппинг переменных
│   ├── scada_integration.py   # Интеграция SCADA
│   ├── gateway_backend.py     # Основной бэкенд
│   └── main_application.py    # Главное приложение
│
├── config/                    # Конфигурационные файлы
│   ├── variables.json         # Конфигурация переменных
│   └── devices.json          # Конфигурация устройств
│
├── logs/                     # Логи
│   └── gateway.log
│
├── exports/                  # Экспорт данных
│   ├── stienen_data.xml
│   └── stienen_data.csv
│
├── tests/                    # Тесты
│   ├── test_protocol.py
│   ├── test_communication.py
│   └── test_variables.py
│
└── docs/                     # Документация
    ├── README.md
    ├── MIGRATION.md          # Документация миграции
    └── API.md               # API документация
"""

# requirements.txt для проекта
REQUIREMENTS_TXT = """
# RS485 Communication
pyserial>=3.5
crcmod>=1.7

# Async support
aiohttp>=3.8.0
asyncio-mqtt>=0.11.0  # Опционально для MQTT

# Data processing
pydantic>=1.10.0
lxml>=4.9.0

# Database (если используется)
asyncpg>=0.27.0      # Для PostgreSQL
sqlalchemy>=1.4.0    # ORM опционально

# Logging and monitoring
coloredlogs>=15.0    # Цветные логи

# Testing
pytest>=7.0.0
pytest-asyncio>=0.21.0

# Development tools
black>=22.0.0        # Форматирование кода
pylint>=2.15.0       # Линтер
mypy>=0.991          # Типизация
"""

if __name__ == "__main__":
    # Запуск приложения
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
