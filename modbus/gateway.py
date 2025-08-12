"""
Modbus TCP‑шлюз для КУБ‑1063 (ШЛЮЗ 1)
Читает данные через TimeWindowManager (RS485) и ретранслирует их в Modbus TCP (порт 5021).
Сохраняет данные в SQLite для дашборда.
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
        request_rs485_read_register,
        get_time_window_manager
    )
except ImportError:
    try:
        from .modbus_storage import init_db, update_data
        from .time_window_manager import (
            request_rs485_read_all,
            request_rs485_read_register,
            get_time_window_manager
        )
    except ImportError:
        # Fallback для прямого запуска
        import modbus_storage
        import time_window_manager
        init_db = modbus_storage.init_db
        update_data = modbus_storage.update_data
        request_rs485_read_all = time_window_manager.request_rs485_read_all
        request_rs485_read_register = time_window_manager.request_rs485_read_register
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

# Набор адресов, которые читаем с контроллера и кладём в Holding Registers
REGISTERS_TO_READ = [
    0x0301,  # Версия ПО
    0x0081,  # Состояние цифровых выходов (1)
    0x0082,  # Состояние цифровых выходов (2)
    0x00A2,  # Состояние цифровых выходов (3)
    0x0083,  # Отрицательное давление
    0x0084,  # Относительная влажность
    0x0085,  # Концентрация CO2
    0x0086,  # Концентрация NH3
    0x0087,  # Выход ГРВ базовой вентиляции
    0x0088,  # Выход ГРВ туннельной вентиляции
    0x0089,  # Выход демпфера
    0x00C3,  # Активные аварии
    0x00C7,  # Зарегистрированные аварии
    0x00CB,  # Активные предупреждения
    0x00CF,  # Зарегистрированные предупреждения
    0x00D0,  # Целевой уровень вентиляции
    0x00D1,  # Фактический уровень вентиляции
    0x00D2,  # Активная схема вентиляции
    0x00D3,  # Счетчик дней
    0x00D4,  # Целевая температура
    0x00D5,  # Текущая температура
    0x00D6,  # Температура активации вентиляции
]

MODBUS_TCP_PORT = 5021  # Порт для Modbus TCP
SERIAL_PORT = "/dev/tty.usbserial-210"  # Порт RS485


def create_modbus_datastore():
    """Создаёт блок Holding Registers на полный диапазон адресов (0..65535)."""
    registers = [0] * 65536
    return ModbusSequentialDataBlock(0, registers)


def update_register_from_rs485(store, register_addr, value):
    """Потокобезопасно обновляет значение Holding Register."""
    try:
        with store_lock:
            store.setValues(3, register_addr, [int(value)])  # FC=3 Holding
        logging.info(f"📡 Обновлен регистр 0x{register_addr:04X} = {int(value)}")
    except Exception as e:
        logging.error(f"❌ Ошибка обновления регистра 0x{register_addr:04X}: {e}")


def read_and_retranslate_all_registers(store):
    """Читает набор регистров через менеджер окон и пишет их в Modbus‑datastore."""
    updated_count = 0
    
    for register_addr in REGISTERS_TO_READ:
        try:
            result = [None]

            def register_callback(v):
                result[0] = v

            # Запрос одного регистра
            request_rs485_read_register(register_addr, register_callback)

            # Ждём ответ (до 20 секунд)
            start_time = time.time()
            while result[0] is None and time.time() - start_time < 20:
                time.sleep(0.1)

            if result[0] is not None:
                update_register_from_rs485(store, register_addr, result[0])
                updated_count += 1
            else:
                logging.warning(f"⚠️ Таймаут чтения регистра 0x{register_addr:04X}")

            time.sleep(0.3)  # Пауза между запросами
            
        except Exception as e:
            logging.error(f"❌ Ошибка чтения регистра 0x{register_addr:04X}: {e}")
    
    logging.info(f"📊 Ретранслировано {updated_count} регистров из {len(REGISTERS_TO_READ)}")
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

                    try:
                        # Ретранслируем регистры в Modbus TCP
                        updated_count = read_and_retranslate_all_registers(store)
                        logging.info(f"📡 Ретранслировано {updated_count} регистров")
                    except Exception as e:
                        logging.error(f"❌ Ошибка ретрансляции: {e}")

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