"""
Gateway 2 - поддержка FC=03 и FC=04 с конфигурируемыми портами
Записывает данные И в Holding Registers (FC=03) И в Input Registers (FC=04)
"""

import sys
import os
import time
import threading
import logging
import json
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.datastore import ModbusSequentialDataBlock

try:
    from modbus.modbus_storage import read_data
except ImportError:
    try:
        from .modbus_storage import read_data
    except ImportError:
        import modbus_storage
        read_data = modbus_storage.read_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [GATEWAY2] %(message)s",
    handlers=[
        logging.FileHandler("gateway2.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

store_lock = threading.Lock()

# Маппинг полей БД на адреса регистров
DB_TO_REGISTER_MAP = {
    "software_version": 0x0301,
    "temp_inside": 0x00D5,
    "temp_target": 0x00D4,
    "humidity": 0x0084,
    "co2": 0x0085,
    "nh3": 0x0086,
    "pressure": 0x0083,
    "ventilation_level": 0x00D1,
    "ventilation_target": 0x00D0,
    "ventilation_scheme": 0x00D2,
    "day_counter": 0x00D3,
}

def load_config():
    """Загрузка конфигурации из config.json"""
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
            "gateway2": {"port": 5022}
        }
    }

def get_port_config():
    """Получение порта из разных источников с приоритетами"""
    # Приоритет: CLI args > config.json > default
    
    # 1. Аргументы командной строки (высший приоритет)
    parser = argparse.ArgumentParser(description="Gateway 2 для КУБ-1063 - FC=03 + FC=04")
    parser.add_argument("--port", type=int, help="Modbus TCP port (default: config.json or 5022)")
    parser.add_argument("--config", default="config.json", help="Путь к файлу конфигурации")
    args, _ = parser.parse_known_args()
    
    if args.port:
        logging.info(f"🔧 Используем порт из аргументов: {args.port}")
        return args.port
    
    # 2. Файл конфигурации
    try:
        config = load_config()
        config_port = config.get("services", {}).get("gateway2", {}).get("port")
        if config_port:
            logging.info(f"📄 Используем порт из config.json: {config_port}")
            return config_port
    except Exception as e:
        logging.warning(f"⚠️ Ошибка чтения конфигурации: {e}")
    
    # 3. Дефолтное значение
    default_port = 5022
    logging.info(f"🔧 Используем дефолтный порт: {default_port}")
    return default_port

def create_modbus_datastore():
    """Создаёт блоки для ОБОИХ типов регистров"""
    registers = [0] * 65536
    return ModbusSequentialDataBlock(0, registers)

def convert_value_to_register(value, field_name):
    """Конвертирует значение из БД в формат регистра"""
    if value is None:
        return 0
    
    try:
        if field_name == "software_version":
            if isinstance(value, str):
                parts = value.split('.')
                if len(parts) == 2:
                    return int(parts[0]) * 100 + int(parts[1])
            return 0
        
        elif field_name in ["temp_inside", "temp_target"]:
            temp = float(value) * 10
            if temp < 0:
                return int(65536 + temp)
            return int(temp)
        
        elif field_name in ["humidity", "pressure", "nh3"]:
            val = float(value) * 10
            if val < 0:
                return int(65536 + val)
            return int(val)
        
        elif field_name in ["ventilation_level", "ventilation_target"]:
            return int(float(value) * 10)
        
        elif field_name == "ventilation_scheme":
            if isinstance(value, str):
                return 1 if "туннельная" in value.lower() else 0
            return int(value)
        
        else:
            return int(float(value))
            
    except (ValueError, TypeError):
        return 0

def update_register_in_both_stores(store, register_addr, value):
    """Записывает значение И в Holding Registers (FC=03) И в Input Registers (FC=04)"""
    try:
        with store_lock:
            # Записываем в Holding Registers (FC=03)
            store.setValues(3, register_addr, [int(value)])
            
            # ТАКЖЕ записываем в Input Registers (FC=04) 
            store.setValues(4, register_addr, [int(value)])
            
        logging.debug(f"📡 Записано в ОБА типа регистров 0x{register_addr:04X} = {int(value)}")
    except Exception as e:
        logging.error(f"❌ Ошибка записи регистра 0x{register_addr:04X}: {e}")

def update_registers_from_database(store):
    """Читает данные из БД и обновляет ОБА типа Modbus регистров"""
    try:
        data = read_data()
        
        if not data:
            logging.warning("⚠️ Нет данных в БД")
            return 0
        
        updated_count = 0
        
        for field_name, register_addr in DB_TO_REGISTER_MAP.items():
            if field_name in data and data[field_name] is not None:
                register_value = convert_value_to_register(data[field_name], field_name)
                update_register_in_both_stores(store, register_addr, register_value)
                updated_count += 1
        
        if updated_count > 0:
            logging.info(f"📊 Обновлено {updated_count} регистров (FC=03 + FC=04)")
            # Показываем ключевые значения
            temp = data.get('temp_inside')
            humidity = data.get('humidity') 
            co2 = data.get('co2')
            logging.info(f"📡 Данные: temp={temp}°C, humidity={humidity}%, CO2={co2}ppm")
        
        return updated_count
        
    except Exception as e:
        logging.error(f"❌ Ошибка чтения данных из БД: {e}")
        return 0

def run_modbus_server(context, port):
    """Запускает Modbus TCP сервер на указанном порту"""
    try:
        logging.info(f"🧲 Запуск Modbus TCP сервера на порту {port}...")
        logging.info("🔧 Поддерживает FC=03 (Holding) и FC=04 (Input) регистры")
        StartTcpServer(context=context, address=("0.0.0.0", port))
    except Exception as e:
        logging.error(f"❌ Ошибка TCP сервера: {e}")

def main():
    # Получаем порт из конфигурации
    tcp_port = get_port_config()
    
    logging.info("🚀 Запуск ИСПРАВЛЕННОГО Gateway 2 (FC=03 + FC=04)")
    logging.info(f"🔌 Modbus TCP порт: {tcp_port}")

    try:
        # Создаём контекст с ОБОИМИ типами регистров
        holding_registers = create_modbus_datastore()  # FC=03
        input_registers = create_modbus_datastore()    # FC=04
        
        store = ModbusSlaveContext(
            hr=holding_registers,  # Holding Registers (FC=03)
            ir=input_registers     # Input Registers (FC=04)  
        )
        
        context = ModbusServerContext(slaves=store, single=True)
        logging.info("✅ Modbus контекст создан (FC=03 + FC=04)")
    except Exception as e:
        logging.error(f"❌ Ошибка создания контекста: {e}")
        raise

    # Фоновый поток: читаем БД и обновляем datastore
    def update_loop():
        logging.info("🔄 Запуск цикла обновления (поддержка FC=03 + FC=04)")
        
        while True:
            try:
                updated_count = update_registers_from_database(store)
                
                if updated_count == 0:
                    logging.warning("⚠️ Нет данных для обновления")

                time.sleep(3)  # Обновляем каждые 3 секунды
                
            except Exception as e:
                logging.error(f"❌ Ошибка в цикле обновления: {e}")
                time.sleep(3)

    # Стартуем фоновый поток и TCP сервер с конфигурируемым портом
    threading.Thread(target=update_loop, daemon=True).start()
    run_modbus_server(context, tcp_port)  # Передаем порт в функцию

if __name__ == "__main__":
    main()