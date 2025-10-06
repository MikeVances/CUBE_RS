#!/usr/bin/env python3
"""
Менеджер временных окон для безопасного доступа к RS485 порту
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import argparse
import logging
import queue
import threading
import time

# Импорт единой системы управления процессами
try:
    from ..core.process_manager import register_thread_service, ProcessType, ProcessPriority
    from ..core.graceful_shutdown import is_shutdown_requested
except ImportError:
    # Fallback для прямого запуска
    def register_thread_service(*args, **kwargs):
        pass
    def is_shutdown_requested():
        return False

try:
    from modbus.reader import KUB1063Reader
except Exception:
    from .reader import KUB1063Reader


class ModbusConnectionError(Exception):
    """Ошибка подключения к Modbus устройству"""

    pass


class ModbusTimeoutError(Exception):
    """Таймаут ожидания ответа от Modbus устройства"""

    pass


class TimeWindowManager:
    def __init__(
        self,
        window_duration=5,
        cooldown_duration=10,
        serial_port="/dev/tty.usbserial-2130",
        **reader_kwargs,
    ):
        """
        Инициализация менеджера временных окон

        Args:
            window_duration: Длительность окна доступа (секунды)
            cooldown_duration: Время ожидания между окнами (секунды)
            serial_port: Путь к последовательному порту RS485
            reader_kwargs: Доп. параметры для KUB1063Reader (baudrate, parity и т.п.)
        """
        self.window_duration = window_duration
        self.cooldown_duration = cooldown_duration
        self.serial_port = serial_port
        self.reader_kwargs = reader_kwargs
        self.lock = threading.Lock()
        self.current_window = None
        self.last_window_end = 0
        self.request_queue = queue.Queue()
        self.running = True

        # Единственное переиспользуемое соединение
        self.shared_reader = None
        self.connection_lock = threading.Lock()
        self.connection_errors = 0
        self.max_connection_retries = 3

        # Статистика для оптимизации
        self.stats = {
            "windows_opened": 0,
            "requests_processed": 0,
            "connection_errors": 0,
            "avg_request_time_ms": 0,
            "last_error": None,
        }

        # Запускаем поток обработки запросов
        self.worker_thread = threading.Thread(target=self._worker, daemon=True, name="time-window-manager")
        
        # Регистрируем в единой системе управления
        try:
            register_thread_service(
                name="time_window_manager_worker",
                thread=self.worker_thread,
                process_type=ProcessType.MODBUS,
                priority=ProcessPriority.HIGH
            )
        except Exception:
            pass  # Если система недоступна, продолжаем
        
        self.worker_thread.start()

    def _worker(self):
        """Рабочий поток для обработки запросов к RS485"""
        logging.info("🔄 Запуск менеджера временных окон RS485")
        while self.running and not is_shutdown_requested():
            try:
                current_time = time.time()

                # Проверяем, можно ли открыть новое окно
                if (
                    self.current_window is None
                    and current_time - self.last_window_end >= self.cooldown_duration
                ):
                    # Открываем окно доступа
                    with self.lock:
                        self.current_window = {
                            "start_time": current_time,
                            "end_time": current_time + self.window_duration,
                        }

                    logging.info(
                        f"🪟 Открыто окно доступа к RS485 (до {self.window_duration}с)"
                    )

                    # Обрабатываем все запросы в окне с оптимизацией
                    window_start = current_time
                    requests_in_window = 0

                    while (
                        time.time() - window_start < self.window_duration
                        and self.running
                    ):
                        try:
                            # Получаем запрос из очереди (неблокирующий)
                            request = self.request_queue.get_nowait()
                            self._process_request(request)
                            requests_in_window += 1
                        except queue.Empty:
                            # Если нет запросов, проверяем реже для экономии CPU
                            time.sleep(0.05 if requests_in_window > 0 else 0.1)

                    # Закрываем соединение после окна для экономии ресурсов
                    if requests_in_window > 0:
                        self._close_reader()

                    # Закрываем окно
                    with self.lock:
                        self.current_window = None
                        self.last_window_end = time.time()
                        self.stats["windows_opened"] += 1

                    logging.info(
                        f"🔒 Окно доступа к RS485 закрыто (обработано {requests_in_window} запросов, cooldown {self.cooldown_duration}с)"
                    )

                time.sleep(0.1)

            except Exception as e:
                logging.error(f"❌ Ошибка в менеджере временных окон: {e}")
                time.sleep(1)

    def _get_or_create_reader(self):
        """Получить или создать переиспользуемое соединение"""
        with self.connection_lock:
            if self.shared_reader is None:
                last_error: Exception | None = None
                for attempt in range(1, 4):
                    try:
                        logging.info(
                            f"🔌 Создаем соединение к {self.serial_port} (попытка {attempt}/3)..."
                        )
                        self.shared_reader = KUB1063Reader(
                            port=self.serial_port, **self.reader_kwargs
                        )

                        connection_result = threading.Event()
                        connection_success = [False]
                        connection_error = [None]

                        def connect_with_timeout():
                            try:
                                connection_success[0] = bool(
                                    self.shared_reader.connect()
                                )
                            except Exception as exc:
                                connection_error[0] = exc
                            finally:
                                connection_result.set()

                        connect_thread = threading.Thread(target=connect_with_timeout)
                        connect_thread.daemon = True
                        connect_thread.start()

                        # Ждем с таймаутом (5 секунд)
                        if connection_result.wait(timeout=5.0):
                            if connection_error[0]:
                                raise connection_error[0]
                            if not connection_success[0]:
                                raise ModbusConnectionError(
                                    f"Не удалось подключиться к {self.serial_port}"
                                )
                        else:
                            self.shared_reader = None
                            raise ModbusTimeoutError(
                                f"Таймаут подключения к {self.serial_port} (5с)"
                            )

                        logging.info(
                            f"✅ Создано переиспользуемое соединение к {self.serial_port}"
                        )
                        self.connection_errors = 0
                        last_error = None
                        break
                    except Exception as exc:
                        last_error = exc
                        logging.warning(
                            f"⚠️ Попытка {attempt}/3 подключения неудачна: {exc}"
                        )
                        self.shared_reader = None
                        time.sleep(1.0)

                if last_error is not None:
                    self.connection_errors += 1
                    self.stats["connection_errors"] += 1
                    self.stats["last_error"] = str(last_error)
                    raise ModbusConnectionError(
                        f"Ошибка создания соединения: {last_error}"
                    )
            return self.shared_reader

    def _close_reader(self):
        """Закрыть переиспользуемое соединение"""
        try:
            if self.connection_lock.acquire(timeout=1):
                try:
                    if self.shared_reader:
                        try:
                            # Закрываем соединение с таймаутом
                            import threading
                            disconnect_result = threading.Event()
                            disconnect_error = [None]
                            
                            def disconnect_with_timeout():
                                try:
                                    self.shared_reader.disconnect()
                                except Exception as e:
                                    disconnect_error[0] = e
                                finally:
                                    disconnect_result.set()
                            
                            # Запускаем закрытие в отдельном потоке
                            disconnect_thread = threading.Thread(target=disconnect_with_timeout)
                            disconnect_thread.daemon = True
                            disconnect_thread.start()
                            
                            # Ждем результат с таймаутом 2 секунды
                            if disconnect_result.wait(timeout=2.0):
                                if disconnect_error[0]:
                                    logging.warning(f"⚠️ Ошибка закрытия соединения: {disconnect_error[0]}")
                                else:
                                    logging.debug("🔒 Переиспользуемое соединение закрыто")
                            else:
                                logging.warning("⚠️ Timeout при закрытии соединения (2с)")
                                
                        except Exception as e:
                            logging.warning(f"⚠️ Ошибка закрытия соединения: {e}")
                        finally:
                            # ВАЖНО: всегда обнуляем reader даже при ошибке
                            self.shared_reader = None
                finally:
                    self.connection_lock.release()
            else:
                logging.warning("⚠️ Timeout при попытке закрыть соединение")
                # Принудительно обнуляем reader
                self.shared_reader = None
        except Exception as e:
            logging.warning(f"⚠️ Ошибка при закрытии соединения: {e}")
            # Принудительно обнуляем reader
            self.shared_reader = None

    def _process_request(self, request):
        """Обработка запроса к RS485 с переиспользуемым соединением"""
        start_time = time.time()

        try:
            # Получаем переиспользуемое соединение
            reader = self._get_or_create_reader()

            if request["type"] == "read_all":
                # Чтение всех данных БЕЗ закрытия соединения
                data = reader.read_all_keep_connection()
                request["callback"](data)

            elif request["type"] == "read_register":
                # Чтение конкретного регистра БЕЗ закрытия соединения
                value = reader.read_register(request["register"])
                request["callback"](value)

            elif request["type"] == "write_register":
                # Запись регистра
                success = reader.write_register(request["register"], request["value"])
                request["callback"](success)

            # Обновляем статистику
            execution_time_ms = int((time.time() - start_time) * 1000)
            self.stats["requests_processed"] += 1

            # Скользящее среднее времени выполнения
            current_avg = self.stats["avg_request_time_ms"]
            total_requests = self.stats["requests_processed"]
            self.stats["avg_request_time_ms"] = (
                (current_avg * (total_requests - 1)) + execution_time_ms
            ) / total_requests

        except (ModbusConnectionError, ModbusTimeoutError) as e:
            logging.error(f"❌ Ошибка Modbus: {e}")
            # Закрываем соединение при ошибках для пересоздания
            self._close_reader()
            request["callback"](None)

        except Exception as e:
            logging.error(f"❌ Неожиданная ошибка обработки запроса: {e}")
            self.stats["last_error"] = str(e)
            request["callback"](None)

    def request_read_all(self, callback):
        """Запрос на чтение всех данных"""
        request = {"type": "read_all", "callback": callback, "timestamp": time.time()}
        self.request_queue.put(request)
        logging.info("📋 Запрос на чтение всех данных добавлен в очередь")

    def request_read_register(self, register, callback):
        """Запрос на чтение конкретного регистра"""
        request = {
            "type": "read_register",
            "register": register,
            "callback": callback,
            "timestamp": time.time(),
        }
        self.request_queue.put(request)
        logging.info(f"📋 Запрос на чтение регистра 0x{register:04X} добавлен в очередь")

    def request_write_register(self, register, value, callback):
        """Запрос на запись регистра"""
        request = {
            "type": "write_register",
            "register": register,
            "value": value,
            "callback": callback,
            "timestamp": time.time(),
        }
        self.request_queue.put(request)
        logging.info(
            f"📋 Запрос на запись регистра 0x{register:04X}={value} добавлен в очередь"
        )

    def get_window_status(self):
        """Получение статуса текущего окна"""
        with self.lock:
            if self.current_window:
                remaining = self.current_window["end_time"] - time.time()
                return {
                    "window_open": True,
                    "remaining_time": max(0, remaining),
                    "total_duration": self.window_duration,
                }
            else:
                time_since_last = time.time() - self.last_window_end
                return {
                    "window_open": False,
                    "time_since_last": time_since_last,
                    "cooldown_remaining": max(
                        0, self.cooldown_duration - time_since_last
                    ),
                }

    def get_statistics(self):
        """Получение статистики менеджера"""
        with self.lock:
            current_status = self.get_window_status()
            return {
                **self.stats,
                "queue_size": self.request_queue.qsize(),
                "window_status": current_status,
                "connection_active": self.shared_reader is not None,
                "running": self.running,
            }

    def stop(self):
        """Остановка менеджера"""
        logging.info("🛑 Остановка TimeWindowManager...")
        self.running = False

        # Закрываем соединение с принудительным завершением
        self._close_reader()

        # Ожидаем завершения рабочего потока с таймаутом
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=3)
            
            # Если поток все еще живой, это означает что он заблокирован
            if self.worker_thread.is_alive():
                logging.warning("⚠️ Рабочий поток не завершился за 3с, принудительная остановка")
                # Поток daemon=True, поэтому он завершится при выходе из программы

        logging.info("✅ TimeWindowManager остановлен")


# Глобальный экземпляр менеджера
_time_window_manager = None
_manager_lock = threading.Lock()


def get_time_window_manager(serial_port=None, **reader_kwargs):
    """Получение глобального экземпляра менеджера временных окон.
    Первый вызов может задать параметры serial_port/reader_kwargs; последующие вызовы возвращают уже созданный экземпляр.
    """
    global _time_window_manager
    with _manager_lock:
        if _time_window_manager is None:
            _time_window_manager = TimeWindowManager(
                serial_port=serial_port or "/dev/tty.usbserial-2130", **reader_kwargs
            )
        return _time_window_manager


def stop_time_window_manager():
    """Остановить глобальный менеджер временных окон."""
    global _time_window_manager
    with _manager_lock:
        if _time_window_manager is not None:
            try:
                _time_window_manager.stop()
            finally:
                _time_window_manager = None


def request_rs485_read_all(callback):
    """Запрос на чтение всех данных через временные окна"""
    manager = get_time_window_manager()
    manager.request_read_all(callback)


def request_rs485_read_register(register, callback):
    """Запрос на чтение регистра через временные окна"""
    manager = get_time_window_manager()
    manager.request_read_register(register, callback)


def request_rs485_write_register(register, value, callback):
    """Запрос на запись регистра через временные окна"""
    manager = get_time_window_manager()
    manager.request_write_register(register, value, callback)


def get_rs485_statistics():
    """Получение статистики работы RS485"""
    manager = get_time_window_manager()
    return manager.get_statistics()


def get_rs485_window_status():
    """Получение статуса временных окон"""
    manager = get_time_window_manager()
    return manager.get_window_status()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler("time_window_manager.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    parser = argparse.ArgumentParser(description="TimeWindowManager for RS485 access")
    parser.add_argument(
        "--port",
        dest="port",
        default="/dev/tty.usbserial-2130",
        help="Serial port path, e.g. /dev/tty.usbserial-2130",
    )
    parser.add_argument(
        "--window",
        dest="window",
        type=int,
        default=5,
        help="Access window duration (sec)",
    )
    parser.add_argument(
        "--cooldown",
        dest="cooldown",
        type=int,
        default=10,
        help="Cooldown between windows (sec)",
    )
    args = parser.parse_args()

    # Создаём глобальный менеджер с указанными параметрами
    get_time_window_manager(serial_port=args.port)
    logging.info(
        f"✅ TimeWindowManager инициализирован (port={args.port}, window={args.window}s, cooldown={args.cooldown}s)"
    )

    # Обновляем параметры окна, если отличаются от дефолта
    mgr = get_time_window_manager()
    mgr.window_duration = args.window
    mgr.cooldown_duration = args.cooldown

    # Держим процесс живым
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("🛑 Остановка TimeWindowManager по Ctrl+C…")
        mgr.stop()
