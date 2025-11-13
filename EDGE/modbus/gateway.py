"""
Modbus TCP‑шлюз для КУБ‑1063 (ШЛЮЗ 1)
Читает данные через TimeWindowManager (RS485) и ретранслирует их в Modbus TCP.
Сохраняет данные в SQLite для дашборда.

Использует централизованный конфиг-менеджер для всех настроек.
"""

import os
import sys

# Приоритет локального пакета поверх одноимённого PyPI-модуля
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging
import threading
import time

try:
    from pymodbus.datastore import (
        ModbusSequentialDataBlock,
        ModbusServerContext,
        ModbusSlaveContext,
    )
except ImportError:  # pymodbus >= 3.6 renamed ModbusSlaveContext → ModbusDeviceContext
    from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext
    from pymodbus.datastore.context import ModbusDeviceContext as ModbusSlaveContext
from pymodbus.server import StartTcpServer

# Импорт централизованного конфиг-менеджера
try:
    from core.config_manager import get_config

    config = get_config()
except ImportError:
    logging.error(
        "❌ Не удалось импортировать ConfigManager. Убедитесь что установлен PyYAML."
    )
    sys.exit(1)

# Безопасные импорты локальных модулей
try:
    from modbus.modbus_storage import init_db, update_data
    from modbus.time_window_manager import (
        get_time_window_manager,
        request_rs485_read_all,
        request_rs485_read_register,
    )
    from modbus.writer import KUB1063Writer
except ImportError:
    try:
        from .modbus_storage import init_db, update_data
        from .time_window_manager import (
            get_time_window_manager,
            request_rs485_read_all,
            request_rs485_read_register,
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

try:
    from ..core.log_filter import get_secure_logger
    logger = get_secure_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)

# Глобальная блокировка для потокобезопасной работы с хранилищем регистров
store_lock = threading.Lock()

# Получаем список регистров для чтения из конфига
REGISTERS_TO_READ = []
for reg_name, reg_addr in config.get_all_modbus_registers().items():
    # Конвертируем строковый адрес в int
    if isinstance(reg_addr, str):
        if reg_addr.startswith("0x"):
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

    logging.info(
        f"📊 Ретранслировано {updated_count} регистров из {len(REGISTERS_TO_READ)}"
    )
    return updated_count


def run_modbus_server(context):
    """Запускает Modbus TCP‑сервер на настроенном порту."""
    try:
        logger.info(f"🧲 Запуск Modbus TCP‑сервера на порту {MODBUS_TCP_PORT}…")
        StartTcpServer(context=context, address=("0.0.0.0", MODBUS_TCP_PORT))
    except Exception as e:
        logger.error(f"❌ Ошибка TCP сервера: {e}")


def main():
    parser = argparse.ArgumentParser(description="EDGE Modbus Gateway")
    parser.add_argument("--port", dest="serial_port", help="RS485 serial port override")
    parser.add_argument(
        "--modbus-port", dest="modbus_port", type=int, help="Modbus TCP port override"
    )
    args = parser.parse_args()

    global SERIAL_PORT, MODBUS_TCP_PORT
    if args.serial_port:
        SERIAL_PORT = args.serial_port
        config.rs485.port = args.serial_port
    if args.modbus_port:
        MODBUS_TCP_PORT = args.modbus_port
        config.modbus_tcp.port = args.modbus_port

    logger.info("🚀 Запуск MULTI-DEVICE Modbus TCP Gateway")
    logger.info(f"⚙️ Конфигурация: порт {MODBUS_TCP_PORT}, RS485: {SERIAL_PORT}")

    # Загружаем реестр устройств
    try:
        from core.device_registry import get_device_registry
        device_registry = get_device_registry()
        devices = device_registry.get_all_devices(enabled_only=True)
        logger.info(f"📋 Найдено {len(devices)} активных устройств в реестре")
        for device in devices:
            logger.info(f"  • {device.name} (slave_id={device.slave_id}, type={device.device_type.value})")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки реестра устройств: {e}")
        return

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

    # Фоновый поток: периодически опрашиваем ВСЕ устройства и обновляем datastore + БД
    def update_loop():
        logger.info("🔄 Запуск цикла ретрансляции данных для всех устройств")

        while True:
            try:
                # Опрашиваем каждое устройство по очереди
                for device in devices:
                    device_name = device.name
                    slave_id = device.slave_id

                    logger.info(f"📡 Опрос устройства: {device_name} (slave_id={slave_id})")

                    data_result = [None]

                    def data_callback(data, dev_name=device_name, dev_info=device):
                        logger.info(
                            "🔔 Callback для %s (slave_id=%s): %s",
                            dev_name,
                            dev_info.slave_id,
                            data,
                        )
                        data_result[0] = data or {}

                        try:
                            raw_payload = data_result[0] if data_result[0] else {}
                            connection_status = raw_payload.get("connection_status") or (
                                "connected" if raw_payload else "error"
                            )
                            last_error = raw_payload.get("error")
                            payload = {
                                key: value
                                for key, value in raw_payload.items()
                                if key not in {"connection_status", "error", "last_error"}
                            }

                            update_data(
                                device_id=dev_info.device_id,
                                slave_id=dev_info.slave_id,
                                device_type=dev_info.device_type.value,
                                connection_status=connection_status,
                                last_error=last_error,
                                **payload,
                            )
                            logger.info("💾 Данные от %s сохранены в БД", dev_name)
                        except Exception as e:
                            logger.error(
                                "❌ Ошибка сохранения данных от %s: %s", dev_name, e
                            )
                            import traceback

                            logger.error(traceback.format_exc())

                    logging.info(f"📤 Отправка запроса для slave_id={slave_id}")
                    request_rs485_read_all(data_callback, slave_id=slave_id)

                    # Ждём ответ до 20 секунд
                    start_time = time.time()
                    while data_result[0] is None and time.time() - start_time < 20:
                        time.sleep(0.1)

                    data = data_result[0]
                    if data and data.get("connection_status") == "connected":
                        logging.info(
                            f"📊 {device_name}: temp={data.get('temp_inside')}°C, humidity={data.get('humidity')}%, CO2={data.get('co2')}ppm"
                        )

                        try:
                            # Ретранслируем регистры в Modbus TCP
                            # TODO: Учитывать slave_id при ретрансляции
                            updated_count = read_and_retranslate_all_registers(store)
                            logging.info(f"📡 {device_name}: ретранслировано {updated_count} регистров")
                        except Exception as e:
                            logging.error(f"❌ Ошибка ретрансляции для {device_name}: {e}")
                    else:
                        logging.warning(
                            f"⚠️ Нет связи с {device_name} (slave_id={slave_id})"
                        )
                        update_data(
                            device_id=device.device_id,
                            slave_id=device.slave_id,
                            device_type=device.device_type.value,
                            connection_status="error",
                            last_error="timeout",
                        )

                    # Небольшая пауза между устройствами
                    time.sleep(2)

                # Пауза перед следующим циклом опроса всех устройств
                time.sleep(30)

            except Exception as e:
                logging.error(f"❌ Ошибка в цикле ретрансляции: {e}")
                time.sleep(3)

    # Стартуем фоновый поток и TCP‑сервер
    update_thread = threading.Thread(target=update_loop, daemon=False)
    update_thread.start()
    run_modbus_server(context)


if __name__ == "__main__":
    main()
