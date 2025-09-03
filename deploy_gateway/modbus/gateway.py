"""
Modbus TCP‑шлюз для КУБ‑1063 (ШЛЮЗ 1)
Читает данные через TimeWindowManager (RS485) и ретранслирует их в Modbus TCP.
Сохраняет данные в SQLite для дашборда.

Использует централизованный конфиг-менеджер для всех настроек.
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

# Импорт централизованного конфиг-менеджера
try:
    from core.config_manager import get_config
    config = get_config()
except ImportError:
    logging.error("❌ Не удалось импортировать ConfigManager. Убедитесь что установлен PyYAML.")
    sys.exit(1)

# Безопасные импорты локальных модулей
try:
    from modbus.modbus_storage import init_db, update_data
    from modbus.time_window_manager import (
        request_rs485_read_all,
        request_rs485_read_register,
        get_time_window_manager
    )
    from modbus.writer import KUB1063Writer
except ImportError:
    try:
        from .modbus_storage import init_db, update_data
        from .time_window_manager import (
            request_rs485_read_all,
            request_rs485_read_register,
            get_time_window_manager
        )
        from .writer import KUB1063Writer
    except ImportError:
        # Fallback для прямого запуска
        import modbus_storage
        import time_window_manager
        init_db = modbus_storage.init_db
        update_data = modbus_storage.update_data
        request_rs485_read_all = time_window_manager.request_rs485_read_all
        request_rs485_read_register = time_window_manager.request_rs485_read_register
        get_time_window_manager = time_window_manager.get_time_window_manager
        from writer import KUB1063Writer

# Настройка логирования из конфига
log_file = config.config_dir / "logs" / "gateway1.log"
log_file.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=getattr(logging, config.system.log_level),
    format="%(asctime)s %(levelname)s [GATEWAY1] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

# Глобальная блокировка для потокобезопасной работы с хранилищем регистров
store_lock = threading.Lock()

# Получаем список регистров для чтения из конфига
REGISTERS_TO_READ = []
for reg_name, reg_addr in config.get_all_modbus_registers().items():
    # Конвертируем строковый адрес в int
    if isinstance(reg_addr, str):
        if reg_addr.startswith('0x'):
            addr_int = int(reg_addr, 16)
        else:
            addr_int = int(reg_addr)
        REGISTERS_TO_READ.append(addr_int)

logger.info(f"📋 Загружено {len(REGISTERS_TO_READ)} регистров из конфигурации")

# Получаем настройки из конфиг-менеджера
MODBUS_TCP_PORT = config.modbus_tcp.port
SERIAL_PORT = config.rs485.port


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
    """Запускает Modbus TCP‑сервер на настроенном порту."""
    try:
        logger.info(f"🧲 Запуск Modbus TCP‑сервера на порту {MODBUS_TCP_PORT}…")
        StartTcpServer(context=context, address=("0.0.0.0", MODBUS_TCP_PORT))
    except Exception as e:
        logger.error(f"❌ Ошибка TCP сервера: {e}")


def main():
    logger.info("🚀 Запуск ШЛЮЗА 1: Modbus TCP ретранслятор для КУБ‑1063")
    logger.info(f"⚙️ Конфигурация: порт {MODBUS_TCP_PORT}, RS485: {SERIAL_PORT}")

    # Инициализация менеджера временных окон с нужным портом
    try:
        manager = get_time_window_manager(serial_port=SERIAL_PORT)
        logger.info(f"✅ TimeWindowManager инициализирован (порт: {SERIAL_PORT})")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации TimeWindowManager: {e}")
        return

    # Инициализация БД (SQLite) для сводных данных/дашборда
    try:
        init_db()
        logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        raise

    # Создание Modbus‑контекста (один slave, только Holding Registers)
    try:
        store = ModbusSlaveContext(hr=create_modbus_datastore())
        context = ModbusServerContext(slaves=store, single=True)
        logger.info("✅ Modbus контекст создан (65536 регистров)")
    except Exception as e:
        logger.error(f"❌ Ошибка создания контекста: {e}")
        raise

    # Запускаем Writer для обработки очереди команд (в том же процессе, чтобы разделять TimeWindowManager)
    try:
        writer = KUB1063Writer(use_time_window_manager=True)
        writer.start()
        logger.info("✍️ Writer запущен: обработка очереди write_commands активна")
    except Exception as e:
        logger.error(f"❌ Не удалось запустить Writer: {e}")

    # Фоновый поток: периодически запрашиваем RS485 и обновляем datastore + БД
    def update_loop():
        logger.info("🔄 Запуск цикла ретрансляции данных")
        
        while True:
            try:
                data_result = [None]

                def data_callback(data):
                    logger.info(f"🔔 Callback вызван с данными: {data}")
                    data_result[0] = data
                    
                    # Сохраняем данные в SQLite сразу в callback
                    try:
                        logger.info(f"🔍 Попытка сохранения данных: {list(data.keys())}")
                        update_data(**data)
                        logger.info("💾 Данные сохранены в БД")
                    except Exception as e:
                        logger.error(f"❌ Ошибка сохранения в БД: {e}")
                        import traceback
                        logger.error(traceback.format_exc())

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
                else:
                    logging.warning("⚠️ Нет связи с КУБ‑1063 или нет данных")

                time.sleep(30)  # Увеличенный интервал опроса для записи данных
                
            except Exception as e:
                logging.error(f"❌ Ошибка в цикле ретрансляции: {e}")
                time.sleep(3)

    # Стартуем фоновый поток и TCP‑сервер
    threading.Thread(target=update_loop, daemon=True).start()
    run_modbus_server(context)


if __name__ == "__main__":
    main()
