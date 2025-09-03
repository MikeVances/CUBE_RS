"""
KUB1063Writer - система записи команд в КУБ-1063
Напарник для KUB1063Reader с поддержкой команд записи, аудита и очереди
"""

import serial
import time
import crcmod
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Используем тот же CRC что и в reader
crc16 = crcmod.predefined.mkPredefinedCrcFun('modbus')

# Настройка логирования
logger = logging.getLogger(__name__)

class CommandStatus(Enum):
    """Статусы команд записи"""
    PENDING = "pending"
    EXECUTING = "executing" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class WriteCommand:
    """Команда записи в КУБ-1063"""
    id: str
    register: int
    value: int
    source_ip: Optional[str] = None
    source_port: Optional[int] = None
    user_info: Optional[str] = None
    created_at: datetime = None
    scheduled_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    status: CommandStatus = CommandStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    priority: int = 0  # 0 = обычный, 1 = высокий, 2 = критический
    error_message: Optional[str] = None
    execution_time_ms: Optional[int] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.id is None:
            self.id = str(uuid.uuid4())

class CommandStorage:
    """Хранилище команд записи в SQLite"""
    
    def __init__(self, db_file: str = "kub_commands.db"):
        self.db_file = db_file
        self.lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """Инициализация таблиц для команд и аудита"""
        with sqlite3.connect(self.db_file) as conn:
            # Таблица команд записи
            conn.execute("""
                CREATE TABLE IF NOT EXISTS write_commands (
                    id TEXT PRIMARY KEY,
                    register INTEGER NOT NULL,
                    value INTEGER NOT NULL,
                    source_ip TEXT,
                    source_port INTEGER,
                    user_info TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    scheduled_at TIMESTAMP,
                    executed_at TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    attempts INTEGER DEFAULT 0,
                    max_attempts INTEGER DEFAULT 3,
                    priority INTEGER DEFAULT 0,
                    error_message TEXT,
                    execution_time_ms INTEGER
                )
            """)
            
            # Индексы для быстрого поиска
            conn.execute("CREATE INDEX IF NOT EXISTS idx_commands_status ON write_commands(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_commands_priority ON write_commands(priority DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_commands_created ON write_commands(created_at)")
            
            # Таблица аудита операций
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command_id TEXT,
                    event_type TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    register INTEGER,
                    old_value INTEGER,
                    new_value INTEGER,
                    source_ip TEXT,
                    user_info TEXT,
                    success BOOLEAN,
                    error_message TEXT,
                    execution_time_ms INTEGER,
                    additional_data TEXT
                )
            """)
            
            # Индекс для аудита
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_command ON audit_log(command_id)")
    
    def add_command(self, command: WriteCommand) -> str:
        """Добавление команды в очередь"""
        with self.lock, sqlite3.connect(self.db_file) as conn:
            conn.execute("""
                INSERT INTO write_commands 
                (id, register, value, source_ip, source_port, user_info,
                 created_at, scheduled_at, status, attempts, max_attempts, priority)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                command.id, command.register, command.value,
                command.source_ip, command.source_port, command.user_info,
                command.created_at, command.scheduled_at,
                command.status.value, command.attempts, command.max_attempts, command.priority
            ))
        return command.id
    
    def get_pending_commands(self) -> List[WriteCommand]:
        """Получение команд в ожидании выполнения (по приоритету)"""
        with self.lock, sqlite3.connect(self.db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM write_commands 
                WHERE status = 'pending' 
                AND (scheduled_at IS NULL OR scheduled_at <= CURRENT_TIMESTAMP)
                ORDER BY priority DESC, created_at ASC
                LIMIT 10
            """)
            
            commands = []
            for row in cursor.fetchall():
                command = WriteCommand(
                    id=row['id'],
                    register=row['register'],
                    value=row['value'],
                    source_ip=row['source_ip'],
                    source_port=row['source_port'],
                    user_info=row['user_info'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                    scheduled_at=datetime.fromisoformat(row['scheduled_at']) if row['scheduled_at'] else None,
                    executed_at=datetime.fromisoformat(row['executed_at']) if row['executed_at'] else None,
                    status=CommandStatus(row['status']),
                    attempts=row['attempts'],
                    max_attempts=row['max_attempts'],
                    priority=row['priority'],
                    error_message=row['error_message']
                )
                commands.append(command)
            
            return commands
    
    def update_command_status(self, command_id: str, status: CommandStatus, 
                            error_message: str = None, execution_time_ms: int = None):
        """Обновление статуса команды"""
        with self.lock, sqlite3.connect(self.db_file) as conn:
            if status == CommandStatus.COMPLETED or status == CommandStatus.FAILED:
                conn.execute("""
                    UPDATE write_commands 
                    SET status = ?, executed_at = CURRENT_TIMESTAMP, 
                        error_message = ?, execution_time_ms = ?
                    WHERE id = ?
                """, (status.value, error_message, execution_time_ms, command_id))
            else:
                conn.execute("""
                    UPDATE write_commands 
                    SET status = ?, error_message = ?
                    WHERE id = ?
                """, (status.value, error_message, command_id))
    
    def increment_attempts(self, command_id: str):
        """Увеличение счетчика попыток"""
        with self.lock, sqlite3.connect(self.db_file) as conn:
            conn.execute("""
                UPDATE write_commands 
                SET attempts = attempts + 1
                WHERE id = ?
            """, (command_id,))

class AuditLogger:
    """Логирование операций для аудита"""
    
    def __init__(self, command_storage: CommandStorage):
        self.storage = command_storage
    
    def log_command_received(self, command: WriteCommand):
        """Логирование получения команды"""
        self._log_event(
            command_id=command.id,
            event_type="command_received",
            register=command.register,
            new_value=command.value,
            source_ip=command.source_ip,
            user_info=command.user_info,
            success=True
        )
    
    def log_command_executing(self, command: WriteCommand):
        """Логирование начала выполнения"""
        self._log_event(
            command_id=command.id,
            event_type="command_executing",
            register=command.register,
            new_value=command.value,
            source_ip=command.source_ip,
            user_info=command.user_info,
            success=True
        )
    
    def log_command_completed(self, command: WriteCommand, execution_time_ms: int):
        """Логирование успешного выполнения"""
        self._log_event(
            command_id=command.id,
            event_type="command_completed",
            register=command.register,
            new_value=command.value,
            source_ip=command.source_ip,
            user_info=command.user_info,
            success=True,
            execution_time_ms=execution_time_ms
        )
    
    def log_command_failed(self, command: WriteCommand, error_message: str, execution_time_ms: int = None):
        """Логирование неудачного выполнения"""
        self._log_event(
            command_id=command.id,
            event_type="command_failed",
            register=command.register,
            new_value=command.value,
            source_ip=command.source_ip,
            user_info=command.user_info,
            success=False,
            error_message=error_message,
            execution_time_ms=execution_time_ms
        )
    
    def _log_event(self, **kwargs):
        """Запись события в аудит лог"""
        with sqlite3.connect(self.storage.db_file) as conn:
            conn.execute("""
                INSERT INTO audit_log 
                (command_id, event_type, register, old_value, new_value, 
                 source_ip, user_info, success, error_message, execution_time_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                kwargs.get('command_id'),
                kwargs.get('event_type'),
                kwargs.get('register'),
                kwargs.get('old_value'),
                kwargs.get('new_value'),
                kwargs.get('source_ip'),
                kwargs.get('user_info'),
                kwargs.get('success'),
                kwargs.get('error_message'),
                kwargs.get('execution_time_ms')
            ))

class KUB1063Writer:
    """
    Оптимизированная система записи команд в КУБ-1063
    Интегрированная с TimeWindowManager для координации доступа к RS485
    """
    
    # Доступные для записи регистры (из документации КУБ-1063)
    WRITABLE_REGISTERS = {
        0x0020: {
            "name": "reset_alarms",
            "description": "Сброс аварий и предупреждений",
            "min_value": 0,
            "max_value": 1,
            "access_level": "operator"
        },
        0x003F: {
            "name": "timezone",
            "description": "Часовой пояс в минутах",
            "min_value": -720,
            "max_value": 720,
            "access_level": "admin"
        },
        # Номера реле ГНВ (0x0100-0x010F)
        **{
            addr: {
                "name": f"relay_gnv_{addr-0x0100}",
                "description": f"Номер реле ГНВ {addr-0x0100}",
                "min_value": 0,
                "max_value": 255,
                "access_level": "engineer"
            } for addr in range(0x0100, 0x0110)
        },
        # Управление ГРВ и нагревателями (0x0110-0x0117)
        **{
            addr: {
                "name": f"control_{addr-0x0110}",
                "description": f"Управление {addr-0x0110}",
                "min_value": 0,
                "max_value": 1,
                "access_level": "operator"
            } for addr in range(0x0110, 0x0118)
        }
    }
    
    def __init__(self, port: str = "/dev/tty.usbserial-21230", 
                 baudrate: int = 9600, slave_id: int = 1, 
                 use_time_window_manager: bool = True):
        self.port = port
        self.baudrate = baudrate
        self.slave_id = slave_id
        self.use_time_window_manager = use_time_window_manager
        self.serial_connection = None
        
        # Компоненты системы
        self.command_storage = CommandStorage()
        self.audit_logger = AuditLogger(self.command_storage)
        
        # Статистика
        self.stats = {
            'commands_total': 0,
            'commands_success': 0,
            'commands_failed': 0,
            'commands_pending': 0,
            'last_command_time': None,
            'avg_execution_time_ms': 0
        }
        
        # Флаги состояния
        self.is_running = False
        self.processing_thread = None
        
        mode = "TimeWindowManager" if self.use_time_window_manager else "прямое соединение"
        logger.info(f"✅ KUB1063Writer инициализирован (режим: {mode})")
    
    def validate_command(self, register: int, value: int) -> tuple[bool, str]:
        """Валидация команды записи"""
        
        # Проверяем что регистр доступен для записи
        if register not in self.WRITABLE_REGISTERS:
            return False, f"Регистр 0x{register:04X} недоступен для записи"
        
        reg_config = self.WRITABLE_REGISTERS[register]
        
        # Проверяем диапазон значений
        if 'min_value' in reg_config and value < reg_config['min_value']:
            return False, f"Значение {value} меньше минимального {reg_config['min_value']}"
        
        if 'max_value' in reg_config and value > reg_config['max_value']:
            return False, f"Значение {value} больше максимального {reg_config['max_value']}"
        
        return True, ""
    
    def add_write_command(self, register: int, value: int, 
                         source_ip: str = None, source_port: int = None,
                         user_info: str = None, priority: int = 0) -> tuple[bool, str]:
        """Добавление команды записи в очередь"""
        
        # Валидация команды
        is_valid, error_msg = self.validate_command(register, value)
        if not is_valid:
            logger.warning(f"❌ Невалидная команда 0x{register:04X}={value}: {error_msg}")
            return False, error_msg
        
        # Создание команды
        command = WriteCommand(
            id=str(uuid.uuid4()),
            register=register,
            value=value,
            source_ip=source_ip,
            source_port=source_port,
            user_info=user_info,
            priority=priority
        )
        
        # Сохранение в очереди
        try:
            command_id = self.command_storage.add_command(command)
            self.audit_logger.log_command_received(command)
            
            self.stats['commands_total'] += 1
            self.stats['commands_pending'] += 1
            self.stats['last_command_time'] = datetime.now()
            
            reg_name = self.WRITABLE_REGISTERS[register]['name']
            logger.info(f"✅ Команда добавлена: 0x{register:04X} ({reg_name}) = {value}, ID: {command_id[:8]}")
            
            return True, command_id
            
        except Exception as e:
            error_msg = f"Ошибка добавления команды: {e}"
            logger.error(f"❌ {error_msg}")
            return False, error_msg
    
    def build_modbus_write_request(self, register: int, value: int) -> bytes:
        """Создание Modbus RTU запроса записи (FC=06)"""
        request = bytearray([
            self.slave_id,
            0x06,  # Function Code: Write Single Register
            (register >> 8) & 0xFF,
            register & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF
        ])
        
        # Добавляем CRC
        crc = crc16(request)
        request.append(crc & 0xFF)
        request.append((crc >> 8) & 0xFF)
        
        return bytes(request)
    
    def execute_write_command(self, command: WriteCommand) -> tuple[bool, str, int]:
        """Оптимизированное выполнение команды записи"""
        start_time = time.time()
        
        try:
            # Логируем начало выполнения
            self.audit_logger.log_command_executing(command)
            self.command_storage.update_command_status(command.id, CommandStatus.EXECUTING)
            
            if self.use_time_window_manager:
                # Используем TimeWindowManager для координации
                return self._execute_via_time_window_manager(command, start_time)
            else:
                # Прямое соединение (старый способ)
                return self._execute_direct_connection(command, start_time)
                
        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Критическая ошибка выполнения команды: {e}"
            return False, error_msg, execution_time_ms
    
    def _execute_via_time_window_manager(self, command: WriteCommand, start_time: float) -> tuple[bool, str, int]:
        """Выполнение через TimeWindowManager"""
        try:
            from .time_window_manager import request_rs485_write_register
            
            result_container = [None]
            
            def write_callback(success):
                result_container[0] = success
            
            # Отправляем запрос через TimeWindowManager
            request_rs485_write_register(command.register, command.value, write_callback)
            
            # Ожидаем результат
            timeout = 20  # секунд
            elapsed = 0
            while result_container[0] is None and elapsed < timeout:
                time.sleep(0.1)
                elapsed = time.time() - start_time
            
            execution_time_ms = int(elapsed * 1000)
            
            if result_container[0] is None:
                return False, "Таймаут выполнения команды", execution_time_ms
            elif result_container[0]:
                return True, "Команда выполнена через TimeWindowManager", execution_time_ms
            else:
                return False, "Ошибка выполнения через TimeWindowManager", execution_time_ms
                
        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return False, f"Ошибка TimeWindowManager: {e}", execution_time_ms
    
    def _execute_direct_connection(self, command: WriteCommand, start_time: float) -> tuple[bool, str, int]:
        """Прямое выполнение (старый способ)"""
        try:
            # Подключение к устройству
            if not self._connect():
                error_msg = "Не удалось подключиться к устройству"
                execution_time_ms = int((time.time() - start_time) * 1000)
                return False, error_msg, execution_time_ms
            
            # Создание и отправка запроса
            request = self.build_modbus_write_request(command.register, command.value)
            
            # Очистка буферов
            self.serial_connection.flushInput()
            self.serial_connection.flushOutput()
            
            # Отправка запроса
            self.serial_connection.write(request)
            self.serial_connection.flush()
            
            # Ожидание ответа
            time.sleep(0.2)
            
            if self.serial_connection.in_waiting > 0:
                response = self.serial_connection.read(self.serial_connection.in_waiting)
                execution_time_ms = int((time.time() - start_time) * 1000)
                
                # Проверка ответа
                if len(response) >= 8 and response[0] == self.slave_id and response[1] == 0x06:
                    # Проверка CRC
                    received_crc = (response[-1] << 8) | response[-2]
                    calculated_crc = crc16(response[:-2])
                    
                    if received_crc == calculated_crc:
                        # Проверка что записанное значение совпадает
                        returned_register = (response[2] << 8) | response[3]
                        returned_value = (response[4] << 8) | response[5]
                        
                        if returned_register == command.register and returned_value == command.value:
                            return True, "Команда выполнена успешно", execution_time_ms
                        else:
                            error_msg = f"Неверный ответ: регистр={returned_register:04X}, значение={returned_value}"
                            return False, error_msg, execution_time_ms
                    else:
                        return False, "Ошибка CRC в ответе", execution_time_ms
                else:
                    return False, "Неверный формат ответа", execution_time_ms
            else:
                execution_time_ms = int((time.time() - start_time) * 1000)
                return False, "Нет ответа от устройства", execution_time_ms
                
        finally:
            self._disconnect()
    
    def _connect(self) -> bool:
        """Подключение к устройству"""
        try:
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=2.0,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False
            )
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка подключения Writer к {self.port}: {e}")
            return False
    
    def _disconnect(self):
        """Отключение от устройства"""
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
    
    def process_command_queue(self):
        """Обработка очереди команд"""
        while self.is_running:
            try:
                # Получение команд в ожидании
                pending_commands = self.command_storage.get_pending_commands()
                
                if not pending_commands:
                    time.sleep(1)  # Нет команд, ждем
                    continue
                
                # Обработка каждой команды
                for command in pending_commands:
                    if not self.is_running:
                        break
                    
                    # Увеличиваем счетчик попыток
                    self.command_storage.increment_attempts(command.id)
                    
                    # Выполнение команды
                    success, error_msg, execution_time_ms = self.execute_write_command(command)
                    
                    if success:
                        # Успешное выполнение
                        self.command_storage.update_command_status(
                            command.id, CommandStatus.COMPLETED, 
                            execution_time_ms=execution_time_ms
                        )
                        self.audit_logger.log_command_completed(command, execution_time_ms)
                        
                        self.stats['commands_success'] += 1
                        self.stats['commands_pending'] -= 1
                        
                        reg_name = self.WRITABLE_REGISTERS[command.register]['name']
                        logger.info(f"✅ Команда выполнена: 0x{command.register:04X} ({reg_name}) = {command.value} за {execution_time_ms}мс")
                        
                    else:
                        # Неудачное выполнение
                        command.attempts += 1
                        
                        if command.attempts >= command.max_attempts:
                            # Превышено количество попыток
                            self.command_storage.update_command_status(
                                command.id, CommandStatus.FAILED,
                                error_message=error_msg, execution_time_ms=execution_time_ms
                            )
                            self.audit_logger.log_command_failed(command, error_msg, execution_time_ms)
                            
                            self.stats['commands_failed'] += 1
                            self.stats['commands_pending'] -= 1
                            
                            logger.error(f"❌ Команда провалена окончательно: {command.id[:8]} - {error_msg}")
                        else:
                            # Повторная попытка через некоторое время
                            logger.warning(f"⚠️ Команда {command.id[:8]} неудачна, попытка {command.attempts}/{command.max_attempts}: {error_msg}")
                            time.sleep(5)  # Пауза перед повтором
                    
                    # Пауза между командами
                    time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле обработки команд: {e}")
                time.sleep(5)
    
    def start(self):
        """Запуск системы Writer"""
        if self.is_running:
            logger.warning("⚠️ Writer уже запущен")
            return
        
        self.is_running = True
        self.processing_thread = threading.Thread(target=self.process_command_queue, daemon=True)
        self.processing_thread.start()
        
        logger.info("🚀 KUB1063Writer запущен")
    
    def stop(self):
        """Остановка системы Writer"""
        self.is_running = False
        
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=5)
        
        logger.info("🛑 KUB1063Writer остановлен")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получение статистики работы Writer"""
        # Обновляем количество ожидающих команд
        pending_commands = self.command_storage.get_pending_commands()
        self.stats['commands_pending'] = len(pending_commands)
        
        # Вычисляем успешность
        total_completed = self.stats['commands_success'] + self.stats['commands_failed']
        success_rate = (self.stats['commands_success'] / total_completed) if total_completed > 0 else 0
        
        return {
            **self.stats,
            'success_rate': success_rate,
            'is_running': self.is_running,
            'writable_registers_count': len(self.WRITABLE_REGISTERS),
            'using_time_window_manager': self.use_time_window_manager
        }

# Пример использования
def test_writer():
    """Тест системы Writer"""
    print("🧪 Тестирование KUB1063Writer")
    print("=" * 50)
    
    writer = KUB1063Writer()
    writer.start()
    
    try:
        # Тест валидации
        print("1. Тест валидации команд:")
        valid, msg = writer.validate_command(0x0020, 1)  # Сброс аварий
        print(f"   Сброс аварий (0x0020=1): {'✅' if valid else '❌'} {msg}")
        
        valid, msg = writer.validate_command(0x9999, 1)  # Недоступный регистр
        print(f"   Недоступный регистр (0x9999=1): {'✅' if valid else '❌'} {msg}")
        
        # Тест добавления команды
        print("\n2. Тест добавления команды:")
        success, result = writer.add_write_command(
            register=0x0020,
            value=1,
            source_ip="127.0.0.1",
            user_info="test_user",
            priority=1
        )
        print(f"   Добавление команды: {'✅' if success else '❌'} {result}")
        
        # Статистика
        print("\n3. Статистика Writer:")
        stats = writer.get_statistics()
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
        time.sleep(2)  # Даем время на обработку
        
    finally:
        writer.stop()

if __name__ == "__main__":
    test_writer()