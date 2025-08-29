"""
Modbus RTU Reader for КУБ-1063
Читает значения по RS485 и возвращает словарь данных
"""

import serial
import time
import crcmod
import logging
from datetime import datetime
from typing import Dict, Optional, Any

# Настройки подключения
PORT = "/dev/tty.usbserial-21230"  # Исправлен порт
BAUDRATE = 9600
SLAVE_ID = 1
TIMEOUT = 2.0

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("reader.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# CRC16 для Modbus RTU
crc16 = crcmod.predefined.mkPredefinedCrcFun('modbus')

# Карта регистров КУБ-1063 (согласно документации)
REGISTER_MAP = {
    "software_version": 0x0301,    # Версия ПО
    "temp_inside": 0x00D5,         # Текущая температура
    "temp_target": 0x00D4,         # Целевая температура
    "humidity": 0x0084,            # Относительная влажность
    "co2": 0x0085,                 # Концентрация CO2
    "nh3": 0x0086,                 # Концентрация NH3
    "pressure": 0x0083,            # Отрицательное давление
    "ventilation_level": 0x00D1,   # Фактический уровень вентиляции
    "ventilation_target": 0x00D0,  # Целевой уровень вентиляции
    "ventilation_scheme": 0x00D2,  # Активная схема вентиляции
    "day_counter": 0x00D3,         # Счетчик дней
}

class KUB1063Reader:
    """Класс для чтения данных с КУБ-1063"""

    # =========================
    # Методы для поддержки записи (Writer API)
    # =========================

    def build_modbus_write_request(self, function_code: int, register: int, value: int) -> bytes:
        """Создание Modbus RTU запроса записи"""
        if function_code == 0x06:  # Write Single Register
            request = bytearray([
                self.slave_id,
                function_code,
                (register >> 8) & 0xFF,
                register & 0xFF,
                (value >> 8) & 0xFF,
                value & 0xFF
            ])
        elif function_code == 0x10:  # Write Multiple Registers (не реализовано)
            raise NotImplementedError("Write Multiple Registers не реализован")
        else:
            raise ValueError(f"Неподдерживаемый код функции записи: {function_code}")

        crc = crc16(request)
        request.append(crc & 0xFF)
        request.append((crc >> 8) & 0xFF)
        return bytes(request)

    def write_register(self, register: int, value: int, function_code: int = 0x06) -> bool:
        """Запись одного регистра (FC=06 - Write Single Register)"""
        if not self.serial_connection or not self.serial_connection.is_open:
            logger.error("❌ Нет подключения к устройству для записи")
            return False

        try:
            request = self.build_modbus_write_request(function_code, register, value)
            self.serial_connection.flushInput()
            self.serial_connection.flushOutput()
            self.serial_connection.write(request)
            self.serial_connection.flush()
            time.sleep(0.2)

            if self.serial_connection.in_waiting > 0:
                response = self.serial_connection.read(self.serial_connection.in_waiting)
                if len(response) >= 8 and response[0] == self.slave_id and response[1] == function_code:
                    received_crc = (response[-1] << 8) | response[-2]
                    calculated_crc = crc16(response[:-2])
                    if received_crc == calculated_crc:
                        returned_register = (response[2] << 8) | response[3]
                        returned_value = (response[4] << 8) | response[5]
                        if returned_register == register and returned_value == value:
                            logger.info(f"✅ Запись в регистр 0x{register:04X} = {value} выполнена")
                            return True
                        else:
                            logger.warning(f"⚠️ Несоответствие в ответе записи: ожидали {register:04X}={value}, получили {returned_register:04X}={returned_value}")
                    else:
                        logger.warning(f"⚠️ Ошибка CRC при записи в регистр 0x{register:04X}")
                else:
                    logger.warning(f"⚠️ Неправильный формат ответа при записи в регистр 0x{register:04X}")
            else:
                logger.warning(f"⚠️ Нет ответа при записи в регистр 0x{register:04X}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка записи регистра 0x{register:04X}: {e}")
            return False

    def write_and_verify(self, register: int, value: int) -> bool:
        """Запись с верификацией - записывает и сразу читает для проверки"""
        write_success = self.write_register(register, value)
        if not write_success:
            return False
        time.sleep(0.1)
        read_value = self.read_register(register)
        if read_value is None:
            logger.warning(f"⚠️ Не удалось прочитать регистр 0x{register:04X} для верификации")
            return False
        if read_value == value:
            logger.info(f"✅ Запись в регистр 0x{register:04X} = {value} верифицирована")
            return True
        else:
            logger.error(f"❌ Верификация записи провалена: записали {value}, прочитали {read_value}")
            return False

    def get_writable_registers(self) -> dict:
        """Получение списка доступных для записи регистров"""
        # Возвращаем те же регистры что и в Writer
        from writer import KUB1063Writer
        return KUB1063Writer.WRITABLE_REGISTERS

    def validate_write_operation(self, register: int, value: int) -> tuple[bool, str]:
        """Валидация операции записи"""
        writable = self.get_writable_registers()
        if register not in writable:
            return False, f"Регистр 0x{register:04X} недоступен для записи"
        reg_config = writable[register]
        if 'min_value' in reg_config and value < reg_config['min_value']:
            return False, f"Значение {value} меньше минимального {reg_config['min_value']}"
        if 'max_value' in reg_config and value > reg_config['max_value']:
            return False, f"Значение {value} больше максимального {reg_config['max_value']}"
        return True, ""

# --- Интеграционный тест Reader + Writer ---

    def test_reader_writer_integration():
        """Интеграционный тест для Reader и Writer"""
        print("🧪 Интеграционный тест Reader + Writer")
        print("=" * 60)
        reader = KUB1063Reader()
        from writer import KUB1063Writer
        writer = KUB1063Writer()
        writer.start()
        try:
            # 1. Тест чтения через Reader
            print("1. Тест чтения через Reader:")
            data = reader.read_all()
            if data:
                param_count = len([k for k, v in data.items() if v is not None and k not in ['timestamp', 'connection_status']])
                print(f"    ✅ Прочитано {param_count} параметров")
                temp = data.get('temp_inside')
                humidity = data.get('humidity')
                print(f"    📊 Температура: {temp if temp is not None else 'нет данных'}°C")
                print(f"    💧 Влажность: {humidity if humidity is not None else 'нет данных'}%")
            else:
                print("    ❌ Нет данных от Reader")

            # 2. Тест записи через Writer
            print("\n2. Тест записи через Writer:")
            success, result = writer.add_write_command(
                register=0x0020,  # Сброс аварий
                value=1,
                source_ip="127.0.0.1",
                user_info="integration_test"
            )
            print(f"    Команда сброса аварий: {'✅' if success else '❌'} {result}")

            # 3. Тест прямой записи через Reader
            print("\n3. Тест прямой записи через Reader:")
            if reader.connect():
                valid, msg = reader.validate_write_operation(0x0020, 1)
                print(f"    Валидация команды: {'✅' if valid else '❌'} {msg}")
                if valid:
                    write_ok = reader.write_register(0x0020, 1)
                    print(f"    Прямая запись: {'✅' if write_ok else '❌'}")
                    verify_ok = reader.write_and_verify(0x0020, 0)  # Сброс обратно
                    print(f"    Запись с верификацией: {'✅' if verify_ok else '❌'}")
                reader.disconnect()
            else:
                print("    ❌ Не удалось подключиться для прямой записи")

            # 4. Статистика Writer
            print("\n4. Статистика Writer:")
            stats = writer.get_statistics()
            for key, value in stats.items():
                print(f"    {key}: {value}")

            time.sleep(3)

            # 5. Финальная статистика
            print("\n5. Финальная статистика:")
            final_stats = writer.get_statistics()
            for key, value in final_stats.items():
                print(f"    {key}: {value}")
        finally:
            writer.stop()

    # =============================================================================
    # ПОЛНЫЙ СПИСОК ИЗМЕНЕНИЙ ДЛЯ modbus/reader.py
    # =============================================================================

    """
    ИЗМЕНЕНИЯ ДЛЯ ДОБАВЛЕНИЯ В modbus/reader.py:

    1. Добавить импорты (если нужно):
    # Уже есть: serial, time, crcmod, logging, datetime, typing

    2. Добавить новые методы в класс KUB1063Reader:
    - build_modbus_write_request()
    - write_register()
    - write_and_verify()
    - get_writable_registers()
    - validate_write_operation()

    3. Обновить комментарии в заголовке файла:
    "Modbus RTU Reader/Writer for КУБ-1063"
    "Читает и записывает значения по RS485"

    4. Добавить в конец файла тестовую функцию:
    test_reader_writer_integration()

    ОБРАТНАЯ СОВМЕСТИМОСТЬ:
    - Все существующие методы чтения остаются без изменений
    - Новые методы записи добавляются как дополнительная функциональность
    - Можно использовать только чтение, как и раньше
    """
    
    def __init__(self, port: str = PORT, baudrate: int = BAUDRATE, slave_id: int = SLAVE_ID):
        self.port = port
        self.baudrate = baudrate
        self.slave_id = slave_id
        self.serial_connection = None
        
    def build_modbus_request(self, function_code: int, register: int, count: int = 1) -> bytes:
        """Создание Modbus RTU запроса"""
        request = bytearray([
            self.slave_id,
            function_code,
            (register >> 8) & 0xFF,
            register & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF
        ])
        
        # Добавляем CRC
        crc = crc16(request)
        request.append(crc & 0xFF)
        request.append((crc >> 8) & 0xFF)
        
        return bytes(request)
    
    def connect(self) -> bool:
        """Подключение к устройству"""
        try:
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,  # Исправлено: 8N1 вместо 8E1
                stopbits=serial.STOPBITS_ONE,
                timeout=TIMEOUT,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False
            )
            logger.info(f"✅ Подключение к {self.port} установлено")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к {self.port}: {e}")
            return False
    
    def disconnect(self):
        """Отключение от устройства"""
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
            logger.info("🔒 Соединение закрыто")
    
    def is_connected(self) -> bool:
        """Проверка состояния соединения"""
        return (self.serial_connection is not None and 
                self.serial_connection.is_open)
    
    def read_register(self, register: int, function_code: int = 0x04) -> Optional[int]:
        """Чтение одного регистра"""
        if not self.serial_connection or not self.serial_connection.is_open:
            logger.error("❌ Нет подключения к устройству")
            return None
        
        try:
            # Строим запрос
            request = self.build_modbus_request(function_code, register, 1)
            
            # Очищаем буферы
            self.serial_connection.flushInput()
            self.serial_connection.flushOutput()
            
            # Отправляем запрос
            self.serial_connection.write(request)
            self.serial_connection.flush()
            
            # Ждем ответа
            time.sleep(0.2)
            
            if self.serial_connection.in_waiting > 0:
                response = self.serial_connection.read(self.serial_connection.in_waiting)
                
                # Проверяем ответ
                if len(response) >= 5 and response[0] == self.slave_id and response[1] == function_code:
                    # Проверяем CRC
                    received_crc = (response[-1] << 8) | response[-2]
                    calculated_crc = crc16(response[:-2])
                    
                    if received_crc == calculated_crc:
                        # Извлекаем значение
                        raw_value = (response[3] << 8) | response[4]
                        return raw_value
                    else:
                        logger.warning(f"⚠️ Ошибка CRC для регистра 0x{register:04X}")
                else:
                    logger.warning(f"⚠️ Неправильный формат ответа для регистра 0x{register:04X}")
            else:
                logger.warning(f"⚠️ Нет ответа для регистра 0x{register:04X}")
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка чтения регистра 0x{register:04X}: {e}")
            return None
    
    def parse_value(self, raw_value: int, register_name: str) -> Any:
        """Парсинг значения в зависимости от типа регистра"""
        if raw_value is None:
            return None
        
        # Обработка специальных значений
        if raw_value == 0xFFFF:
            return None  # Датчик отключен
        elif raw_value == 0x7FFF:
            return None  # Не инициализирован
        elif raw_value == 0x7FFE:
            return None  # Ошибка датчика
        elif raw_value >= 0xFFF0:  # Коды ошибок (0xFFFF - N)
            return None  # Датчик отключен или ошибка
        
        # Парсинг по типу регистра
        if register_name == "software_version":
            # Версия ПО: 401 -> "4.01"
            return f"{raw_value // 100}.{raw_value % 100:02d}"
        
        elif register_name in ["temp_inside", "temp_target"]:
            # Температура в десятых долях °C (знаковое число)
            if raw_value >= 0x8000:
                temp = (raw_value - 0x10000) / 10.0
            else:
                temp = raw_value / 10.0
            return round(temp, 1)
        
        elif register_name in ["humidity", "pressure", "nh3"]:
            # Параметры в десятых долях (согласно документации)
            if raw_value >= 0x8000:
                value = (raw_value - 0x10000) / 10.0
            else:
                value = raw_value / 10.0
            return round(value, 1)
        
        elif register_name in ["ventilation_level", "ventilation_target"]:
            # Вентиляция - делим на 10 (показывает 191% -> 19.1%)
            return raw_value / 10.0
        
        elif register_name in ["co2", "day_counter"]:
            # Целые числа
            return raw_value
        
        elif register_name == "ventilation_scheme":
            # 0 — базовая, 1 — туннельная
            return "базовая" if raw_value == 0 else "туннельная"
        
        else:
            # По умолчанию возвращаем как есть
            return raw_value
    
    def read_all(self) -> Dict[str, Any]:
        """Чтение всех регистров"""
        if not self.connect():
            return {}
        
        data = {
            'timestamp': datetime.now(),
            'connection_status': 'connected'
        }
        
        success_count = 0
        total_count = len(REGISTER_MAP)
        
        try:
            for name, register in REGISTER_MAP.items():
                raw_value = self.read_register(register)
                parsed_value = self.parse_value(raw_value, name)
                data[name] = parsed_value
                
                if parsed_value is not None:
                    success_count += 1
                    logger.debug(f"✅ {name}: {parsed_value}")
                else:
                    logger.debug(f"❌ {name}: нет данных")
                
                # Небольшая пауза между запросами
                time.sleep(0.1)
            
            data['success_rate'] = success_count / total_count
            logger.info(f"📊 Успешно прочитано {success_count}/{total_count} регистров")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при чтении данных: {e}")
            data['connection_status'] = 'error'
            data['error'] = str(e)
        
        finally:
            self.disconnect()
        
        return data
    
    def read_all_keep_connection(self) -> Dict[str, Any]:
        """Чтение всех регистров БЕЗ закрытия соединения (для TimeWindowManager)"""
        if not self.is_connected():
            if not self.connect():
                return {}
        
        data = {
            'timestamp': datetime.now(),
            'connection_status': 'connected'
        }
        
        success_count = 0
        total_count = len(REGISTER_MAP)
        
        try:
            for name, register in REGISTER_MAP.items():
                raw_value = self.read_register(register)
                parsed_value = self.parse_value(raw_value, name)
                data[name] = parsed_value
                
                if parsed_value is not None:
                    success_count += 1
                    logger.debug(f"✅ {name}: {parsed_value}")
                else:
                    logger.debug(f"❌ {name}: нет данных")
                
                # Небольшая пауза между запросами
                time.sleep(0.05)  # Уменьшенная пауза для производительности
            
            data['success_rate'] = success_count / total_count
            logger.debug(f"📊 Успешно прочитано {success_count}/{total_count} регистров")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при чтении данных: {e}")
            data['connection_status'] = 'error'
            data['error'] = str(e)
        
        # НЕ закрываем соединение - оставляем для переиспользования
        
        return data
    
    def write_register(self, register: int, value: int) -> bool:
        """Запись значения в регистр (для TimeWindowManager)"""
        if not self.is_connected():
            if not self.connect():
                return False
        
        try:
            # Создание Modbus RTU запроса записи (FC=06)
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
            
            # Очистка буферов
            self.serial.flushInput()
            self.serial.flushOutput()
            
            # Отправка запроса
            self.serial.write(request)
            self.serial.flush()
            
            # Ожидание ответа
            time.sleep(0.2)
            
            if self.serial.in_waiting > 0:
                response = self.serial.read(self.serial.in_waiting)
                
                # Проверка ответа
                if len(response) >= 8 and response[0] == self.slave_id and response[1] == 0x06:
                    # Проверка CRC
                    received_crc = (response[-1] << 8) | response[-2]
                    calculated_crc = crc16(response[:-2])
                    
                    if received_crc == calculated_crc:
                        # Проверка что записанное значение совпадает
                        returned_register = (response[2] << 8) | response[3]
                        returned_value = (response[4] << 8) | response[5]
                        
                        if returned_register == register and returned_value == value:
                            logger.debug(f"✅ Запись успешна: 0x{register:04X}={value}")
                            return True
                        else:
                            logger.warning(f"❌ Неверный ответ: регистр=0x{returned_register:04X}, значение={returned_value}")
                            return False
                    else:
                        logger.warning("❌ Ошибка CRC в ответе записи")
                        return False
                else:
                    logger.warning("❌ Неверный формат ответа записи")
                    return False
            else:
                logger.warning("❌ Нет ответа от устройства при записи")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка записи регистра 0x{register:04X}: {e}")
            return False

# Глобальный экземпляр читателя
_reader = KUB1063Reader()

def read_all() -> Dict[str, Any]:
    """Основная функция для использования в дашборде"""
    return _reader.read_all()

def test_connection():
    """Тест подключения"""
    reader = KUB1063Reader()
    
    print("🔍 Тестирование подключения к КУБ-1063")
    print("=" * 40)
    
    if reader.connect():
        print("✅ Подключение установлено")
        
        # Тестируем несколько ключевых регистров
        test_registers = {
            "Версия ПО": 0x0301,
            "Температура": 0x00D5,
            "Влажность": 0x0084,
            "CO2": 0x0085
        }
        
        for name, register in test_registers.items():
            raw_value = reader.read_register(register)
            if raw_value is not None:
                print(f"✅ {name}: 0x{raw_value:04X} ({raw_value})")
            else:
                print(f"❌ {name}: нет ответа")
        
        reader.disconnect()
    else:
        print("❌ Не удалось подключиться")

if __name__ == "__main__":
    # Запуск теста при прямом вызове
    test_connection()
    
    print("\n" + "=" * 50)
    print("📊 Полное чтение всех данных:")
    print("=" * 50)
    
    result = read_all()
    for key, value in result.items():
        if key != 'timestamp':
            print(f"{key:20}: {value}")
    
    if result.get('success_rate'):
        print(f"\n📈 Успешность: {result['success_rate']*100:.1f}%")