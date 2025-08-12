"""
Modbus TCP‑шлюз для КУБ‑1063 (ШЛЮЗ 1) с полной поддержкой JSON конфигурации
Читает данные через TimeWindowManager (RS485) и ретранслирует их в Modbus TCP.
Поддержка ВСЕХ регистров из документации КУБ-1063
"""

import sys
import os
import time
import threading
import logging
import json
import argparse
from pathlib import Path

# Приоритет локального пакета поверх одноимённого PyPI-модуля
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.datastore import ModbusSequentialDataBlock

# Безопасные импорты локальных модулей
try:
    from modbus.modbus_storage import init_db, update_data
    from modbus.time_window_manager import (
        request_rs485_read_all,
        get_time_window_manager
    )
except ImportError:
    try:
        from .modbus_storage import init_db, update_data
        from .time_window_manager import (
            request_rs485_read_all,
            get_time_window_manager
        )
    except ImportError:
        # Fallback для прямого запуска
        import modbus_storage
        import time_window_manager
        init_db = modbus_storage.init_db
        update_data = modbus_storage.update_data
        request_rs485_read_all = time_window_manager.request_rs485_read_all
        get_time_window_manager = time_window_manager.get_time_window_manager

# Глобальная блокировка для потокобезопасной работы с хранилищем регистров
store_lock = threading.Lock()

# Глобальная конфигурация
CONFIG = None

def load_config():
    """Загрузка полной конфигурации из config.json"""
    config_file = Path(__file__).parent.parent / "config.json"
    
    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"⚠️ Ошибка загрузки config.json: {e}")
    
    # Дефолтная конфигурация если файл не найден
    return {
        "services": {
            "gateway1": {"port": 5021}
        },
        "rs485": {
            "port": "/dev/tty.usbserial-210",
            "baudrate": 9600,
            "parity": "N",
            "databits": 8,
            "stopbits": 1,
            "timeout": 2.0,
            "slave_id": 1,
            "window_duration": 5,
            "cooldown_duration": 10
        },
        "modbus_registers": {
            "software_version": "0x0301",
            "digital_outputs_1": "0x0081",
            "digital_outputs_2": "0x0082", 
            "digital_outputs_3": "0x00A2",
            "pressure": "0x0083",
            "humidity": "0x0084",
            "co2": "0x0085",
            "nh3": "0x0086",
            "grv_base": "0x0087",
            "grv_tunnel": "0x0088",
            "damper": "0x0089",
            "active_alarms": "0x00C3",
            "registered_alarms": "0x00C7",
            "active_warnings": "0x00CB",
            "registered_warnings": "0x00CF",
            "ventilation_target": "0x00D0",
            "ventilation_level": "0x00D1",
            "ventilation_scheme": "0x00D2",
            "day_counter": "0x00D3",
            "temp_target": "0x00D4",
            "temp_inside": "0x00D5",
            "temp_vent_activation": "0x00D6"
        },
        "logging": {
            "level": "INFO",
            "files": {
                "gateway1": "gateway1.log"
            }
        }
    }

def setup_logging(config):
    """Настройка логирования из конфигурации"""
    log_level = config.get("logging", {}).get("level", "INFO")
    log_file = config.get("logging", {}).get("files", {}).get("gateway1", "gateway1.log")
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s %(levelname)s [GATEWAY1] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

def get_port_config(config):
    """Получение порта из разных источников с приоритетами"""
    # Приоритет: CLI args > config.json > default
    
    # 1. Аргументы командной строки (высший приоритет)
    parser = argparse.ArgumentParser(description="Gateway 1 для КУБ-1063 - основной шлюз")
    parser.add_argument("--port", type=int, help="Modbus TCP port (default: config.json or 5021)")
    parser.add_argument("--config", default="config.json", help="Путь к файлу конфигурации")
    args, _ = parser.parse_known_args()
    
    if args.port:
        logging.info(f"🔧 Используем порт из аргументов: {args.port}")
        return args.port
    
    # 2. Файл конфигурации
    try:
        config_port = config.get("services", {}).get("gateway1", {}).get("port")
        if config_port:
            logging.info(f"📄 Используем порт из config.json: {config_port}")
            return config_port
    except Exception as e:
        logging.warning(f"⚠️ Ошибка чтения конфигурации порта: {e}")
    
    # 3. Дефолтное значение
    default_port = 5021
    logging.info(f"🔧 Используем дефолтный порт: {default_port}")
    return default_port

def get_rs485_config(config):
    """Получение настроек RS485 из конфигурации"""
    rs485_config = config.get("rs485", {})
    
    return {
        "serial_port": rs485_config.get("port", "/dev/tty.usbserial-210"),
        "baudrate": rs485_config.get("baudrate", 9600),
        "parity": rs485_config.get("parity", "N"),
        "databits": rs485_config.get("databits", 8),
        "stopbits": rs485_config.get("stopbits", 1),
        "timeout": rs485_config.get("timeout", 2.0),
        "slave_id": rs485_config.get("slave_id", 1),
        "window_duration": rs485_config.get("window_duration", 5),
        "cooldown_duration": rs485_config.get("cooldown_duration", 10)
    }

def get_register_mapping(config):
    """Получение маппинга регистров из конфигурации"""
    register_config = config.get("modbus_registers", {})
    
    # Конвертируем строковые адреса в числа
    register_map = {}
    for field_name, addr_str in register_config.items():
        try:
            if isinstance(addr_str, str) and addr_str.startswith("0x"):
                register_map[field_name] = int(addr_str, 16)
            else:
                register_map[field_name] = int(addr_str)
        except (ValueError, TypeError):
            logging.warning(f"⚠️ Неверный адрес регистра для {field_name}: {addr_str}")
    
    return register_map

def create_modbus_datastore():
    """Создаёт блок Holding Registers на полный диапазон адресов (0..65535)."""
    registers = [0] * 65536
    return ModbusSequentialDataBlock(0, registers)

def convert_value_to_register(value, field_name):
    """Конвертирует значение из БД в формат регистра с поддержкой ВСЕХ типов"""
    if value is None:
        return 0
    
    try:
        if field_name == "software_version":
            # Версия ПО как строка "4.14" -> 414
            if isinstance(value, str):
                parts = value.split('.')
                if len(parts) == 2:
                    return int(parts[0]) * 100 + int(parts[1])
            return 0
        
        elif field_name in ["temp_inside", "temp_target", "temp_vent_activation"]:
            # Температура в десятых долях
            temp = float(value) * 10
            # Обработка отрицательных значений (two's complement для 16-bit)
            if temp < 0:
                return int(65536 + temp)
            return int(temp)
        
        elif field_name in ["humidity", "pressure", "nh3"]:
            # Параметры в десятых долях
            val = float(value) * 10
            if val < 0:
                return int(65536 + val)
            return int(val)
        
        elif field_name in ["ventilation_level", "ventilation_target"]:
            # Вентиляция в десятых долях процента
            return int(float(value) * 10)
        
        elif field_name == "ventilation_scheme":
            # Текстовое значение в число
            if isinstance(value, str):
                return 1 if "туннельная" in value.lower() else 0
            return int(value)
        
        elif field_name in ["digital_outputs_1", "digital_outputs_2", "digital_outputs_3"]:
            # Битовые поля состояния цифровых выходов
            return int(value) if value is not None else 0
        
        elif field_name in ["grv_base", "grv_tunnel", "damper"]:
            # Выходы управления (0-100%)
            return int(float(value) * 10) if value is not None else 0
        
        elif field_name in ["active_alarms", "registered_alarms", "active_warnings", "registered_warnings"]:
            # Битовые поля аварий и предупреждений
            return int(value) if value is not None else 0
        
        elif field_name in ["co2", "day_counter"]:
            # Целые числа без преобразования
            return int(float(value))
        
        else:
            # По умолчанию - целые числа
            return int(float(value))
            
    except (ValueError, TypeError):
        logging.warning(f"⚠️ Ошибка конвертации {field_name}={value}")
        return 0

def update_register_from_data(store, register_addr, value):
    """Потокобезопасно обновляет значение Holding Register."""
    try:
        with store_lock:
            store.setValues(3, register_addr, [int(value)])  # FC=3 Holding
        logging.debug(f"📡 Обновлен регистр 0x{register_addr:04X} = {int(value)}")
    except Exception as e:
        logging.error(f"❌ Ошибка обновления регистра 0x{register_addr:04X}: {e}")

def update_modbus_registers_from_data(store, data, register_mapping):
    """Обновляет Modbus регистры из полученных данных"""
    updated_count = 0
    
    for field_name, register_addr in register_mapping.items():
        if field_name in data and data[field_name] is not None:
            register_value = convert_value_to_register(data[field_name], field_name)
            update_register_from_data(store, register_addr, register_value)
            updated_count += 1
        else:
            # Для отсутствующих полей записываем 0
            update_register_from_data(store, register_addr, 0)
    
    if updated_count > 0:
        logging.info(f"📡 Обновлено {updated_count}/{len(register_mapping)} Modbus регистров")
        # Показываем ключевые значения
        temp = data.get('temp_inside')
        humidity = data.get('humidity') 
        co2 = data.get('co2')
        alarms = data.get('active_alarms', 0)
        warnings = data.get('active_warnings', 0)
        logging.info(f"📊 Ключевые данные: temp={temp}°C, humidity={humidity}%, CO2={co2}ppm")
        if alarms or warnings:
            logging.warning(f"⚠️ Активные состояния: аварии=0x{alarms:04X}, предупреждения=0x{warnings:04X}")
    
    return updated_count

def run_modbus_server(context, port):
    """Запускает Modbus TCP‑сервер на указанном порту."""
    try:
        logging.info(f"🧲 Запуск Modbus TCP‑сервера на порту {port}…")
        StartTcpServer(context=context, address=("0.0.0.0", port))
    except Exception as e:
        logging.error(f"❌ Ошибка TCP сервера: {e}")

def main():
    global CONFIG
    
    # Загружаем конфигурацию
    CONFIG = load_config()
    
    # Настраиваем логирование из конфигурации
    setup_logging(CONFIG)
    
    logging.info("🚀 Запуск ШЛЮЗА 1: Modbus TCP ретранслятор для КУБ‑1063")
    
    # Получаем настройки из конфигурации
    modbus_tcp_port = get_port_config(CONFIG)
    rs485_config = get_rs485_config(CONFIG)
    register_mapping = get_register_mapping(CONFIG)
    
    logging.info(f"🔌 Modbus TCP порт: {modbus_tcp_port}")
    logging.info(f"📡 RS485 порт: {rs485_config['serial_port']}")
    logging.info(f"⚙️ RS485 настройки: {rs485_config['baudrate']}, {rs485_config['parity']}-{rs485_config['databits']}-{rs485_config['stopbits']}")
    logging.info(f"📋 Загружено {len(register_mapping)} регистров из конфигурации")
    
    # Показываем все загруженные регистры
    logging.info("📊 Поддерживаемые регистры:")
    for field_name, addr in sorted(register_mapping.items(), key=lambda x: x[1]):
        logging.info(f"  • 0x{addr:04X}: {field_name}")

    # Инициализация менеджера временных окон с настройками из конфига
    try:
        manager = get_time_window_manager(
            serial_port=rs485_config['serial_port'],
            window_duration=rs485_config['window_duration'],
            cooldown_duration=rs485_config['cooldown_duration'],
            baudrate=rs485_config['baudrate'],
            slave_id=rs485_config['slave_id']
        )
        logging.info(f"✅ TimeWindowManager инициализирован с настройками из config.json")
    except Exception as e:
        logging.error(f"❌ Ошибка инициализации TimeWindowManager: {e}")
        return

    # Инициализация БД (SQLite) для сводных данных/дашборда
    try:
        init_db()
        logging.info("✅ База данных инициализирована")
    except Exception as e:
        logging.error(f"❌ Ошибка инициализации БД: {e}")
        raise

    # Создание Modbus‑контекста (один slave, только Holding Registers)
    try:
        store = ModbusSlaveContext(hr=create_modbus_datastore())
        context = ModbusServerContext(slaves=store, single=True)
        logging.info("✅ Modbus контекст создан (65536 регистров)")
    except Exception as e:
        logging.error(f"❌ Ошибка создания контекста: {e}")
        raise

    # Фоновый поток: периодически запрашиваем RS485 и обновляем datastore + БД
    def update_loop():
        logging.info("🔄 Запуск цикла ретрансляции данных")
        
        while True:
            try:
                data_result = [None]

                def data_callback(data):
                    logging.debug(f"🔔 Callback вызван с данными: {data}")
                    data_result[0] = data

                logging.debug("📤 Отправка запроса в TimeWindowManager…")
                request_rs485_read_all(data_callback)

                # Ждём ответ общего запроса до 20 секунд
                start_time = time.time()
                while data_result[0] is None and time.time() - start_time < 20:
                    time.sleep(0.1)

                data = data_result[0]
                if data and data.get("connection_status") == "connected":
                    logging.info(f"📊 Получены данные с КУБ-1063")

                    # Используем полученные данные для обновления Modbus регистров
                    try:
                        updated_count = update_modbus_registers_from_data(store, data, register_mapping)
                        logging.info(f"📡 Ретранслировано {updated_count} регистров в Modbus TCP")
                    except Exception as e:
                        logging.error(f"❌ Ошибка ретрансляции в Modbus: {e}")

                    # Сохраняем данные в SQLite для дашборда
                    try:
                        update_data(**data)
                        logging.debug("💾 Данные сохранены в БД")
                    except Exception as e:
                        logging.error(f"❌ Ошибка сохранения в БД: {e}")
                else:
                    logging.warning("⚠️ Нет связи с КУБ‑1063 или нет данных")

                time.sleep(10)  # Интервал опроса
                
            except Exception as e:
                logging.error(f"❌ Ошибка в цикле ретрансляции: {e}")
                time.sleep(3)

    # Стартуем фоновый поток и TCP‑сервер
    threading.Thread(target=update_loop, daemon=True).start()
    run_modbus_server(context, modbus_tcp_port)

if __name__ == "__main__":
    main()