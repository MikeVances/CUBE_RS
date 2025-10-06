#!/usr/bin/env python3
"""
EDGE Device Startup Script
Запускает все сервисы EDGE устройства: аутентификацию, мониторинг, telegram бот, real-time publishing

Usage:
  python start.py                           # start all EDGE services
  python start.py --disable-telegram        # start without telegram bot
  python start.py --disable-websocket       # start without websocket server
"""

import argparse
import asyncio
import logging
import os
import sys
import signal
import threading
import time
from pathlib import Path
from typing import Any, List, Optional

# Добавляем текущую директорию в путь для импортов
sys.path.insert(0, str(Path(__file__).parent))

from core.config_manager import get_config
from core.edge_authentication import EDGEAuthConfig, EDGEAuthenticatedClient
from core.device_registry import DeviceRegistry
from core.log_filter import get_secure_logger

# Опциональные импорты
try:
    from core.telegram import run_telegram_bot
    TELEGRAM_AVAILABLE = True
except ImportError as e:
    TELEGRAM_AVAILABLE = False
    print(f"⚠️ Telegram bot недоступен: {e}")

try:
    from core.edge_ping_service import run_edge_ping_service
    EDGE_PING_AVAILABLE = True
except ImportError as e:
    EDGE_PING_AVAILABLE = False
    print(f"⚠️ EDGE Ping Service недоступен: {e}")

try:
    from core.health_api import start_health_api, stop_health_api
    HEALTH_API_AVAILABLE = True
except ImportError as e:
    HEALTH_API_AVAILABLE = False
    print(f"⚠️ Health API недоступен: {e}")

try:
    from core.publishing import WebSocketServer, MQTTPublisher
    WEBSOCKET_AVAILABLE = True
    MQTT_AVAILABLE = MQTTPublisher is not None
except ImportError as e:
    WEBSOCKET_AVAILABLE = False
    MQTT_AVAILABLE = False
    print(f"⚠️ Publishing services недоступны: {e}")

try:
    from modbus.writer import KUB1063Writer
    WRITER_AVAILABLE = True
except ImportError as e:
    WRITER_AVAILABLE = False
    print(f"⚠️ Modbus writer недоступен: {e}")

try:
    from modbus.time_window_manager import stop_time_window_manager, request_rs485_read_all
    from modbus.modbus_storage import update_data
    print("✅ Успешный импорт modbus модулей")
except ImportError as e:
    print(f"❌ Ошибка импорта modbus модулей: {e}")
    def stop_time_window_manager():
        pass
    def request_rs485_read_all(callback):
        raise RuntimeError("TimeWindowManager недоступен")
    def update_data(**kwargs):
        raise RuntimeError("modbus_storage недоступен")

logger = get_secure_logger(__name__)

# Глобальная переменная для остановки
shutdown_requested = threading.Event()


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


class EDGEService:
    """Главный сервис EDGE устройства"""
    
    def __init__(self, config, offline_mode: bool = False):
        self.config = config
        self.device_registry = DeviceRegistry()
        self.auth_client = None
        self.running_tasks = []
        self.offline_mode = offline_mode
        self.offline_reason: Optional[str] = None
        self.writer = None
        self.reader_thread = None
        
    async def setup_authentication(self):
        """Настройка аутентификации с SERVER"""
        if self.offline_mode:
            self.offline_reason = self.offline_reason or "offline mode enabled via configuration"
            logger.info("🚫 Offline mode активирован — аутентификация с SERVER пропущена")
            self.auth_client = None
            return

        auth_config = EDGEAuthConfig(
            api_key=os.getenv('EDGE_API_KEY', 'demo-api-key'),
            device_id=os.getenv('EDGE_DEVICE_ID', 'edge-device-001'),
            farm_id=os.getenv('EDGE_FARM_ID', 'demo-farm'),
            server_url=os.getenv('SERVER_URL', 'http://localhost:8080')
        )
        
        self.auth_client = EDGEAuthenticatedClient(auth_config, enable_mitm_protection=True)
        
        try:
            success = await asyncio.to_thread(self.auth_client.authenticate)
        except Exception as exc:
            reason = self.auth_client.last_error or str(exc)
            logger.warning(f"⚠️ Authentication error ({reason}), переключаемся в offline mode")
            self.offline_mode = True
            self.offline_reason = reason
            self.auth_client = None
            return

        if success:
            logger.info("✅ Authentication with SERVER successful")
            return

        reason = self.auth_client.last_error or "authentication failed"
        logger.warning(f"⚠️ Authentication failed ({reason}), переключаемся в offline mode")
        self.offline_mode = True
        self.offline_reason = reason
        self.auth_client = None
    
    async def start_telegram_bot(self):
        """Запуск Telegram бота"""
        if not TELEGRAM_AVAILABLE:
            logger.warning("Telegram bot недоступен")
            return
        
        telegram_token = None
        
        try:
            from core.security_manager import get_security_manager
            security_manager = get_security_manager()
            telegram_token = security_manager.get_secure_config_value(
                "bot_secrets", "telegram.bot_token", "TELEGRAM_BOT_TOKEN"
            )
            
            try:
                secrets = security_manager.load_encrypted_config("bot_secrets")
                admin_users = secrets.get("telegram", {}).get("admin_users", [])
                if admin_users:
                    admin_str = ",".join(str(uid) for uid in admin_users)
                    os.environ["TELEGRAM_ADMIN_USERS"] = admin_str
                    logger.info(f"✅ Загружено {len(admin_users)} админов из зашифрованной конфигурации")
            except Exception as admin_err:
                logger.warning(f"Не удалось загрузить админов из зашифрованной конфигурации: {admin_err}")
                
        except Exception as e:
            logger.warning(f"Не удалось прочитать зашифрованную конфигурацию: {e}")
            telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        
        if not telegram_token:
            logger.warning("Telegram токен не найден. Настройте его через:")
            logger.warning("  python tools/telegram_secrets_cli.py set-token YOUR_TOKEN")
            logger.warning("  или установите переменную TELEGRAM_BOT_TOKEN")
            return
            
        logger.info("🚀 Запуск Telegram бота...")
        
        # Создаем задачу с проверкой отмены
        async def telegram_wrapper():
            try:
                await run_telegram_bot(telegram_token)
            except asyncio.CancelledError:
                logger.info("🛑 Telegram bot отменен")
                raise
            except Exception as e:
                logger.error(f"❌ Ошибка Telegram bot: {e}")
        
        task = asyncio.create_task(telegram_wrapper())
        self.running_tasks.append(task)
    
    async def start_websocket_server(self):
        """Запуск WebSocket сервера"""
        if not WEBSOCKET_AVAILABLE:
            logger.warning("WebSocket server недоступен") 
            return
            
        logger.info("🚀 Запуск WebSocket сервера...")
        ws_server = WebSocketServer()
        
        async def websocket_wrapper():
            try:
                await ws_server.start_server()
            except asyncio.CancelledError:
                logger.info("🛑 WebSocket server отменен")
                raise
            except Exception as e:
                logger.error(f"❌ Ошибка WebSocket server: {e}")
        
        task = asyncio.create_task(websocket_wrapper())
        self.running_tasks.append(task)
    
    async def start_mqtt_publisher(self):
        """Запуск MQTT Publisher"""
        if not MQTT_AVAILABLE:
            logger.warning("MQTT Publisher недоступен")
            return
            
        logger.info("🚀 Запуск MQTT Publisher...")
        mqtt_publisher = MQTTPublisher(self.device_registry)
        
        async def mqtt_wrapper():
            try:
                await mqtt_publisher.publish_loop()
            except asyncio.CancelledError:
                logger.info("🛑 MQTT Publisher отменен")
                raise
            except Exception as e:
                logger.error(f"❌ Ошибка MQTT Publisher: {e}")
        
        task = asyncio.create_task(mqtt_wrapper())
        self.running_tasks.append(task)
    
    async def start_edge_ping_service(self):
        """Запуск EDGE Ping Service"""
        if not EDGE_PING_AVAILABLE:
            logger.warning("EDGE Ping Service недоступен")
            return
        if self.offline_mode:
            logger.info("⏸️ EDGE Ping Service пропущен в offline режиме")
            return
            
        logger.info("🚀 Запуск EDGE Ping Service...")
        
        async def ping_wrapper():
            try:
                await run_edge_ping_service(self.device_registry)
            except asyncio.CancelledError:
                logger.info("🛑 EDGE Ping Service отменен")
                raise
            except Exception as e:
                logger.error(f"❌ Ошибка EDGE Ping Service: {e}")
        
        task = asyncio.create_task(ping_wrapper())
        self.running_tasks.append(task)
    
    async def start_health_api(self):
        """Запуск Health API"""
        if not HEALTH_API_AVAILABLE:
            logger.warning("Health API недоступен")
            return
            
        logger.info("🚀 Запуск Health API...")
        success = await start_health_api()
        if not success:
            logger.error("❌ Не удалось запустить Health API")

    async def start_modbus_writer(self):
        """Запуск Modbus writer"""
        if not WRITER_AVAILABLE:
            logger.warning("Modbus writer недоступен")
            return
        if self.writer:
            logger.debug("Modbus writer уже запущен")
            return

        try:
            from modbus.time_window_manager import get_time_window_manager

            cfg_rs485 = self.config.rs485
            get_time_window_manager(
                serial_port=cfg_rs485.port,
                window_duration=getattr(cfg_rs485, "window_duration", 5),
                cooldown_duration=getattr(cfg_rs485, "cooldown_duration", 10),
                baudrate=cfg_rs485.baudrate,
                slave_id=cfg_rs485.slave_id,
            )

            self.writer = KUB1063Writer(
                port=cfg_rs485.port,
                baudrate=cfg_rs485.baudrate,
                slave_id=cfg_rs485.slave_id,
                use_time_window_manager=True,
            )
            self.writer.start()
            logger.info("✍️ Modbus writer запущен (порт %s)", cfg_rs485.port)
            
        except Exception as e:
            self.writer = None
            logger.error(f"❌ Не удалось запустить Modbus writer: {e}")

    def start_modbus_reader(self, interval: float | None = None):
        """Запуск фонового опроса RS485"""
        if self.reader_thread and self.reader_thread.is_alive():
            return

        poll_interval = interval or float(os.getenv("EDGE_POLL_INTERVAL", "10"))
        timeout = float(os.getenv("EDGE_POLL_TIMEOUT", str(self.config.rs485.timeout * 3)))
        max_retries = int(os.getenv("EDGE_POLL_MAX_RETRIES", "3"))

        def reader_worker():
            consecutive_errors = 0
            logger.info("📖 Modbus reader запущен (интервал %.1fс)", poll_interval)
            
            while not shutdown_requested.is_set():
                try:
                    data_holder: dict[str, Any] = {}
                    error_holder: dict[str, Any] = {}
                    done = threading.Event()

                    def _callback(payload):
                        if payload is None:
                            error_holder["err"] = "timeout"
                        else:
                            data_holder["data"] = payload
                        done.set()

                    try:
                        logger.debug("📞 Вызываем request_rs485_read_all")
                        request_rs485_read_all(_callback)
                        logger.debug("📞 request_rs485_read_all завершен")
                    except Exception as exc:
                        logger.error(f"❌ Ошибка request_rs485_read_all: {exc}")
                        error_holder["err"] = str(exc)
                        done.set()

                    done.wait(timeout)
                    
                    logger.debug(f"📊 Результат ожидания: data_holder={data_holder}, error_holder={error_holder}")

                    data = data_holder.get("data")

                    if data and data.get("connection_status") == "connected":
                        try:
                            update_data(**data)
                            logger.debug("💾 Данные сохранены в базу")
                        except Exception as db_err:
                            logger.error(f"❌ Ошибка сохранения данных: {db_err}")
                        consecutive_errors = 0
                    else:
                        consecutive_errors += 1
                        logger.warning("⚠️ Не удалось получить данные от КУБ-1063 (%s/%s)", consecutive_errors, max_retries)

                        if consecutive_errors >= max_retries:
                            backoff = min(poll_interval * 2, 60)
                            logger.error("❌ Превышено число ошибок чтения, пауза %.1fс", backoff)
                            if shutdown_requested.wait(backoff):
                                break
                            consecutive_errors = 0
                            continue

                    if shutdown_requested.wait(poll_interval):
                        break

                except Exception as exc:
                    consecutive_errors += 1
                    logger.error(f"❌ Критическая ошибка Modbus reader: {exc}")
                    if shutdown_requested.wait(5):
                        break

            logger.info("📖 Modbus reader остановлен")

        # ВАЖНО: daemon=True чтобы поток не блокировал завершение программы
        self.reader_thread = threading.Thread(target=reader_worker, daemon=True, name="modbus-reader")
        self.reader_thread.start()

    async def heartbeat_loop(self):
        """Heartbeat цикл для поддержания связи с SERVER"""
        if not self.auth_client:
            return
            
        logger.info("💓 Запуск heartbeat service")
        while not shutdown_requested.is_set():
            try:
                devices_data = {}
                for device_info in self.device_registry.get_devices():
                    device_data = self.device_registry.get_device_data(device_info.device_id)
                    if device_data:
                        devices_data[device_info.device_id] = device_data
                
                success = await asyncio.to_thread(
                    self.auth_client.send_heartbeat,
                    "online",
                    {"devices_count": len(devices_data), "devices_data": devices_data}
                )
                
                if success:
                    logger.debug("💓 Heartbeat отправлен")
                else:
                    logger.warning("⚠️ Heartbeat failed")
                    
            except asyncio.CancelledError:
                logger.info("🛑 Heartbeat service отменен")
                break
            except Exception as e:
                logger.error(f"❌ Heartbeat error: {e}")
            
            try:
                await asyncio.wait_for(
                    asyncio.create_task(self._wait_for_shutdown()),
                    timeout=60
                )
                break
            except asyncio.TimeoutError:
                continue
    
    async def _wait_for_shutdown(self):
        """Асинхронное ожидание сигнала завершения"""
        while not shutdown_requested.is_set():
            await asyncio.sleep(0.1)
    
    async def run(
        self,
        enable_telegram: bool = True,
        enable_websocket: bool = True,
        enable_mqtt: bool = True,
        enable_edge_ping: bool = True,
        enable_health_api: bool = True,
        enable_writer: bool = True,
    ):
        """Запуск всех сервисов EDGE"""
        logger.info("🚀 Запуск EDGE Services...")
        
        # Настройка аутентификации
        await self.setup_authentication()

        # Загрузка устройств
        logger.info("📡 Загрузка конфигурации устройств...")
        self.device_registry.load_devices_from_config()

        # Прокидываем параметры Modbus в окружение
        try:
            os.environ["MODBUS_RTU_PORT"] = self.config.rs485.port
        except Exception:
            pass
        try:
            os.environ["MODBUS_TCP_PORT"] = str(self.config.modbus_tcp.port)
        except Exception:
            pass
        
        if self.offline_mode and self.offline_reason:
            logger.info(f"🌐 EDGE работает в offline режиме: {self.offline_reason}")
        elif self.offline_mode:
            logger.info("🌐 EDGE работает в offline режиме")

        # Запуск сервисов
        if enable_health_api:
            await self.start_health_api()
            
        if enable_telegram:
            await self.start_telegram_bot()
            
        if enable_websocket:
            await self.start_websocket_server()
            
        if enable_mqtt:
            await self.start_mqtt_publisher()
            
        if enable_edge_ping:
            await self.start_edge_ping_service()

        if enable_writer:
            await self.start_modbus_writer()
            self.start_modbus_reader()
        
        # Запуск heartbeat
        if not self.offline_mode and self.auth_client:
            async def heartbeat_wrapper():
                try:
                    await self.heartbeat_loop()
                except asyncio.CancelledError:
                    logger.info("🛑 Heartbeat service отменен")
                    raise
                except Exception as e:
                    logger.error(f"❌ Ошибка Heartbeat service: {e}")
            
            heartbeat_task = asyncio.create_task(heartbeat_wrapper())
            self.running_tasks.append(heartbeat_task)
        else:
            logger.debug("Heartbeat service отключен в offline режиме")
        
        logger.info(f"✅ EDGE Services запущены ({len(self.running_tasks)} задач)")
        
        # Ожидание завершения
        try:
            await self._wait_for_shutdown()
        except KeyboardInterrupt:
            logger.info("🛑 Получен сигнал остановки")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Корректное завершение всех сервисов"""
        logger.info("🛑 Остановка EDGE Services...")

        # Устанавливаем флаг остановки
        shutdown_requested.set()
        
        # Останавливаем Health API
        if HEALTH_API_AVAILABLE:
            try:
                await stop_health_api()
                logger.info("🛑 Health API остановлен")
            except Exception as e:
                logger.error(f"❌ Ошибка остановки Health API: {e}")

        # Останавливаем writer
        if self.writer:
            try:
                self.writer.stop()
                logger.info("🛑 Modbus writer остановлен")
            except Exception as e:
                logger.error(f"❌ Ошибка остановки Modbus writer: {e}")
            self.writer = None
            
            try:
                stop_time_window_manager()
                logger.info("🛑 TimeWindowManager остановлен")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось остановить TimeWindowManager: {e}")

        # Ждем завершения reader thread (он демонический, но лучше подождать)
        if self.reader_thread and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=3)

        # Отменяем все задачи
        cancelled_tasks = []
        for task in self.running_tasks:
            if not task.done():
                logger.info(f"🔪 Отменяем задачу")
                task.cancel()
                cancelled_tasks.append(task)
        
        # Ждем завершения всех задач с таймаутом
        if cancelled_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*cancelled_tasks, return_exceptions=True),
                    timeout=5.0
                )
                logger.info("✅ Все задачи корректно отменены")
            except asyncio.TimeoutError:
                logger.warning("⚠️ Некоторые задачи не завершились в отведенное время")
        
        logger.info("✅ EDGE Services остановлены")

        try:
            import threading

            active_threads = [t.name for t in threading.enumerate()]
            logger.debug(f"🧵 Активные потоки после shutdown: {active_threads}")
        except Exception:
            pass

        try:
            loop = asyncio.get_running_loop()
            pending = [
                f"{task.get_coro().__name__}" for task in asyncio.all_tasks(loop)
                if not task.done()
            ]
            if pending:
                logger.debug(f"🌀 Незавершенные задачи после shutdown: {pending}")
        except Exception:
            pass


async def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(description='EDGE Device Services')
    parser.add_argument('--disable-telegram', action='store_true', help='Отключить Telegram бота')
    parser.add_argument('--disable-websocket', action='store_true', help='Отключить WebSocket сервер')
    parser.add_argument('--disable-mqtt', action='store_true', help='Отключить MQTT Publisher')
    parser.add_argument('--disable-edge-ping', action='store_true', help='Отключить EDGE Ping Service')
    parser.add_argument('--disable-health-api', action='store_true', help='Отключить Health API')
    parser.add_argument('--disable-writer', action='store_true', help='Отключить Modbus writer')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])
    parser.add_argument('--offline', action='store_true', help='Запуск без подключения к SERVER (offline mode)')
    
    args = parser.parse_args()

    # Настройка логирования
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s [%(name)s] %(levelname)s - %(message)s'
    )
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Получаем event loop и устанавливаем обработчики сигналов
    loop = asyncio.get_running_loop()

    def signal_handler():
        """Обработчик сигналов"""
        logger.info("🛑 Получен сигнал остановки")
        shutdown_requested.set()

    # Устанавливаем обработчики сигналов через asyncio
    try:
        loop.add_signal_handler(signal.SIGINT, signal_handler)
        loop.add_signal_handler(signal.SIGTERM, signal_handler)
    except NotImplementedError:
        # Windows fallback
        signal.signal(signal.SIGINT, lambda s, f: signal_handler())
        signal.signal(signal.SIGTERM, lambda s, f: signal_handler())

    # Загружаем конфигурацию
    config = get_config()
    
    config_offline = getattr(getattr(config, "system", None), "offline_mode", False)
    offline_mode = args.offline or _env_flag('EDGE_OFFLINE_MODE', False) or bool(config_offline)
    
    # Создаем и запускаем сервис
    service = EDGEService(config, offline_mode=offline_mode)
    
    try:
        services_cfg = getattr(config, "services", None)

        await service.run(
            enable_telegram=(not args.disable_telegram)
            and bool(getattr(services_cfg, "telegram_enabled", True)),
            enable_websocket=(not args.disable_websocket)
            and bool(getattr(services_cfg, "websocket_enabled", False)),
            enable_mqtt=(not args.disable_mqtt)
            and bool(getattr(services_cfg, "mqtt_enabled", False)),
            enable_edge_ping=(not args.disable_edge_ping)
            and bool(getattr(services_cfg, "gateway_enabled", True)),
            enable_health_api=(not args.disable_health_api),
            enable_writer=(not args.disable_writer)
            and bool(getattr(services_cfg, "gateway_enabled", True)),
        )
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n🛑 Прервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1)
