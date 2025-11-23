#!/usr/bin/env python3
"""
Universal Modbus Reader
Универсальный reader для всех типов устройств через Device Adapters
Поддерживает: КУБ-1063, КУБ-1112, VFD-INVERTER и любые другие адаптеры
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import serial
import crcmod

from core.log_filter import get_secure_logger
from core.device_registry import DeviceInfo, DeviceType
from core.device_adapters import get_device_adapter
from core.device_adapters.base import RegisterType

logger = get_secure_logger(__name__)

# CRC16 для Modbus RTU
crc16 = crcmod.predefined.mkPredefinedCrcFun("modbus")


class UniversalModbusReader:
    """
    Универсальный Modbus RTU reader
    Использует Device Adapters для определения регистров и парсинга данных
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        timeout: float = 2.0,
        parity: str = 'N',
        stopbits: int = 1,
        bytesize: int = 8
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.parity = parity
        self.stopbits = stopbits
        self.bytesize = bytesize
        self.serial_connection: Optional[serial.Serial] = None

    def connect(self) -> bool:
        """Подключение к serial порту"""
        try:
            if self.serial_connection and self.serial_connection.is_open:
                return True

            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                parity=self.parity,
                stopbits=self.stopbits,
                bytesize=self.bytesize,
                timeout=self.timeout
            )

            logger.info(f"✅ Подключено к {self.port} (baudrate={self.baudrate})")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка подключения к {self.port}: {e}")
            return False

    def disconnect(self):
        """Отключение от serial порта"""
        if self.serial_connection:
            try:
                # Принудительное закрытие для macOS
                if hasattr(self.serial_connection, 'cancel_read'):
                    self.serial_connection.cancel_read()
                if hasattr(self.serial_connection, 'reset_input_buffer'):
                    self.serial_connection.reset_input_buffer()
                if hasattr(self.serial_connection, 'reset_output_buffer'):
                    self.serial_connection.reset_output_buffer()
            except Exception:
                pass

            try:
                if self.serial_connection.is_open:
                    self.serial_connection.close()
                    # Задержка для macOS - порт освобождается не мгновенно
                    import time
                    time.sleep(0.1)
            except Exception:
                pass

            # Полностью удаляем ссылку на объект
            self.serial_connection = None
            logger.info(f"🔌 Отключено от {self.port}")

    def __del__(self):
        """Деструктор - гарантированное закрытие порта"""
        try:
            self.disconnect()
        except Exception:
            pass  # Игнорируем ошибки в деструкторе

    def __enter__(self):
        """Поддержка context manager (with statement)"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Поддержка context manager - автоматическое закрытие"""
        self.disconnect()
        return False  # Не подавляем исключения

    def _build_modbus_request(self, slave_id: int, register_address: int, count: int = 1, register_type: RegisterType = RegisterType.HOLDING) -> bytes:
        """
        Построение Modbus RTU запроса
        Function Code 03 (Read Holding Registers) или 04 (Read Input Registers)

        Args:
            slave_id: Адрес устройства
            register_address: Адрес регистра
            count: Количество регистров
            register_type: Тип регистра (HOLDING или INPUT)
        """
        # Выбираем function code в зависимости от типа регистра
        if register_type == RegisterType.INPUT:
            function_code = 0x04  # Read Input Registers
        else:
            function_code = 0x03  # Read Holding Registers

        # Формируем запрос без CRC
        request = bytes([
            slave_id,
            function_code,
            (register_address >> 8) & 0xFF,  # High byte address
            register_address & 0xFF,         # Low byte address
            (count >> 8) & 0xFF,             # High byte count
            count & 0xFF                     # Low byte count
        ])

        # Добавляем CRC16
        crc = crc16(request)
        request += bytes([crc & 0xFF, (crc >> 8) & 0xFF])

        return request

    def _build_write_single_request(self, slave_id: int, register_address: int, value: int) -> bytes:
        """Создание запроса FC06 (Write Single Register)."""
        request = bytearray(
            [
                slave_id,
                0x06,
                (register_address >> 8) & 0xFF,
                register_address & 0xFF,
                (value >> 8) & 0xFF,
                value & 0xFF,
            ]
        )
        crc = crc16(request)
        request.append(crc & 0xFF)
        request.append((crc >> 8) & 0xFF)
        return bytes(request)

    def _parse_modbus_response(self, response: bytes, expected_count: int) -> Optional[List[int]]:
        """Парсинг Modbus RTU ответа"""
        if len(response) < 5:  # Минимальная длина: slave_id + func + byte_count + crc(2)
            logger.warning(f"⚠️ Слишком короткий ответ: {len(response)} байт")
            return None

        # Проверяем CRC
        received_crc = response[-2] | (response[-1] << 8)
        calculated_crc = crc16(response[:-2])

        if received_crc != calculated_crc:
            logger.warning(f"⚠️ Ошибка CRC: получен {received_crc:04X}, ожидался {calculated_crc:04X}")
            return None

        # Проверяем функцию (error response = 0x80 + function_code)
        function_code = response[1]
        if function_code & 0x80:
            error_code = response[2]
            logger.error(f"❌ Modbus error: function={function_code:02X}, error_code={error_code}")
            return None

        # Извлекаем данные
        byte_count = response[2]
        expected_bytes = expected_count * 2

        if byte_count != expected_bytes:
            logger.warning(f"⚠️ Неожиданное количество байт: {byte_count}, ожидалось {expected_bytes}")
            return None

        # Парсим регистры (2 байта на регистр, big-endian)
        registers = []
        for i in range(expected_count):
            offset = 3 + (i * 2)
            if offset + 1 < len(response) - 2:  # -2 для CRC
                value = (response[offset] << 8) | response[offset + 1]
                registers.append(value)

        return registers

    def read_register(
        self,
        slave_id: int,
        register_address: int,
        register_type: RegisterType = RegisterType.HOLDING,
    ) -> Optional[int]:
        """Чтение одного регистра"""
        if not self.connect():
            return None

        try:
            # Формируем запрос
            request = self._build_modbus_request(
                slave_id,
                register_address,
                count=1,
                register_type=register_type,
            )

            # Отправляем запрос
            self.serial_connection.write(request)
            time.sleep(0.05)  # Небольшая задержка

            # Читаем ответ
            response = self.serial_connection.read(100)  # Читаем максимум 100 байт

            # Парсим ответ
            registers = self._parse_modbus_response(response, expected_count=1)

            if registers and len(registers) > 0:
                return registers[0]

            return None

        except Exception as e:
            logger.error(f"❌ Ошибка чтения регистра 0x{register_address:04X}: {e}")
            return None

    def write_single_register(
        self,
        slave_id: int,
        register_address: int,
        value: int,
        validate_response: bool = True,
    ) -> bool:
        """Запись одного регистра (FC06)."""

        if not self.connect():
            return False

        try:
            request = self._build_write_single_request(slave_id, register_address, value)
            assert self.serial_connection is not None
            self.serial_connection.flushInput()
            self.serial_connection.flushOutput()
            self.serial_connection.write(request)
            self.serial_connection.flush()
            time.sleep(0.05)

            if not validate_response:
                return True

            response = self.serial_connection.read(8)
            if len(response) < 8:
                logger.warning(
                    "⚠️ Короткий ответ при записи регистра 0x%04X (получено %d байт)",
                    register_address,
                    len(response),
                )
                return False

            if response[0] != slave_id or response[1] != 0x06:
                logger.warning(
                    "⚠️ Некорректный ответ при записи регистра 0x%04X", register_address
                )
                return False

            received_crc = (response[-1] << 8) | response[-2]
            calculated_crc = crc16(response[:-2])
            if received_crc != calculated_crc:
                logger.warning(
                    "⚠️ Ошибка CRC при записи регистра 0x%04X: %04X != %04X",
                    register_address,
                    received_crc,
                    calculated_crc,
                )
                return False

            returned_register = (response[2] << 8) | response[3]
            returned_value = (response[4] << 8) | response[5]
            if returned_register != register_address or returned_value != (value & 0xFFFF):
                logger.warning(
                    "⚠️ Подтверждение записи не совпало (ожидали %04X=%s, получили %04X=%s)",
                    register_address,
                    value,
                    returned_register,
                    returned_value,
                )
                return False

            return True

        except Exception as exc:
            logger.error(
                "❌ Ошибка записи регистра 0x%04X для slave_id=%s: %s",
                register_address,
                slave_id,
                exc,
            )
            return False

    def read_registers_batch(
        self,
        slave_id: int,
        register_addresses: List[int],
        batch_size: int = 10
    ) -> Dict[int, int]:
        """
        Чтение нескольких регистров пакетами
        Modbus поддерживает чтение до 125 последовательных регистров за раз
        """
        results: Dict[int, int] = {}

        if not self.connect():
            return results

        # Сортируем адреса
        sorted_addresses = sorted(register_addresses)

        # Группируем последовательные адреса
        groups = []
        current_group = [sorted_addresses[0]]

        for addr in sorted_addresses[1:]:
            if addr == current_group[-1] + 1 and len(current_group) < batch_size:
                current_group.append(addr)
            else:
                groups.append(current_group)
                current_group = [addr]

        groups.append(current_group)

        # Читаем каждую группу
        for group in groups:
            start_addr = group[0]
            count = len(group)

            try:
                request = self._build_modbus_request(slave_id, start_addr, count=count)
                self.serial_connection.write(request)
                time.sleep(0.05 * count)  # Задержка пропорциональна количеству регистров

                response = self.serial_connection.read(200)
                registers = self._parse_modbus_response(response, expected_count=count)

                if registers:
                    for i, addr in enumerate(group):
                        if i < len(registers):
                            results[addr] = registers[i]

                time.sleep(0.02)  # Небольшая пауза между пакетами

            except Exception as e:
                logger.error(f"❌ Ошибка чтения группы регистров {start_addr:04X}-{group[-1]:04X}: {e}")
                continue

        return results

    def _read_registers_with_types(
        self,
        slave_id: int,
        register_map: Dict[str, Any],
        batch_size: int = 10
    ) -> Dict[int, int]:
        """
        Чтение регистров с учётом их типов (Holding/Input)

        Args:
            slave_id: Адрес устройства
            register_map: Карта регистров из адаптера
            batch_size: Размер пакета

        Returns:
            Dict[address] = value
        """
        results: Dict[int, int] = {}

        if not self.connect():
            return results

        # Группируем регистры по типу (Holding/Input)
        holding_regs = []
        input_regs = []

        for reg_info in register_map.values():
            if reg_info.register_type == RegisterType.INPUT:
                input_regs.append(reg_info.address)
            else:
                holding_regs.append(reg_info.address)

        def read_groups(addresses: List[int], reg_type: RegisterType) -> None:
            if not addresses:
                return
            addresses.sort()
            logger.debug(
                "  Читаем %d %s регистров (FC%02d) пакетами до %d",
                len(addresses),
                "Holding" if reg_type == RegisterType.HOLDING else "Input",
                3 if reg_type == RegisterType.HOLDING else 4,
                batch_size,
            )

            groups: List[List[int]] = []
            current_group = [addresses[0]]
            for addr in addresses[1:]:
                if addr == current_group[-1] + 1 and len(current_group) < batch_size:
                    current_group.append(addr)
                else:
                    groups.append(current_group)
                    current_group = [addr]
            groups.append(current_group)

            for group in groups:
                start_addr = group[0]
                count = len(group)
                try:
                    request = self._build_modbus_request(
                        slave_id,
                        start_addr,
                        count=count,
                        register_type=reg_type,
                    )
                    self.serial_connection.write(request)
                    time.sleep(0.01 * count)
                    response = self.serial_connection.read(5 + count * 2)
                    registers = self._parse_modbus_response(response, expected_count=count)
                    if registers:
                        for idx, value in enumerate(registers):
                            results[start_addr + idx] = value
                    time.sleep(0.02)
                except Exception as exc:
                    logger.error(
                        "❌ Ошибка чтения %s регистров 0x%04X-0x%04X: %s",
                        "Holding" if reg_type == RegisterType.HOLDING else "Input",
                        start_addr,
                        start_addr + count - 1,
                        exc,
                    )
                    continue

        read_groups(holding_regs, RegisterType.HOLDING)
        read_groups(input_regs, RegisterType.INPUT)

        return results

    def read_device(self, device_info: DeviceInfo) -> Optional[Dict[str, Any]]:
        """
        Чтение всех данных устройства через его адаптер

        Args:
            device_info: Информация об устройстве из Device Registry

        Returns:
            Dict с parsed данными устройства или None при ошибке
        """
        # Получаем адаптер для типа устройства
        adapter = get_device_adapter(device_info.device_type)

        if not adapter:
            logger.error(f"❌ Адаптер для {device_info.device_type} не найден")
            return None

        # Получаем карту регистров (содержит адреса И типы)
        register_map = adapter.register_map

        if not register_map:
            logger.warning(f"⚠️ Нет регистров для чтения у {device_info.name}")
            return None

        logger.debug(
            f"📖 Читаем {len(register_map)} регистров для {device_info.name} "
            f"(slave_id={device_info.slave_id})"
        )

        # Читаем регистры с учётом их типов (Holding/Input)
        batch_size = getattr(adapter, "max_batch_size", 20)

        raw_registers = self._read_registers_with_types(
            slave_id=device_info.slave_id,
            register_map=register_map,
            batch_size=batch_size  # адаптер задаёт безопасный размер блока
        )

        if not raw_registers:
            logger.warning(f"⚠️ Не удалось прочитать данные с {device_info.name}")
            return None

        logger.debug(f"✅ Прочитано {len(raw_registers)} регистров")

        # Парсим данные через адаптер
        try:
            device_data = adapter.parse_device_data(
                device_id=device_info.device_id,
                raw_registers=raw_registers
            )

            # Проверяем критические аварии
            alarms = adapter.get_critical_alarms(device_data)
            warnings = adapter.get_warnings(device_data)

            if alarms:
                logger.warning(f"🚨 {device_info.name}: Критические аварии: {alarms}")

            if warnings:
                logger.info(f"⚠️  {device_info.name}: Предупреждения: {warnings}")

            # Формируем результат
            result = {
                "device_id": device_data.device_id,
                "device_type": device_data.device_type,
                "device_name": device_info.name,
                "timestamp": datetime.now().isoformat(),
                "connection_status": "connected",
                "registers": device_data.registers,
                "raw_registers": raw_registers,
                "raw_named_registers": device_data.raw_registers,
                "status": device_data.status,
                "alarms": alarms,
                "warnings": warnings,
            }

            return result

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга данных {device_info.name}: {e}", exc_info=True)
            return None

    def read_multiple_devices(
        self,
        devices: List[DeviceInfo],
        delay_between_devices: float = 0.1
    ) -> Dict[int, Dict[str, Any]]:
        """
        Последовательное чтение нескольких устройств

        Args:
            devices: Список устройств для чтения
            delay_between_devices: Задержка между устройствами (секунды)

        Returns:
            Dict[device_id] = device_data
        """
        results = {}

        for device in devices:
            if not device.enabled:
                logger.debug(f"⏭️ Пропускаем отключенное устройство {device.name}")
                continue

            logger.info(f"📡 Опрос {device.name} (type={device.device_type.value}, slave_id={device.slave_id})")

            data = self.read_device(device)

            if data:
                results[device.device_id] = data
                logger.info(f"✅ {device.name}: данные получены")
            else:
                logger.warning(f"⚠️ {device.name}: не удалось получить данные")
                results[device.device_id] = {
                    "device_id": device.device_id,
                    "device_type": device.device_type.value,
                    "device_name": device.name,
                    "timestamp": datetime.now().isoformat(),
                    "connection_status": "error",
                    "error": "Failed to read device"
                }

            # Задержка между устройствами
            if delay_between_devices > 0:
                time.sleep(delay_between_devices)

        return results


# Глобальный экземпляр reader'а
_global_reader: Optional[UniversalModbusReader] = None


def get_universal_reader(
    port: str = "/dev/ttyUSB0",
    baudrate: int = 9600,
    timeout: float = 2.0
) -> UniversalModbusReader:
    """Получение глобального экземпляра universal reader"""
    global _global_reader

    if _global_reader is None:
        _global_reader = UniversalModbusReader(
            port=port,
            baudrate=baudrate,
            timeout=timeout
        )

    return _global_reader


def close_universal_reader():
    """Закрытие глобального reader'а"""
    global _global_reader

    if _global_reader:
        _global_reader.disconnect()
        _global_reader = None
