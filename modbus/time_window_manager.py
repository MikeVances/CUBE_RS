#!/usr/bin/env python3
"""
Менеджер временных окон для безопасного доступа к RS485 порту
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logging
import argparse

import threading
import time
import queue
try:
    from modbus.reader import KUB1063Reader
except Exception:
    from .reader import KUB1063Reader

class TimeWindowManager:
    def __init__(self, window_duration=5, cooldown_duration=10, serial_port="/dev/tty.usbserial-210", **reader_kwargs):
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
        
        # Запускаем поток обработки запросов
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
    
    def _worker(self):
        """Рабочий поток для обработки запросов к RS485"""
        logging.info("🔄 Запуск менеджера временных окон RS485")
        while self.running:
            try:
                current_time = time.time()
                
                # Проверяем, можно ли открыть новое окно
                if (self.current_window is None and 
                    current_time - self.last_window_end >= self.cooldown_duration):
                    
                    # Открываем окно доступа
                    with self.lock:
                        self.current_window = {
                            'start_time': current_time,
                            'end_time': current_time + self.window_duration
                        }
                    
                    logging.info(f"🪟 Открыто окно доступа к RS485 (до {self.window_duration}с)")
                    
                    # Обрабатываем все запросы в окне
                    window_start = current_time
                    while (time.time() - window_start < self.window_duration and 
                           self.running):
                        
                        try:
                            # Получаем запрос из очереди (неблокирующий)
                            request = self.request_queue.get_nowait()
                            self._process_request(request)
                        except queue.Empty:
                            time.sleep(0.1)
                    
                    # Закрываем окно
                    with self.lock:
                        self.current_window = None
                        self.last_window_end = time.time()
                    
                    logging.info(f"🔒 Окно доступа к RS485 закрыто (cooldown {self.cooldown_duration}с)")
                
                time.sleep(0.1)
                
            except Exception as e:
                logging.error(f"❌ Ошибка в менеджере временных окон: {e}")
                time.sleep(1)
    
    def _process_request(self, request):
        """Обработка запроса к RS485"""
        try:
            reader = KUB1063Reader(port=self.serial_port, **self.reader_kwargs)
            
            if request['type'] == 'read_all':
                # Чтение всех данных
                data = reader.read_all()
                request['callback'](data)
                
            elif request['type'] == 'read_register':
                # Чтение конкретного регистра
                value = reader.read_register(request['register'])
                request['callback'](value)
            
            # KUB1063Reader автоматически закрывает соединение в read_all()
            # reader.close() не нужен
            
        except Exception as e:
            logging.error(f"❌ Ошибка обработки запроса: {e}")
            request['callback'](None)
    
    def request_read_all(self, callback):
        """Запрос на чтение всех данных"""
        request = {
            'type': 'read_all',
            'callback': callback,
            'timestamp': time.time()
        }
        self.request_queue.put(request)
        logging.info(f"📋 Запрос на чтение всех данных добавлен в очередь")
    
    def request_read_register(self, register, callback):
        """Запрос на чтение конкретного регистра"""
        request = {
            'type': 'read_register',
            'register': register,
            'callback': callback,
            'timestamp': time.time()
        }
        self.request_queue.put(request)
        logging.info(f"📋 Запрос на чтение регистра 0x{register:04X} добавлен в очередь")
    
    def get_window_status(self):
        """Получение статуса текущего окна"""
        with self.lock:
            if self.current_window:
                remaining = self.current_window['end_time'] - time.time()
                return {
                    'window_open': True,
                    'remaining_time': max(0, remaining),
                    'total_duration': self.window_duration
                }
            else:
                time_since_last = time.time() - self.last_window_end
                return {
                    'window_open': False,
                    'time_since_last': time_since_last,
                    'cooldown_remaining': max(0, self.cooldown_duration - time_since_last)
                }
    
    def stop(self):
        """Остановка менеджера"""
        self.running = False

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
            _time_window_manager = TimeWindowManager(serial_port=serial_port or "/dev/tty.usbserial-210", **reader_kwargs)
        return _time_window_manager

def request_rs485_read_all(callback):
    """Запрос на чтение всех данных через временные окна"""
    manager = get_time_window_manager()
    manager.request_read_all(callback)

def request_rs485_read_register(register, callback):
    """Запрос на чтение регистра через временные окна"""
    manager = get_time_window_manager()
    manager.request_read_register(register, callback)

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
    parser.add_argument("--port", dest="port", default="/dev/tty.usbserial-210", help="Serial port path, e.g. /dev/tty.usbserial-21230")
    parser.add_argument("--window", dest="window", type=int, default=5, help="Access window duration (sec)")
    parser.add_argument("--cooldown", dest="cooldown", type=int, default=10, help="Cooldown between windows (sec)")
    args = parser.parse_args()

    # Создаём глобальный менеджер с указанными параметрами
    get_time_window_manager(serial_port=args.port)
    logging.info(f"✅ TimeWindowManager инициализирован (port={args.port}, window={args.window}s, cooldown={args.cooldown}s)")

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