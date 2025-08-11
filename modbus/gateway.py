"""
Modbus TCP‑шлюз для КУБ‑1063 (ШЛЮЗ 1) - ИСПРАВЛЕННАЯ ВЕРСИЯ
Читает данные через TimeWindowManager (RS485) и ретранслирует их в Modbus TCP (порт 5021).
"""

import sys
import os
# Приоритет локального пакета поверх одноимённого PyPI-модуля
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import threading
import logging

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [GATEWAY1] %(message)s",
    handlers=[
        logging.FileHandler("gateway1.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

# Глобальная блокировка для потокобезопасной работы с хранилищем регистров
store_lock = threading.Lock()

# Маппинг данных на адреса регистров
DATA_TO_REGISTER_MAP = {
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

MODBUS_TCP_PORT = 5021
SERIAL_PORT = "/dev/tty.usbserial-210"


def create_modbus_datastore():
    """Создаёт блок Holding Registers на полный диапазон адресов (0..65535)."""
    registers = [0] * 65536
    return ModbusSequentialDataBlock(0, registers)


def convert_value_to_register(value, field_name):
    """Конвертирует значение из БД в формат регистра"""
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
        
        elif field_name in ["temp_inside", "temp_target"]:
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
        
        else:
            # Остальные как целые числа
            return int(float(value))
            
    except (ValueError, TypeError):
        return 0


def update_register_from_data(store, register_addr, value):
    """Потокобезопасно обновляет значение Holding Register."""
    try:
        with store_lock:
            store.setValues(3, register_addr, [int(value)])  # FC=3 Holding
        logging.debug(f"📡 Обновлен регистр 0x{register_addr:04X} = {int(value)}")
    except Exception as e:
        logging.error(f"❌ Ошибка обновления регистра 0x{register_addr:04X}: {e}")


def update_modbus_registers_from_data(store, data):
    """Обновляет Modbus регистры из полученных данных (НЕ читает RS485 повторно)"""
    updated_count = 0
    
    for field_name, register_addr in DATA_TO_REGISTER_MAP.items():
        if field_name in data and data[field_name] is not None:
            register_value = convert_value_to_register(data[field_name], field_name)
            update_register_from_data(store, register_addr, register_value)
            updated_count += 1
    
    logging.info(f"📡 Обновлено {updated_count} Modbus регистров из полученных данных")
    return updated_count


def run_modbus_server(context):
    """Запускает Modbus TCP‑сервер на 5021 порту."""
    try:
        logging.info(f"🧲 Запуск Modbus TCP‑сервера на порту {MODBUS_TCP_PORT}…")
        StartTcpServer(context=context, address=("0.0.0.0", MODBUS_TCP_PORT))
    except Exception as e:
        logging.error(f"❌ Ошибка TCP сервера: {e}")


def main():
    logging.info("🚀 Запуск ШЛЮЗА 1: Modbus TCP ретранслятор для КУБ‑1063")

    # Инициализация менеджера временных окон с нужным портом
    try:
        manager = get_time_window_manager(serial_port=SERIAL_PORT)
        logging.info(f"✅ TimeWindowManager инициализирован (порт: {SERIAL_PORT})")
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
                    logging.info(f"🔔 Callback вызван с данными: {data}")
                    data_result[0] = data

                logging.info("📤 Отправка запроса в TimeWindowManager…")
                request_rs485_read_all(data_callback)

                # Ждём ответ общего запроса до 20 секунд
                start_time = time.time()
                while data_result[0] is None and time.time() - start_time < 20:
                    time.sleep(0.1)

                data = data_result[0]
                if data and data.get("connection_status") == "connected":
                    logging.info(f"📊 Полученные данные: temp={data.get('temp_inside')}°C, humidity={data.get('humidity')}%, CO2={data.get('co2')}ppm")

                    # Используем полученные данные для обновления Modbus регистров
                    # БЕЗ повторного чтения RS485
                    try:
                        updated_count = update_modbus_registers_from_data(store, data)
                        logging.info(f"📡 Ретранслировано {updated_count} регистров в Modbus TCP")
                    except Exception as e:
                        logging.error(f"❌ Ошибка ретрансляции в Modbus: {e}")

                    # Сохраняем данные в SQLite для дашборда
                    try:
                        update_data(**data)
                        logging.info("💾 Данные сохранены в БД")
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
    run_modbus_server(context)


if __name__ == "__main__":
    main()