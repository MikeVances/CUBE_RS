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
PORT = "/dev/tty.usbserial-210"  # Исправлен порт
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