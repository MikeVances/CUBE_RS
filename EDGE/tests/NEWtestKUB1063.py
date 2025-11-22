#!/usr/bin/env python3
"""
file: EDGE/tests/NEWtestKUB1063.py
description: Тест для проверки чтения КУБ-1063 с использованием Input Registers (FC04).
             Проверяет соответствие реального устройства документации.
author: EDGE Full-Stack RS485 Senior Engineer GPT
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import serial
import crcmod

sys.path.insert(0, str(Path(__file__).parent.parent))

# CRC16 для Modbus RTU
crc16 = crcmod.predefined.mkPredefinedCrcFun("modbus")


class ModbusRTUTester:
    """Низкоуровневый тестер Modbus RTU с поддержкой FC03 и FC04"""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.connection: serial.Serial | None = None

    def connect(self) -> bool:
        """Подключение к порту"""
        try:
            self.connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                parity='N',
                stopbits=1,
                bytesize=8,
                timeout=self.timeout
            )
            print(f"✅ Подключено к {self.port}")
            return True
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            return False

    def disconnect(self):
        """Отключение"""
        if self.connection and self.connection.is_open:
            self.connection.close()
            print(f"🔌 Отключено от {self.port}")

    def _build_read_request(
        self,
        slave_id: int,
        function_code: int,
        address: int,
        count: int = 1
    ) -> bytes:
        """
        Построение Modbus RTU запроса для чтения

        Args:
            slave_id: Адрес устройства
            function_code: 0x03 (Holding) или 0x04 (Input)
            address: Адрес регистра
            count: Количество регистров
        """
        request = bytes([
            slave_id,
            function_code,
            (address >> 8) & 0xFF,
            address & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF
        ])

        crc = crc16(request)
        request += bytes([crc & 0xFF, (crc >> 8) & 0xFF])

        return request

    def _parse_response(self, response: bytes, expected_count: int) -> list[int] | None:
        """Парсинг ответа"""
        if len(response) < 5:
            print(f"⚠️ Слишком короткий ответ: {len(response)} байт")
            return None

        # Проверка CRC
        received_crc = response[-2] | (response[-1] << 8)
        calculated_crc = crc16(response[:-2])

        if received_crc != calculated_crc:
            print(f"⚠️ Ошибка CRC: получен {received_crc:04X}, ожидался {calculated_crc:04X}")
            return None

        # Проверка на ошибку
        function_code = response[1]
        if function_code & 0x80:
            error_code = response[2]
            print(f"❌ Modbus error: function={function_code:02X}, error_code={error_code}")
            return None

        # Извлечение данных
        byte_count = response[2]
        expected_bytes = expected_count * 2

        if byte_count != expected_bytes:
            print(f"⚠️ Неожиданное количество байт: {byte_count}, ожидалось {expected_bytes}")

        # Парсинг регистров
        registers = []
        for i in range(expected_count):
            offset = 3 + (i * 2)
            if offset + 1 < len(response) - 2:
                value = (response[offset] << 8) | response[offset + 1]
                registers.append(value)

        return registers

    def read_registers(
        self,
        slave_id: int,
        address: int,
        count: int = 1,
        function_code: int = 0x03
    ) -> list[int] | None:
        """
        Чтение регистров

        Args:
            slave_id: Адрес устройства
            address: Адрес регистра
            count: Количество регистров
            function_code: 0x03 (Holding) или 0x04 (Input)
        """
        if not self.connection or not self.connection.is_open:
            print("❌ Соединение не установлено")
            return None

        try:
            # Очистка буферов
            self.connection.reset_input_buffer()
            self.connection.reset_output_buffer()

            # Отправка запроса
            request = self._build_read_request(slave_id, function_code, address, count)
            self.connection.write(request)
            time.sleep(0.1)

            # Чтение ответа
            response = self.connection.read(100)

            if not response:
                print(f"⚠️ Нет ответа от устройства")
                return None

            return self._parse_response(response, count)

        except Exception as e:
            print(f"❌ Ошибка чтения: {e}")
            return None


def test_kub1063_registers(port: str, slave_id: int):
    """
    Тестирование КУБ-1063 согласно документации

    Проверяет:
    1. Чтение через FC03 (Holding Registers) - должно НЕ работать
    2. Чтение через FC04 (Input Registers) - должно работать
    """

    tester = ModbusRTUTester(port, baudrate=9600, timeout=1.0)

    if not tester.connect():
        return False

    print(f"\n{'='*60}")
    print(f"ТЕСТ КУБ-1063 (slave_id={slave_id})")
    print(f"{'='*60}\n")

    # Тестовые регистры из документации
    test_registers = [
        (0x0301, "Версия ПО"),
        (0x0302, "Заводской номер"),
        (0x0303, "Номер устройства"),
        (0x0081, "Цифровые выходы 1"),
        (0x0083, "Давление"),
        (0x0084, "Влажность"),
        (0x008D, "Температура внутри 1"),
        (0x00D1, "Уровень вентиляции"),
        (0x00D5, "Текущая температура"),
    ]

    # Тест 1: Попытка чтения через FC03 (Holding Registers)
    print("📋 ТЕСТ 1: Чтение через FC03 (Holding Registers)")
    print("-" * 60)
    fc03_success = 0
    for address, name in test_registers[:3]:  # Проверим первые 3 регистра
        result = tester.read_registers(slave_id, address, count=1, function_code=0x03)
        if result:
            print(f"  0x{address:04X} ({name}): {result[0]} ⚠️ FC03 работает (неожиданно)")
            fc03_success += 1
        else:
            print(f"  0x{address:04X} ({name}): ❌ FC03 не работает (ожидаемо)")

    print()

    # Тест 2: Чтение через FC04 (Input Registers)
    print("📋 ТЕСТ 2: Чтение через FC04 (Input Registers)")
    print("-" * 60)
    fc04_success = 0
    results = {}

    # Тест 2.1: Пакетное чтение первых 4 регистров (0x0301-0x0304)
    print("  Попытка пакетного чтения 0x0301-0x0304 (4 регистра)...")
    time.sleep(0.2)
    batch_result = tester.read_registers(slave_id, 0x0301, count=4, function_code=0x04)
    if batch_result:
        print(f"  ✅ Пакетное чтение успешно: {batch_result}")
        results[0x0301] = batch_result[0]
        results[0x0302] = batch_result[1]
        results[0x0303] = batch_result[2]
    else:
        print(f"  ❌ Пакетное чтение не работает")

    print()
    for address, name in test_registers:
        time.sleep(0.2)  # Увеличенная пауза
        result = tester.read_registers(slave_id, address, count=1, function_code=0x04)
        if result:
            value = result[0]
            results[address] = value

            # Интерпретация значений
            if address == 0x0301:  # Версия ПО
                version = f"{value // 100}.{value % 100:02d}"
                print(f"  ✅ 0x{address:04X} ({name}): {value} → версия {version}")
            elif address in [0x008D, 0x00D5]:  # Температура (знаковая)
                if value >= 0x7FFC:
                    status_map = {0x7FFF: "ожидание", 0x7FFE: "обрыв", 0x7FFD: "ошибка", 0x7FFC: "отключен"}
                    print(f"  ✅ 0x{address:04X} ({name}): {value:04X} → {status_map.get(value, 'спец.значение')}")
                else:
                    # Знаковое преобразование
                    temp = value if value < 32768 else value - 65536
                    temp_celsius = temp / 10.0
                    print(f"  ✅ 0x{address:04X} ({name}): {value} → {temp_celsius:.1f}°C")
            else:
                print(f"  ✅ 0x{address:04X} ({name}): {value}")

            fc04_success += 1
        else:
            print(f"  ❌ 0x{address:04X} ({name}): ошибка чтения")

    tester.disconnect()

    # Итоги
    print(f"\n{'='*60}")
    print("📊 РЕЗУЛЬТАТЫ:")
    print(f"{'='*60}")
    print(f"FC03 (Holding): {fc03_success}/3 регистров прочитано")
    print(f"FC04 (Input):   {fc04_success}/{len(test_registers)} регистров прочитано")

    if fc04_success >= 7:
        print("\n✅ ТЕСТ ПРОЙДЕН: КУБ-1063 работает с FC04 (Input Registers)")
        print("   Согласно документации это правильное поведение.")
        return True
    else:
        print("\n❌ ТЕСТ НЕ ПРОЙДЕН: Не удалось прочитать достаточно регистров через FC04")
        return False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Тест чтения КУБ-1063 с проверкой FC03 vs FC04"
    )
    parser.add_argument("--port", required=True, help="Serial port (e.g. /dev/ttyUSB0)")
    parser.add_argument("--slave", type=int, required=True, help="Slave ID КУБ-1063")
    args = parser.parse_args(argv)

    success = test_kub1063_registers(args.port, args.slave)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
