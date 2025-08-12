"""
Объединенная Reader + Writer система для КУБ-1063
Централизованное управление чтением и записью с полным аудитом
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# Импорты наших компонентов
from .reader import KUB1063Reader
from .writer import KUB1063Writer, WriteCommand, CommandStatus
from .time_window_manager import get_time_window_manager
from .modbus_storage import init_db, read_data, update_data

logger = logging.getLogger(__name__)

class UnifiedKUBSystem:
    """
    Объединенная система Reader + Writer для КУБ-1063
    
    Функции:
    - Централизованное чтение данных через Reader
    - Управление командами записи через Writer  
    - Координация доступа к RS485 через TimeWindowManager
    - Полный аудит операций
    - Статистика и мониторинг
    """
    
    def __init__(self, config_file: str = "config.json"):
        self.config = self._load_config(config_file)
        
        # Компоненты системы
        self.reader = None
        self.writer = None
        self.time_window_manager = None
        
        # Состояние системы
        self.is_running = False
        self.reader_thread = None
        self.stats_update_thread = None
        
        # Статистика
        self.system_stats = {
            'start_time': None,
            'uptime_seconds': 0,
            'reader_cycles': 0,
            'writer_commands': 0,
            'last_successful_read': None,
            'last_successful_write': None,
            'rs485_conflicts': 0
        }
        
        logger.info("🎯 UnifiedKUBSystem инициализирован")
    
    def _load_config(self, config_file: str) -> dict:
        """Загрузка конфигурации"""
        config_path = Path(config_file)
        
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки конфигурации: {e}")
        
        # Дефолтная конфигурация
        return {
            "rs485": {
                "port": "/dev/tty.usbserial-210",
                "baudrate": 9600,
                "timeout": 2.0,
                "slave_id": 1,
                "window_duration": 5,
                "cooldown_duration": 10
            },
            "reader": {
                "enabled": True,
                "read_interval": 10,
                "retry_on_error": True,
                "max_retries": 3
            },
            "writer": {
                "enabled": True,
                "max_commands_per_cycle": 5,
                "command_timeout": 30,
                "max_retries": 3
            },
            "database": {
                "data_file": "kub_data.db",
                "commands_file": "kub_commands.db",
                "backup_enabled": True
            }
        }
    
    def initialize_components(self):
        """Инициализация всех компонентов системы"""
        
        rs485_config = self.config.get("rs485", {})
        
        try:
            # 1. TimeWindowManager - координатор доступа к RS485
            logger.info("🔧 Инициализация TimeWindowManager...")
            self.time_window_manager = get_time_window_manager(
                serial_port=rs485_config.get("port", "/dev/tty.usbserial-210"),
                window_duration=rs485_config.get("window_duration", 5),
                cooldown_duration=rs485_config.get("cooldown_duration", 10),
                baudrate=rs485_config.get("baudrate", 9600),
                slave_id=rs485_config.get("slave_id", 1)
            )
            
            # 2. Reader - система чтения
            if self.config.get("reader", {}).get("enabled", True):
                logger.info("📖 Инициализация Reader...")
                self.reader = KUB1063Reader(
                    port=rs485_config.get("port"),
                    baudrate=rs485_config.get("baudrate", 9600),
                    slave_id=rs485_config.get("slave_id", 1)
                )
            
            # 3. Writer - система записи
            if self.config.get("writer", {}).get("enabled", True):
                logger.info("✍️ Инициализация Writer...")
                self.writer = KUB1063Writer(
                    port=rs485_config.get("port"),
                    baudrate=rs485_config.get("baudrate", 9600),
                    slave_id=rs485_config.get("slave_id", 1)
                )
            
            # 4. База данных
            logger.info("🗄️ Инициализация базы данных...")
            init_db()
            
            logger.info("✅ Все компоненты инициализированы")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации компонентов: {e}")
            raise
    
    def start(self):
        """Запуск объединенной системы"""
        if self.is_running:
            logger.warning("⚠️ Система уже запущена")
            return
        
        try:
            logger.info("🚀 Запуск объединенной Reader + Writer системы...")
            
            # Инициализация компонентов
            self.initialize_components()
            
            # Запуск Writer (если включен)
            if self.writer:
                self.writer.start()
                logger.info("✍️ Writer запущен")
            
            # Запуск Reader цикла
            if self.reader:
                self.is_running = True
                self.system_stats['start_time'] = datetime.now()
                
                # Поток чтения данных
                self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
                self.reader_thread.start()
                logger.info("📖 Reader запущен")
                
                # Поток обновления статистики
                self.stats_update_thread = threading.Thread(target=self._stats_update_loop, daemon=True)
                self.stats_update_thread.start()
            
            logger.info("✅ Объединенная система запущена успешно")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска системы: {e}")
            self.stop()
            raise
    
    def _reader_loop(self):
        """Цикл чтения данных"""
        read_interval = self.config.get("reader", {}).get("read_interval", 10)
        max_retries = self.config.get("reader", {}).get("max_retries", 3)
        
        while self.is_running:
            try:
                # Читаем данные через TimeWindowManager
                data_result = [None]
                
                def read_callback(data):
                    data_result[0] = data
                
                # Запрос чтения через временные окна
                from .time_window_manager import request_rs485_read_all
                request_rs485_read_all(read_callback)
                
                # Ожидание результата
                start_time = time.time()
                while data_result[0] is None and time.time() - start_time < 20:
                    time.sleep(0.1)
                
                data = data_result[0]
                
                if data and data.get("connection_status") == "connected":
                    # Успешное чтение
                    self.system_stats['reader_cycles'] += 1
                    self.system_stats['last_successful_read'] = datetime.now()
                    
                    # Сохранение в базу данных
                    try:
                        update_data(**data)
                        logger.debug("💾 Данные сохранены в базу")
                    except Exception as e:
                        logger.error(f"❌ Ошибка сохранения данных: {e}")
                    
                    logger.info(f"📊 Цикл чтения завершен: temp={data.get('temp_inside')}°C, humidity={data.get('humidity')}%")
                    
                else:
                    logger.warning("⚠️ Нет данных от КУБ-1063")
                
                # Пауза до следующего цикла
                time.sleep(read_interval)
                
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле чтения: {e}")
                time.sleep(5)
    
    def _stats_update_loop(self):
        """Цикл обновления статистики"""
        while self.is_running:
            try:
                # Обновляем uptime
                if self.system_stats['start_time']:
                    uptime = datetime.now() - self.system_stats['start_time']
                    self.system_stats['uptime_seconds'] = int(uptime.total_seconds())
                
                # Обновляем статистику Writer
                if self.writer:
                    writer_stats = self.writer.get_statistics()
                    self.system_stats['writer_commands'] = writer_stats.get('commands_total', 0)
                    
                    # Проверяем последнюю успешную запись
                    if writer_stats.get('last_command_time'):
                        self.system_stats['last_successful_write'] = writer_stats['last_command_time']
                
                time.sleep(60)  # Обновляем статистику каждую минуту
                
            except Exception as e:
                logger.error(f"❌ Ошибка обновления статистики: {e}")
                time.sleep(60)
    
    def stop(self):
        """Остановка объединенной системы"""
        logger.info("🛑 Остановка объединенной системы...")
        
        self.is_running = False
        
        # Остановка Writer
        if self.writer:
            self.writer.stop()
            logger.info("✍️ Writer остановлен")
        
        # Ожидание завершения потоков
        if self.reader_thread and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=5)
        
        if self.stats_update_thread and self.stats_update_thread.is_alive():
            self.stats_update_thread.join(timeout=2)
        
        logger.info("✅ Объединенная система остановлена")
    
    def add_write_command(self, register: int, value: int, 
                         source_ip: str = None, user_info: str = None, 
                         priority: int = 0) -> tuple[bool, str]:
        """Добавление команды записи через Writer"""
        if not self.writer:
            return False, "Writer не инициализирован"
        
        return self.writer.add_write_command(
            register=register,
            value=value,
            source_ip=source_ip,
            user_info=user_info,
            priority=priority
        )
    
    def get_current_data(self) -> Dict[str, Any]:
        """Получение текущих данных из базы"""
        try:
            return read_data()
        except Exception as e:
            logger.error(f"❌ Ошибка чтения текущих данных: {e}")
            return {}
    
    def get_system_statistics(self) -> Dict[str, Any]:
        """Получение статистики всей системы"""
        stats = {
            "system": self.system_stats.copy(),
            "reader": {
                "enabled": self.reader is not None,
                "last_read": self.system_stats.get('last_successful_read'),
                "total_cycles": self.system_stats.get('reader_cycles', 0)
            },
            "writer": {
                "enabled": self.writer is not None
            }
        }
        
        # Добавляем статистику Writer если доступен
        if self.writer:
            writer_stats = self.writer.get_statistics()
            stats["writer"].update(writer_stats)
        
        return stats
    
    def get_writable_registers(self) -> Dict[int, Dict[str, Any]]:
        """Получение списка доступных для записи регистров"""
        if self.writer:
            return self.writer.WRITABLE_REGISTERS
        return {}
    
    def validate_write_command(self, register: int, value: int) -> tuple[bool, str]:
        """Валидация команды записи"""
        if not self.writer:
            return False, "Writer не доступен"
        
        return self.writer.validate_command(register, value)

# =============================================================================
# ПРИМЕР ИСПОЛЬЗОВАНИЯ ОБЪЕДИНЕННОЙ СИСТЕМЫ
# =============================================================================

def main():
    """Основная функция для запуска объединенной системы"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.FileHandler("unified_kub_system.log", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    
    # Создание и запуск системы
    system = UnifiedKUBSystem("config.json")
    
    try:
        system.start()
        
        # Демонстрация функций
        print("\n" + "=" * 60)
        print("🎯 ОБЪЕДИНЕННАЯ СИСТЕМА КУБ-1063 ЗАПУЩЕНА")
        print("=" * 60)
        
        # Показываем доступные регистры для записи
        writable = system.get_writable_registers()
        print(f"📝 Доступно для записи: {len(writable)} регистров")
        
        # Показываем текущие данные
        current_data = system.get_current_data()
        if current_data:
            print(f"🌡️ Температура: {current_data.get('temp_inside')}°C")
            print(f"💧 Влажность: {current_data.get('humidity')}%")
            print(f"🫁 CO2: {current_data.get('co2')} ppm")
        
        # Пример добавления команды записи
        print(f"\n✍️ Тест команды записи...")
        success, result = system.add_write_command(
            register=0x0020,  # Сброс аварий
            value=1,
            source_ip="127.0.0.1",
            user_info="admin_test"
        )
        print(f"Команда добавлена: {'✅' if success else '❌'} {result}")
        
        print(f"\n📊 СТАТИСТИКА СИСТЕМЫ:")
        stats = system.get_system_statistics()
        print(f"Время работы: {stats['system']['uptime_seconds']} сек")
        print(f"Циклов чтения: {stats['reader']['total_cycles']}")
        print(f"Команд записи: {stats['writer'].get('commands_total', 0)}")
        
        print(f"\n⚠️ Нажмите Ctrl+C для остановки")
        
        # Основной цикл
        while True:
            time.sleep(10)
            
            # Показываем статистику каждые 10 секунд
            stats = system.get_system_statistics()
            print(f"📊 Uptime: {stats['system']['uptime_seconds']}s, "
                  f"Reads: {stats['reader']['total_cycles']}, "
                  f"Writes: {stats['writer'].get('commands_total', 0)}")
    
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки...")
    
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    
    finally:
        system.stop()
        print("✅ Система остановлена")

if __name__ == "__main__":
    main()
