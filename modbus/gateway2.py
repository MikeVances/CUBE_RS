"""
Gateway 2 - ИСПРАВЛЕННЫЙ для поддержки FC=03 и FC=04
Записывает данные И в Holding Registers (FC=03) И в Input Registers (FC=04)
"""

import sys
import os
import time
import threading
import logging

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

def run_modbus_server(context):
    """Запускает Modbus TCP сервер на порту 5022"""
    try:
        logging.info("🧲 Запуск Modbus TCP сервера на порту 5022...")
        logging.info("🔧 Поддерживает FC=03 (Holding) и FC=04 (Input) регистры")
        StartTcpServer(context=context, address=("0.0.0.0", 5022))
    except Exception as e:
        logging.error(f"❌ Ошибка TCP сервера: {e}")

def main():
    logging.info("🚀 Запуск ИСПРАВЛЕННОГО Gateway 2 (FC=03 + FC=04)")

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

    # Стартуем фоновый поток и TCP сервер
    threading.Thread(target=update_loop, daemon=True).start()
    run_modbus_server(context)

if __name__ == "__main__":
    main()