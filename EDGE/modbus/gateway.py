"""
Modbus TCP‑шлюз для КУБ‑1063 (ШЛЮЗ 1)
Работает поверх Universal Modbus Reader и ретранслирует данные в Modbus TCP.
Сохраняет данные в SQLite для дашборда.
"""

import os
import sys

# Приоритет локального пакета поверх одноимённого PyPI-модуля
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import logging
import threading
import time
from typing import Any

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
    from modbus.universal_reader import UniversalModbusReader
except ImportError:
    try:
        from .modbus_storage import init_db, update_data
        from .universal_reader import UniversalModbusReader
    except ImportError:
        # Fallback для прямого запуска
        import modbus_storage
        from modbus.universal_reader import UniversalModbusReader  # type: ignore

        init_db = modbus_storage.init_db
        update_data = modbus_storage.update_data

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

# Получаем настройки из конфиг-менеджера
MODBUS_TCP_PORT = config.modbus_tcp.port
SERIAL_PORT = config.rs485.port


def create_modbus_datastore():
    """Создаёт блок Holding Registers на полный диапазон адресов (0..65535)."""
    registers = [0] * 65536
    return ModbusSequentialDataBlock(0, registers)


def update_store_with_raw_registers(store, raw_registers: dict[int, int]) -> int:
    """Потокобезопасно записывает карту регистров в datastore."""
    if not raw_registers:
        return 0

    updated = 0
    with store_lock:
        for register_addr, value in raw_registers.items():
            try:
                store.setValues(3, register_addr, [int(value) & 0xFFFF])
                updated += 1
            except Exception as exc:
                logging.error(
                    "❌ Ошибка обновления регистра 0x%04X: %s",
                    register_addr,
                    exc,
                )
    return updated


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

    # Создаем Universal Reader
    try:
        reader = UniversalModbusReader(
            port=SERIAL_PORT,
            baudrate=config.rs485.baudrate,
            timeout=config.rs485.timeout,
        )
        if not reader.connect():
            logger.error(f"❌ Universal Reader: не удалось подключиться к {SERIAL_PORT}")
            return
        logger.info(f"✅ Universal Reader подключен к {SERIAL_PORT}")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Universal Reader: {e}")
        return

    def _build_payload(data: dict) -> tuple[dict, dict[str, Any]]:
        excluded = {
            "connection_status",
            "error",
            "last_error",
            "device_id",
            "slave_id",
            "device_type",
            "device_name",
            "timestamp",
            "raw_registers",
            "raw_named_registers",
            "registers",
            "status",
            "alarms",
            "warnings",
        }
        payload = {k: v for k, v in data.items() if k not in excluded}
        registers_payload = data.get("registers") or {}
        payload.update(registers_payload)
        return payload, registers_payload

    # Фоновый поток: периодически опрашиваем устройства и обновляем datastore + БД
    def update_loop():
        logger.info("🔄 Запуск цикла Universal Reader для Modbus gateway")

        while True:
            for device in devices:
                device_name = device.name
                slave_id = device.slave_id
                logger.info("📡 Опрос устройства: %s (slave_id=%s)", device_name, slave_id)

                try:
                    data = reader.read_device(device)
                except Exception as exc:
                    logging.error(
                        "❌ Ошибка чтения %s (slave_id=%s): %s",
                        device_name,
                        slave_id,
                        exc,
                    )
                    data = None

                if data:
                    connection_status = data.get("connection_status", "connected")
                    last_error = data.get("error")
                    payload, registers_payload = _build_payload(data)
                    alarms_list = data.get("alarms")
                    warnings_list = data.get("warnings")
                    try:
                        update_data(
                            device_id=device.device_id,
                            slave_id=slave_id,
                            device_type=device.device_type.value,
                            connection_status=connection_status,
                            last_error=last_error,
                            registers=registers_payload,
                            alarms=alarms_list,
                            warnings=warnings_list,
                            room=device.room,
                            location=device.location,
                            **payload,
                        )
                        logger.info("💾 Данные от %s сохранены в БД", device_name)
                    except Exception as exc:
                        logging.error(
                            "❌ Ошибка сохранения данных от %s: %s",
                            device_name,
                            exc,
                        )

                    raw_map = data.get("raw_registers") or {}
                    updated = update_store_with_raw_registers(store, raw_map)
                    if updated:
                        logging.info(
                            "📡 %s: обновлено %s регистров в datastore",
                            device_name,
                            updated,
                        )
                else:
                    logging.warning(
                        "⚠️ Нет связи с %s (slave_id=%s)", device_name, slave_id
                    )
                    update_data(
                        device_id=device.device_id,
                        slave_id=slave_id,
                        device_type=device.device_type.value,
                        connection_status="error",
                        last_error="timeout",
                    )

                time.sleep(2)

            time.sleep(30)

    update_thread = threading.Thread(target=update_loop, daemon=True)
    update_thread.start()

    try:
        run_modbus_server(context)
    finally:
        try:
            reader.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
