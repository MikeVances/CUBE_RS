#!/usr/bin/env python3
"""
Пример использования улучшенного Modbus протокола
Демонстрация паттернов из ST_RS в действии
"""

import serial
import time
from typing import Optional, List

# Импортируем новые типизированные классы
from modbus.protocol import (
    ReadHoldingRegistersRequest,
    ReadHoldingRegistersResponse,
    WriteSingleRegisterRequest,
    WriteSingleRegisterResponse,
    ModbusExceptionCode,
)


class ImprovedModbusReader:
    """
    Улучшенный Modbus Reader с использованием паттернов из ST_RS

    Основные улучшения:
    1. Fluent Interface для построения сообщений
    2. Типизированные Request/Response классы
    3. Автоматическая валидация CRC
    4. Явная обработка exception кодов
    """

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 2.0):
        """
        Инициализация reader'а

        Args:
            port: Последовательный порт (например, /dev/ttyUSB0)
            baudrate: Скорость передачи
            timeout: Timeout в секундах
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial: Optional[serial.Serial] = None

    def connect(self) -> bool:
        """Подключение к порту"""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS
            )
            print(f"✅ Подключено к {self.port}")
            return True
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            return False

    def disconnect(self):
        """Отключение от порта"""
        if self.serial and self.serial.is_open:
            self.serial.close()
            print(f"🔌 Отключено от {self.port}")

    def read_holding_registers(
        self,
        slave_id: int,
        start_address: int,
        count: int
    ) -> Optional[ReadHoldingRegistersResponse]:
        """
        Чтение Holding Registers с типизированными классами

        Args:
            slave_id: ID устройства
            start_address: Начальный адрес регистра
            count: Количество регистров

        Returns:
            Типизированный ответ или None при ошибке
        """
        if not self.serial or not self.serial.is_open:
            print("❌ Порт не открыт")
            return None

        try:
            # 1. Создаём типизированный запрос (паттерн из ST_RS)
            request = ReadHoldingRegistersRequest(
                slave_id=slave_id,
                start_address=start_address,
                count=count
            )

            # 2. Строим бинарное сообщение через Fluent Interface
            message = request.build()

            print(f"📤 Отправка: {message.hex(' ')}")
            print(f"   Request: {request}")

            # 3. Отправляем
            self.serial.write(message)

            # 4. Читаем ответ
            # Минимум: slave_id + func + byte_count + CRC (5 байт)
            # Максимум: 5 + (count * 2) байт
            expected_bytes = 5 + (count * 2)
            response_data = self.serial.read(expected_bytes)

            if not response_data:
                print("❌ Timeout: устройство не ответило")
                return None

            print(f"📥 Получено: {response_data.hex(' ')} ({len(response_data)} байт)")

            # 5. Парсим типизированный ответ
            response = ReadHoldingRegistersResponse.parse(response_data)

            # 6. Проверяем успешность
            if response.is_exception():
                exception_desc = ModbusExceptionCode.get_description(response.exception_code)
                print(f"⚠️  Modbus Exception: {exception_desc}")
            else:
                print(f"✅ Успешно прочитано {len(response.registers)} регистров")
                for i, value in enumerate(response.registers):
                    addr = start_address + i
                    print(f"   Reg[0x{addr:04X}] = {value} (0x{value:04X})")

            return response

        except ValueError as e:
            print(f"❌ Ошибка парсинга: {e}")
            return None
        except Exception as e:
            print(f"❌ Ошибка связи: {e}")
            return None

    def write_single_register(
        self,
        slave_id: int,
        address: int,
        value: int
    ) -> Optional[WriteSingleRegisterResponse]:
        """
        Запись одного регистра с типизированными классами

        Args:
            slave_id: ID устройства
            address: Адрес регистра
            value: Значение для записи

        Returns:
            Типизированный ответ или None при ошибке
        """
        if not self.serial or not self.serial.is_open:
            print("❌ Порт не открыт")
            return None

        try:
            # 1. Создаём типизированный запрос
            request = WriteSingleRegisterRequest(
                slave_id=slave_id,
                address=address,
                value=value
            )

            # 2. Строим сообщение
            message = request.build()

            print(f"📤 Отправка: {message.hex(' ')}")
            print(f"   Request: {request}")

            # 3. Отправляем
            self.serial.write(message)

            # 4. Читаем echo ответ (8 байт)
            response_data = self.serial.read(8)

            if not response_data:
                print("❌ Timeout: устройство не ответило")
                return None

            print(f"📥 Получено: {response_data.hex(' ')}")

            # 5. Парсим ответ
            response = WriteSingleRegisterResponse.parse(response_data)

            # 6. Проверяем успешность
            if response.is_exception():
                exception_desc = ModbusExceptionCode.get_description(response.exception_code)
                print(f"⚠️  Modbus Exception: {exception_desc}")
            else:
                print(f"✅ Успешно записано: Reg[0x{response.address:04X}] = {response.value}")

            return response

        except ValueError as e:
            print(f"❌ Ошибка парсинга: {e}")
            return None
        except Exception as e:
            print(f"❌ Ошибка связи: {e}")
            return None

    def read_multiple_ranges(
        self,
        slave_id: int,
        ranges: List[tuple]
    ) -> dict:
        """
        Чтение нескольких диапазонов регистров

        Args:
            slave_id: ID устройства
            ranges: Список (start_address, count)

        Returns:
            Словарь {address: value}
        """
        all_registers = {}

        for start_addr, count in ranges:
            print(f"\n📖 Чтение диапазона: 0x{start_addr:04X} - 0x{start_addr + count - 1:04X}")

            response = self.read_holding_registers(slave_id, start_addr, count)

            if response and response.is_success():
                for i, value in enumerate(response.registers):
                    all_registers[start_addr + i] = value

            # Небольшая пауза между запросами
            time.sleep(0.1)

        return all_registers


# ============================================================================
# Примеры использования
# ============================================================================

def example_read_vfd_inverter():
    """Пример: чтение данных VFD инвертора"""
    print("=" * 70)
    print("ПРИМЕР: Чтение данных VFD инвертора")
    print("=" * 70)

    reader = ImprovedModbusReader(
        port="/dev/cu.usbserial-2130",
        baudrate=9600,
        timeout=2.0
    )

    if not reader.connect():
        return

    try:
        # Читаем основные регистры VFD (из vfd_inverter.py)
        ranges = [
            (0x1000, 10),  # Статус и частоты
            (0x100A, 10),  # Напряжение и ток
            (0x1014, 10),  # Температуры и мощность
        ]

        all_data = reader.read_multiple_ranges(slave_id=1, ranges=ranges)

        print(f"\n📊 Итого прочитано {len(all_data)} регистров:")
        for addr, value in sorted(all_data.items()):
            print(f"   0x{addr:04X}: {value}")

    finally:
        reader.disconnect()


def example_write_register():
    """Пример: запись регистра"""
    print("\n" + "=" * 70)
    print("ПРИМЕР: Запись регистра")
    print("=" * 70)

    reader = ImprovedModbusReader(
        port="/dev/cu.usbserial-2130",
        baudrate=9600,
        timeout=2.0
    )

    if not reader.connect():
        return

    try:
        # Записываем тестовое значение
        response = reader.write_single_register(
            slave_id=1,
            address=0x2000,
            value=0x1234
        )

        if response and response.is_success():
            print("\n✅ Запись выполнена успешно!")

    finally:
        reader.disconnect()


def example_error_handling():
    """Пример: обработка ошибок"""
    print("\n" + "=" * 70)
    print("ПРИМЕР: Обработка Modbus exceptions")
    print("=" * 70)

    reader = ImprovedModbusReader(
        port="/dev/cu.usbserial-2130",
        baudrate=9600,
        timeout=2.0
    )

    if not reader.connect():
        return

    try:
        # Пытаемся прочитать несуществующий адрес
        print("\n🔍 Попытка чтения несуществующего адреса...")
        response = reader.read_holding_registers(
            slave_id=1,
            start_address=0xFFFF,  # Заведомо неверный адрес
            count=1
        )

        if response:
            if response.is_exception():
                print(f"\n⚠️  Ожидаемая ошибка получена:")
                print(f"   Exception Code: 0x{response.exception_code:02X}")
                print(f"   Описание: {ModbusExceptionCode.get_description(response.exception_code)}")

    finally:
        reader.disconnect()


def example_compare_old_vs_new():
    """Сравнение старого и нового подходов"""
    print("\n" + "=" * 70)
    print("СРАВНЕНИЕ: Старый vs Новый подход")
    print("=" * 70)

    print("\n❌ Старый подход (без типизации):")
    print("""
    # Ручное построение сообщения
    message = bytearray()
    message.append(slave_id)
    message.append(0x03)
    message.extend(address.to_bytes(2, 'big'))
    message.extend(count.to_bytes(2, 'big'))
    crc = calculate_crc16(message)
    message.extend(crc.to_bytes(2, 'little'))

    # Ручной парсинг ответа
    if len(response) < 5:
        return None
    slave = response[0]
    func = response[1]
    byte_count = response[2]
    registers = []
    for i in range(3, 3 + byte_count, 2):
        value = int.from_bytes(response[i:i+2], 'big')
        registers.append(value)
    """)

    print("\n✅ Новый подход (типизированный):")
    print("""
    # Типизированный запрос с валидацией
    request = ReadHoldingRegistersRequest(
        slave_id=1,
        start_address=0x1000,
        count=10
    )

    # Fluent Interface для построения
    message = request.build()

    # Типизированный ответ с автоматическим парсингом
    response = ReadHoldingRegistersResponse.parse(response_data)

    # IDE знает типы! Автодополнение работает
    if response.is_success():
        for register_value in response.registers:
            print(register_value)  # <- IDE знает что это int
    """)

    print("\n📊 Преимущества нового подхода:")
    print("   ✅ Type Safety - IDE ловит ошибки на этапе написания")
    print("   ✅ Читаемость - код самодокументирующийся")
    print("   ✅ Валидация - автоматическая проверка параметров")
    print("   ✅ Тестируемость - легко мокать и тестировать")
    print("   ✅ Поддерживаемость - легко добавлять новые функции")


if __name__ == "__main__":
    # Запускаем примеры
    example_compare_old_vs_new()

    # Раскомментируйте для реального тестирования с устройством
    # example_read_vfd_inverter()
    # example_write_register()
    # example_error_handling()
