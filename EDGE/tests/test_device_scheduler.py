#!/usr/bin/env python3
"""
Тесты для DeviceScheduler
Проверяем приоритетный опрос и масштабируемость
"""

import pytest
import time
from datetime import datetime, timedelta

from core.device_scheduler import (
    DeviceScheduler,
    ScheduledDevice,
    PollPriority
)
from core.device_registry import DeviceInfo, DeviceType


@pytest.fixture
def sample_devices():
    """Тестовые устройства"""
    return [
        DeviceInfo(
            device_id=1,
            device_type=DeviceType.KUB_1063,
            slave_id=1,
            name="КУБ 1",
            enabled=True
        ),
        DeviceInfo(
            device_id=2,
            device_type=DeviceType.VFD_INVERTER,
            slave_id=2,
            name="VFD 1",
            enabled=True
        ),
        DeviceInfo(
            device_id=3,
            device_type=DeviceType.VFD_INVERTER,
            slave_id=3,
            name="VFD 2",
            enabled=True
        ),
    ]


class TestScheduledDevice:
    """Тесты для ScheduledDevice"""

    def test_should_poll_first_time(self):
        """Первый опрос должен быть сразу"""
        device = DeviceInfo(1, DeviceType.KUB_1063, 1, "Test")
        scheduled = ScheduledDevice(device, poll_interval=5.0)

        assert scheduled.should_poll() is True

    def test_should_poll_after_interval(self):
        """После интервала нужен опрос"""
        device = DeviceInfo(1, DeviceType.KUB_1063, 1, "Test")
        scheduled = ScheduledDevice(device, poll_interval=0.1)  # 100ms

        # Первый опрос
        scheduled.mark_polled()
        assert scheduled.should_poll() is False

        # Ждём интервал
        time.sleep(0.15)
        assert scheduled.should_poll() is True

    def test_mark_polled_success(self):
        """Успешный опрос сбрасывает счетчик ошибок"""
        device = DeviceInfo(1, DeviceType.KUB_1063, 1, "Test")
        scheduled = ScheduledDevice(device)

        scheduled.error_count = 5
        scheduled.mark_polled(success=True)

        assert scheduled.error_count == 0
        assert scheduled.last_success is not None

    def test_mark_polled_failure(self):
        """Ошибка увеличивает счетчик"""
        device = DeviceInfo(1, DeviceType.KUB_1063, 1, "Test")
        scheduled = ScheduledDevice(device)

        scheduled.mark_polled(success=False)
        assert scheduled.error_count == 1

        scheduled.mark_polled(success=False)
        assert scheduled.error_count == 2

    def test_is_healthy(self):
        """Проверка здоровья устройства"""
        device = DeviceInfo(1, DeviceType.KUB_1063, 1, "Test")
        scheduled = ScheduledDevice(device)

        assert scheduled.is_healthy() is True

        scheduled.error_count = 2
        assert scheduled.is_healthy() is True

        scheduled.error_count = 3
        assert scheduled.is_healthy(max_errors=3) is False


class TestDeviceScheduler:
    """Тесты для DeviceScheduler"""

    def test_initialization(self, sample_devices):
        """Тест инициализации"""
        scheduler = DeviceScheduler(sample_devices)

        assert len(scheduler.scheduled_devices) == 3
        assert scheduler.total_polls == 0

    def test_default_intervals(self, sample_devices):
        """Проверка дефолтных интервалов"""
        scheduler = DeviceScheduler(sample_devices)

        # КУБ должен иметь интервал 1.0s
        kub = scheduler.scheduled_devices[1]
        assert kub.poll_interval == 1.0

        # VFD должен иметь интервал 2.0s
        vfd = scheduler.scheduled_devices[2]
        assert vfd.poll_interval == 2.0

    def test_custom_intervals(self, sample_devices):
        """Тест кастомных интервалов"""
        custom_intervals = {1: 0.5, 2: 3.0}
        scheduler = DeviceScheduler(sample_devices, custom_intervals=custom_intervals)

        assert scheduler.scheduled_devices[1].poll_interval == 0.5
        assert scheduler.scheduled_devices[2].poll_interval == 3.0

    def test_custom_priorities(self, sample_devices):
        """Тест кастомных приоритетов"""
        custom_priorities = {
            1: PollPriority.CRITICAL,
            2: PollPriority.LOW
        }
        scheduler = DeviceScheduler(sample_devices, custom_priorities=custom_priorities)

        assert scheduler.scheduled_devices[1].priority == PollPriority.CRITICAL
        assert scheduler.scheduled_devices[2].priority == PollPriority.LOW

    def test_get_devices_to_poll_initial(self, sample_devices):
        """Первый запрос должен вернуть все устройства"""
        scheduler = DeviceScheduler(sample_devices)
        devices = scheduler.get_devices_to_poll()

        assert len(devices) == 3

    def test_get_devices_to_poll_priority_order(self, sample_devices):
        """Устройства должны возвращаться по приоритету"""
        # Устанавливаем разные приоритеты
        custom_priorities = {
            1: PollPriority.HIGH,     # КУБ - высокий
            2: PollPriority.CRITICAL, # VFD 1 - критичный
            3: PollPriority.LOW       # VFD 2 - низкий
        }
        scheduler = DeviceScheduler(sample_devices, custom_priorities=custom_priorities)

        devices = scheduler.get_devices_to_poll()

        # Порядок: CRITICAL (2) → HIGH (1) → LOW (3)
        assert devices[0].device_id == 2
        assert devices[1].device_id == 1
        assert devices[2].device_id == 3

    def test_get_devices_to_poll_max_devices(self, sample_devices):
        """Ограничение количества устройств"""
        scheduler = DeviceScheduler(sample_devices)
        devices = scheduler.get_devices_to_poll(max_devices=2)

        assert len(devices) == 2

    def test_mark_poll_result(self, sample_devices):
        """Тест отметки результата опроса"""
        scheduler = DeviceScheduler(sample_devices)

        scheduler.mark_poll_result(1, success=True)
        assert scheduler.successful_polls == 1
        assert scheduler.failed_polls == 0

        scheduler.mark_poll_result(2, success=False)
        assert scheduler.successful_polls == 1
        assert scheduler.failed_polls == 1

    def test_get_next_poll_time(self, sample_devices):
        """Тест расчета времени до следующего опроса"""
        # Очень короткие интервалы для теста
        custom_intervals = {1: 0.1, 2: 0.2, 3: 0.3}
        scheduler = DeviceScheduler(sample_devices, custom_intervals=custom_intervals)

        # До первого опроса - сразу
        next_time = scheduler.get_next_poll_time()
        assert next_time == 0.0

        # Опрашиваем все устройства
        devices = scheduler.get_devices_to_poll()
        for device in devices:
            scheduler.mark_poll_result(device.device_id, success=True)

        # Теперь должно быть ~0.1s (минимальный интервал)
        next_time = scheduler.get_next_poll_time()
        assert 0.0 <= next_time <= 0.15

    def test_statistics(self, sample_devices):
        """Тест статистики"""
        scheduler = DeviceScheduler(sample_devices)

        # Начальное состояние
        stats = scheduler.get_statistics()
        assert stats['total_devices'] == 3
        assert stats['enabled_devices'] == 3
        assert stats['total_polls'] == 0

        # После опросов
        scheduler.mark_poll_result(1, success=True)
        scheduler.mark_poll_result(2, success=True)
        scheduler.mark_poll_result(3, success=False)

        stats = scheduler.get_statistics()
        assert stats['total_polls'] == 3
        assert stats['successful_polls'] == 2
        assert stats['failed_polls'] == 1
        assert stats['success_rate'] == "66.7%"

    def test_device_status(self, sample_devices):
        """Тест получения статуса устройства"""
        scheduler = DeviceScheduler(sample_devices)

        status = scheduler.get_device_status(1)
        assert status is not None
        assert status['device_name'] == "КУБ 1"
        assert status['device_type'] == "KUB-1063"
        assert status['enabled'] is True
        assert status['healthy'] is True

    def test_update_device_interval(self, sample_devices):
        """Тест обновления интервала"""
        scheduler = DeviceScheduler(sample_devices)

        scheduler.update_device_interval(1, 3.0)
        assert scheduler.scheduled_devices[1].poll_interval == 3.0

    def test_enable_disable_device(self, sample_devices):
        """Тест включения/отключения устройства"""
        scheduler = DeviceScheduler(sample_devices)

        # Отключаем
        scheduler.disable_device(1)
        assert scheduler.scheduled_devices[1].enabled is False

        devices = scheduler.get_devices_to_poll()
        assert len(devices) == 2  # Одно отключено

        # Включаем обратно
        scheduler.enable_device(1)
        assert scheduler.scheduled_devices[1].enabled is True

        devices = scheduler.get_devices_to_poll()
        assert len(devices) == 3

    def test_yaml_configuration_priority(self):
        """
        Проверка приоритета конфигурации:
        YAML poll_interval/priority > custom_intervals/priorities > DEFAULT
        """
        # Устройство 1: poll_interval и priority из YAML
        device1 = DeviceInfo(
            device_id=1,
            device_type=DeviceType.KUB_1063,
            slave_id=1,
            name="КУБ с YAML конфигурацией",
            enabled=True,
            poll_interval=0.5,  # YAML: 0.5 секунды
            priority="CRITICAL"  # YAML: CRITICAL
        )

        # Устройство 2: использует custom_intervals/custom_priorities
        device2 = DeviceInfo(
            device_id=2,
            device_type=DeviceType.VFD_INVERTER,
            slave_id=2,
            name="VFD с custom конфигурацией",
            enabled=True
            # poll_interval и priority не заданы в YAML
        )

        # Устройство 3: использует DEFAULT
        device3 = DeviceInfo(
            device_id=3,
            device_type=DeviceType.VFD_INVERTER,
            slave_id=3,
            name="VFD с DEFAULT конфигурацией",
            enabled=True
        )

        # Создаем scheduler с custom настройками для device2
        scheduler = DeviceScheduler(
            [device1, device2, device3],
            custom_intervals={2: 3.0},  # device2: 3 секунды
            custom_priorities={2: PollPriority.HIGH}  # device2: HIGH
        )

        # Проверяем device1 (YAML приоритетнее всего)
        scheduled1 = scheduler.scheduled_devices[1]
        assert scheduled1.poll_interval == 0.5, "YAML poll_interval должен использоваться"
        assert scheduled1.priority == PollPriority.CRITICAL, "YAML priority должен использоваться"

        # Проверяем device2 (custom_intervals/priorities)
        scheduled2 = scheduler.scheduled_devices[2]
        assert scheduled2.poll_interval == 3.0, "custom_intervals должен использоваться"
        assert scheduled2.priority == PollPriority.HIGH, "custom_priorities должен использоваться"

        # Проверяем device3 (DEFAULT)
        scheduled3 = scheduler.scheduled_devices[3]
        assert scheduled3.poll_interval == 2.0, "DEFAULT для VFD должен быть 2.0"
        assert scheduled3.priority == PollPriority.NORMAL, "DEFAULT priority NORMAL"

        print("\n✅ Приоритет конфигурации работает корректно:")
        print(f"   Device 1 (YAML): interval={scheduled1.poll_interval}s, priority={scheduled1.priority.name}")
        print(f"   Device 2 (custom): interval={scheduled2.poll_interval}s, priority={scheduled2.priority.name}")
        print(f"   Device 3 (DEFAULT): interval={scheduled3.poll_interval}s, priority={scheduled3.priority.name}")

    def test_yaml_priority_invalid_value(self):
        """Проверка обработки некорректного priority в YAML"""
        device = DeviceInfo(
            device_id=1,
            device_type=DeviceType.KUB_1063,
            slave_id=1,
            name="КУБ с некорректным priority",
            enabled=True,
            priority="INVALID_PRIORITY"  # Некорректное значение
        )

        # Должен использовать DEFAULT вместо некорректного
        scheduler = DeviceScheduler([device])
        scheduled = scheduler.scheduled_devices[1]

        # Должен откатиться на DEFAULT для КУБ-1063 (HIGH)
        assert scheduled.priority == PollPriority.HIGH, "Должен использовать DEFAULT при некорректном priority"

    def test_yaml_from_dict_integration(self):
        """Проверка загрузки poll_interval и priority через from_dict()"""
        # Симулируем данные из YAML
        yaml_data = {
            'device_id': 10,
            'device_type': 'КУБ-1063',
            'slave_id': 10,
            'name': 'КУБ из YAML',
            'description': 'Тестовое устройство',
            'enabled': True,
            'location': 'Секция A',
            'poll_interval': 1.5,
            'priority': 'HIGH'
        }

        # Загружаем через from_dict
        device = DeviceInfo.from_dict(yaml_data)

        # Проверяем, что поля загрузились
        assert device.poll_interval == 1.5
        assert device.priority == 'HIGH'

        # Проверяем работу в scheduler
        scheduler = DeviceScheduler([device])
        scheduled = scheduler.scheduled_devices[10]

        assert scheduled.poll_interval == 1.5
        assert scheduled.priority == PollPriority.HIGH

        print("\n✅ YAML интеграция через from_dict() работает корректно")


class TestScalability:
    """Тесты масштабируемости"""

    def test_many_devices(self):
        """Тест с большим количеством устройств (24 шт)"""
        devices = []

        # 6 КУБов
        for i in range(1, 7):
            devices.append(DeviceInfo(
                device_id=i,
                device_type=DeviceType.KUB_1063,
                slave_id=i,
                name=f"КУБ {i}",
                enabled=True
            ))

        # 18 VFD
        for i in range(7, 25):
            devices.append(DeviceInfo(
                device_id=i,
                device_type=DeviceType.VFD_INVERTER,
                slave_id=i,
                name=f"VFD {i-6}",
                enabled=True
            ))

        scheduler = DeviceScheduler(devices)

        assert len(scheduler.scheduled_devices) == 24

        # Все должны быть готовы к опросу
        to_poll = scheduler.get_devices_to_poll()
        assert len(to_poll) == 24

    def test_priority_scheduling_simulation(self):
        """Симуляция приоритетного опроса"""
        devices = []

        # 6 критичных КУБов (каждую секунду)
        for i in range(1, 7):
            devices.append(DeviceInfo(
                device_id=i,
                device_type=DeviceType.KUB_1063,
                slave_id=i,
                name=f"КУБ {i}",
                enabled=True
            ))

        # 6 важных VFD (каждые 2 секунды)
        for i in range(7, 13):
            devices.append(DeviceInfo(
                device_id=i,
                device_type=DeviceType.VFD_INVERTER,
                slave_id=i,
                name=f"VFD Important {i-6}",
                enabled=True
            ))

        # 12 обычных VFD (каждые 5 секунд)
        custom_intervals = {i: 5.0 for i in range(13, 25)}
        custom_priorities = {i: PollPriority.LOW for i in range(13, 25)}

        for i in range(13, 25):
            devices.append(DeviceInfo(
                device_id=i,
                device_type=DeviceType.VFD_INVERTER,
                slave_id=i,
                name=f"VFD Normal {i-12}",
                enabled=True
            ))

        scheduler = DeviceScheduler(
            devices,
            custom_intervals=custom_intervals,
            custom_priorities=custom_priorities
        )

        # Первый опрос - все устройства
        first_poll = scheduler.get_devices_to_poll()
        assert len(first_poll) == 24

        # Отмечаем как опрошенные
        for device in first_poll:
            scheduler.mark_poll_result(device.device_id, success=True)

        # Через 1 секунду должны быть готовы только КУБы
        time.sleep(1.1)
        second_poll = scheduler.get_devices_to_poll()

        # Должны быть КУБы (6 шт)
        assert 5 <= len(second_poll) <= 7  # Небольшая погрешность

        # Проверяем что это действительно КУБы
        kub_count = sum(1 for d in second_poll if d.device_type == DeviceType.KUB_1063)
        assert kub_count >= 5


class TestRealWorldScenario:
    """Реальный сценарий: 6 КУБ + 18 VFD"""

    def test_production_scenario(self):
        """Симуляция production сценария"""
        devices = []

        # 6 КУБов - высокий приоритет, 1s интервал
        for i in range(1, 7):
            devices.append(DeviceInfo(
                device_id=i,
                device_type=DeviceType.KUB_1063,
                slave_id=i,
                name=f"КУБ Корпус {i}",
                enabled=True
            ))

        # 18 VFD - разные приоритеты
        for i in range(7, 25):
            devices.append(DeviceInfo(
                device_id=i,
                device_type=DeviceType.VFD_INVERTER,
                slave_id=i,
                name=f"VFD Линия {i-6}",
                enabled=True
            ))

        # Настраиваем: 6 критичных VFD, 12 обычных
        custom_priorities = {}
        custom_intervals = {}

        # VFD 7-12 - критичные (1s интервал)
        for i in range(7, 13):
            custom_priorities[i] = PollPriority.HIGH
            custom_intervals[i] = 1.0

        # VFD 13-24 - обычные (5s интервал)
        for i in range(13, 25):
            custom_priorities[i] = PollPriority.NORMAL
            custom_intervals[i] = 5.0

        scheduler = DeviceScheduler(
            devices,
            custom_intervals=custom_intervals,
            custom_priorities=custom_priorities
        )

        # Проверяем конфигурацию
        assert len(scheduler.scheduled_devices) == 24

        # Критичные устройства (КУБ + важные VFD)
        critical_devices = [
            d for d in scheduler.scheduled_devices.values()
            if d.poll_interval == 1.0
        ]
        assert len(critical_devices) == 12  # 6 КУБ + 6 VFD

        # Получаем статистику
        stats = scheduler.get_statistics()
        assert stats['total_devices'] == 24
        assert stats['enabled_devices'] == 24

        print(f"\n📊 Production Scenario Statistics:")
        print(f"   Total devices: {stats['total_devices']}")
        print(f"   Critical (1s interval): {len(critical_devices)}")
        print(f"   Normal (5s interval): {24 - len(critical_devices)}")
