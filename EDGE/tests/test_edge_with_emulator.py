#!/usr/bin/env python3
"""
Интеграционный тест EDGE узла с эмулятором сети устройств

Этот тест демонстрирует, как можно использовать DeviceNetworkEmulator
для тестирования полного EDGE узла без реальных устройств.
"""

import time
import pytest
from datetime import datetime
from typing import Dict, List

from device_network_emulator import (
    DeviceNetworkEmulator,
    DeviceEmulatorState,
    create_production_network
)
from core.device_scheduler import DeviceScheduler, PollPriority
from core.device_registry import DeviceInfo


class MockModbusStorage:
    """Mock для modbus_storage для тестирования"""

    def __init__(self):
        self.data: Dict[int, Dict] = {}
        self.update_count = 0

    def update_data(self, device_id: int, **data):
        """Обновить данные устройства"""
        if device_id not in self.data:
            self.data[device_id] = {}

        self.data[device_id].update(data)
        self.data[device_id]['last_update'] = datetime.now()
        self.update_count += 1

    def get_data(self, device_id: int) -> Dict:
        """Получить данные устройства"""
        return self.data.get(device_id, {})

    def get_all_data(self) -> Dict[int, Dict]:
        """Получить данные всех устройств"""
        return self.data


class EDGENodeEmulator:
    """
    Эмулятор EDGE узла с DeviceScheduler и DeviceNetworkEmulator

    Симулирует основной цикл опроса устройств, как это работает в start.py
    """

    def __init__(
        self,
        devices: List[DeviceInfo],
        storage: MockModbusStorage
    ):
        """
        Инициализация EDGE узла

        Args:
            devices: Список устройств
            storage: Хранилище данных
        """
        self.devices = devices
        self.storage = storage

        # Создаем компоненты
        self.network_emulator = DeviceNetworkEmulator(devices)
        self.scheduler = DeviceScheduler(devices)

        # Счетчики
        self.total_polls = 0
        self.successful_polls = 0
        self.failed_polls = 0

    def poll_device(self, device: DeviceInfo) -> bool:
        """
        Опросить устройство и сохранить данные

        Args:
            device: Информация об устройстве

        Returns:
            Успешность опроса
        """
        self.total_polls += 1

        # Эмулируем опрос через сеть
        success, data, response_time = self.network_emulator.poll_device(
            device.device_id
        )

        # Отмечаем результат в планировщике
        self.scheduler.mark_poll_result(device.device_id, success=success)

        if success and data:
            self.successful_polls += 1

            # Сохраняем данные в storage
            self.storage.update_data(
                device_id=device.device_id,
                device_type=device.device_type.value,
                slave_id=device.slave_id,
                connection_status="connected",
                response_time_ms=response_time,
                **data
            )

            return True
        else:
            self.failed_polls += 1

            # Сохраняем статус ошибки
            self.storage.update_data(
                device_id=device.device_id,
                device_type=device.device_type.value,
                slave_id=device.slave_id,
                connection_status="error",
                error="Connection failed"
            )

            return False

    def run_cycle(self, max_devices: int = 5):
        """
        Выполнить один цикл опроса

        Args:
            max_devices: Максимум устройств за цикл
        """
        # Получаем устройства для опроса
        devices_to_poll = self.scheduler.get_devices_to_poll(max_devices=max_devices)

        # Опрашиваем устройства
        for device in devices_to_poll:
            self.poll_device(device)

    def run(self, duration: float, max_devices: int = 5):
        """
        Запустить EDGE узел на заданное время

        Args:
            duration: Длительность работы в секундах
            max_devices: Максимум устройств за цикл
        """
        start_time = time.time()
        cycle_count = 0

        while time.time() - start_time < duration:
            self.run_cycle(max_devices=max_devices)
            cycle_count += 1

            # Ждем до следующего опроса
            next_poll_time = self.scheduler.get_next_poll_time()
            if next_poll_time > 0:
                time.sleep(min(next_poll_time, 0.1))

        return cycle_count

    def get_statistics(self) -> Dict:
        """Получить статистику работы узла"""
        scheduler_stats = self.scheduler.get_statistics()
        emulator_stats = self.network_emulator.get_statistics()

        return {
            'total_polls': self.total_polls,
            'successful_polls': self.successful_polls,
            'failed_polls': self.failed_polls,
            'success_rate': (
                f"{100.0 * self.successful_polls / self.total_polls:.1f}%"
                if self.total_polls > 0 else "0%"
            ),
            'devices_count': scheduler_stats['total_devices'],
            'storage_updates': self.storage.update_count,
            'avg_response_time_ms': emulator_stats['avg_response_time_ms'],
        }


class TestEDGENodeWithEmulator:
    """Тесты EDGE узла с эмулятором"""

    def test_basic_operation(self):
        """Базовый тест: EDGE узел работает с 24 устройствами"""
        # Создаем сеть
        devices = create_production_network()
        storage = MockModbusStorage()

        # Создаем EDGE узел
        edge = EDGENodeEmulator(devices, storage)

        # Запускаем на 5 секунд
        cycle_count = edge.run(duration=5.0, max_devices=5)

        # Проверяем результаты
        stats = edge.get_statistics()

        print(f"\n📊 Статистика работы EDGE узла:")
        print(f"   Циклов опроса: {cycle_count}")
        print(f"   Всего опросов: {stats['total_polls']}")
        print(f"   Успешных: {stats['successful_polls']}")
        print(f"   Неудачных: {stats['failed_polls']}")
        print(f"   Процент успеха: {stats['success_rate']}")
        print(f"   Обновлений storage: {stats['storage_updates']}")
        print(f"   Среднее время отклика: {stats['avg_response_time_ms']}ms")

        # Проверки
        assert stats['total_polls'] > 50, "Должно быть минимум 50 опросов за 5 сек"
        assert float(stats['success_rate'].rstrip('%')) > 90.0, "Минимум 90% успеха"
        assert stats['storage_updates'] > 0, "Данные должны сохраняться в storage"

        # Проверяем что критические устройства опрошены чаще
        kub_polls = sum(
            edge.network_emulator.emulated_devices[i].poll_count
            for i in range(1, 7)  # КУБы device_id 1-6
        )
        vfd_low_polls = sum(
            edge.network_emulator.emulated_devices[i].poll_count
            for i in range(13, 25)  # VFD LOW device_id 13-24
        )

        print(f"\n🎯 Приоритеты:")
        print(f"   КУБы (CRITICAL): {kub_polls} опросов")
        print(f"   VFD LOW: {vfd_low_polls} опросов")

        assert kub_polls > vfd_low_polls, "Критические устройства должны опрашиваться чаще"

    def test_device_offline(self):
        """Тест: EDGE узел продолжает работу при отказе устройства"""
        devices = create_production_network()
        storage = MockModbusStorage()
        edge = EDGENodeEmulator(devices, storage)

        # Отключаем КУБ-1063 №1
        edge.network_emulator.set_device_state(1, DeviceEmulatorState.OFFLINE)

        # Запускаем
        edge.run(duration=3.0, max_devices=5)

        # Проверяем что остальные устройства работают
        stats = edge.get_statistics()
        assert float(stats['success_rate'].rstrip('%')) > 85.0, "Минимум 85% успеха с одним offline"

        # Проверяем что устройство 1 имеет ошибки
        device1_data = storage.get_data(1)
        assert device1_data.get('connection_status') == 'error', "Device 1 должен быть в статусе error"

        # Проверяем что другие устройства работают
        device2_data = storage.get_data(2)
        assert device2_data.get('connection_status') == 'connected', "Device 2 должен работать"

        print(f"\n✅ Устойчивость к сбоям: {stats['success_rate']}")

    def test_slow_devices(self):
        """Тест: Медленные устройства не блокируют систему"""
        devices = create_production_network()
        storage = MockModbusStorage()
        edge = EDGENodeEmulator(devices, storage)

        # Делаем несколько VFD медленными
        for device_id in [13, 14, 15]:
            edge.network_emulator.set_device_state(device_id, DeviceEmulatorState.SLOW_RESPONSE)

        # Запускаем
        edge.run(duration=5.0, max_devices=5)

        # Проверяем что критические устройства не пострадали
        kub_success = 0
        kub_total = 0

        for device_id in range(1, 7):  # КУБы
            emulated = edge.network_emulator.emulated_devices[device_id]
            kub_total += emulated.poll_count
            kub_success += emulated.success_count

        kub_success_rate = 100.0 * kub_success / kub_total if kub_total > 0 else 0

        print(f"\n🚀 КУБы при медленных VFD: {kub_success_rate:.1f}% успеха")

        assert kub_success_rate > 90.0, "КУБы должны работать нормально даже при медленных VFD"

    def test_yaml_configuration(self):
        """Тест: YAML конфигурация применяется корректно"""
        devices = create_production_network()
        storage = MockModbusStorage()
        edge = EDGENodeEmulator(devices, storage)

        # Проверяем что устройства имеют правильные параметры из YAML
        for device_id in range(1, 7):  # КУБы
            scheduled = edge.scheduler.scheduled_devices[device_id]
            assert scheduled.poll_interval == 1.0, f"КУБ {device_id} должен иметь interval 1.0s"
            assert scheduled.priority == PollPriority.CRITICAL, f"КУБ {device_id} должен быть CRITICAL"

        for device_id in range(7, 13):  # VFD HIGH
            scheduled = edge.scheduler.scheduled_devices[device_id]
            assert scheduled.poll_interval == 2.0, f"VFD HIGH {device_id} должен иметь interval 2.0s"
            assert scheduled.priority == PollPriority.HIGH, f"VFD HIGH {device_id} должен быть HIGH"

        for device_id in range(13, 25):  # VFD LOW
            scheduled = edge.scheduler.scheduled_devices[device_id]
            assert scheduled.poll_interval == 5.0, f"VFD LOW {device_id} должен иметь interval 5.0s"
            assert scheduled.priority == PollPriority.LOW, f"VFD LOW {device_id} должен быть LOW"

        print(f"\n✅ YAML конфигурация применена корректно")

    def test_storage_data_format(self):
        """Тест: Данные сохраняются в правильном формате"""
        devices = create_production_network()
        storage = MockModbusStorage()
        edge = EDGENodeEmulator(devices, storage)

        # Запускаем
        edge.run(duration=2.0, max_devices=5)

        # Проверяем формат данных КУБ-1063
        kub_data = storage.get_data(1)
        assert 'temperature' in kub_data, "КУБ должен иметь temperature"
        assert 'humidity' in kub_data, "КУБ должен иметь humidity"
        assert 'connection_status' in kub_data, "Должен быть connection_status"
        assert 'response_time_ms' in kub_data, "Должно быть response_time_ms"

        # Проверяем формат данных VFD
        vfd_data = storage.get_data(7)
        if vfd_data.get('connection_status') == 'connected':
            assert 'frequency' in vfd_data, "VFD должен иметь frequency"
            assert 'current' in vfd_data, "VFD должен иметь current"

        print(f"\n✅ Формат данных storage корректен")
        print(f"   КУБ данные: {list(kub_data.keys())}")
        if vfd_data:
            print(f"   VFD данные: {list(vfd_data.keys())}")

    def test_production_scenario(self):
        """Тест: Производственный сценарий 10 секунд"""
        devices = create_production_network()
        storage = MockModbusStorage()
        edge = EDGENodeEmulator(devices, storage)

        print(f"\n🏭 Производственный сценарий:")
        print(f"   Устройств: {len(devices)}")
        print(f"   Длительность: 10 секунд")

        # Запускаем
        cycle_count = edge.run(duration=10.0, max_devices=5)

        # Статистика
        stats = edge.get_statistics()

        print(f"\n📊 Результаты:")
        print(f"   Циклов: {cycle_count}")
        print(f"   Опросов: {stats['total_polls']}")
        print(f"   Успех: {stats['success_rate']}")
        print(f"   Среднее время: {stats['avg_response_time_ms']}ms")

        # Проверяем что все устройства опрошены
        all_data = storage.get_all_data()
        print(f"   Устройств в storage: {len(all_data)}")

        assert len(all_data) == 24, "Все 24 устройства должны быть в storage"
        assert stats['total_polls'] > 100, "Должно быть минимум 100 опросов за 10 сек"
        assert float(stats['success_rate'].rstrip('%')) > 90.0, "Минимум 90% успеха"

        # Детальная статистика по приоритетам
        print(f"\n🎯 По приоритетам:")
        for priority_name, device_ids in [
            ("CRITICAL (КУБы)", range(1, 7)),
            ("HIGH (VFD важные)", range(7, 13)),
            ("LOW (VFD обычные)", range(13, 25))
        ]:
            polls = sum(
                edge.network_emulator.emulated_devices[i].poll_count
                for i in device_ids
            )
            avg_polls = polls / len(list(device_ids))
            print(f"   {priority_name}: {polls} опросов (avg {avg_polls:.1f} на устройство)")


if __name__ == "__main__":
    print("=" * 70)
    print("  🧪 Интеграционные тесты EDGE узла с эмулятором сети")
    print("=" * 70)

    pytest.main([__file__, "-v", "-s"])
