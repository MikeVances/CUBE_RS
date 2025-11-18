#!/usr/bin/env python3
"""
Эмулятор сети устройств для тестирования DeviceScheduler
Симулирует поведение реальной сети с 6 КУБами + 18 VFD
"""

import time
import random
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from core.device_registry import DeviceInfo, DeviceType
from core.device_scheduler import DeviceScheduler, PollPriority


class DeviceEmulatorState(Enum):
    """Состояние эмулируемого устройства"""
    ONLINE = "online"
    OFFLINE = "offline"
    SLOW_RESPONSE = "slow_response"
    INTERMITTENT = "intermittent"


@dataclass
class EmulatedDeviceData:
    """Данные эмулируемого устройства"""
    device_id: int
    device_type: DeviceType
    state: DeviceEmulatorState
    response_time_ms: float  # Время отклика в миллисекундах
    failure_rate: float  # Процент неудачных опросов (0.0 - 1.0)

    # Счетчики
    poll_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_response_time_ms: float = 0.0

    # Симулируемые данные
    temperature: float = 20.0
    humidity: float = 50.0
    frequency: float = 50.0  # Для VFD
    current: float = 0.0


class DeviceNetworkEmulator:
    """
    Эмулятор сети Modbus устройств

    Симулирует:
    - Время отклика устройств
    - Сбои связи
    - Изменение данных датчиков
    - Различные состояния устройств
    """

    def __init__(self, devices: List[DeviceInfo]):
        """
        Инициализация эмулятора

        Args:
            devices: Список устройств для эмуляции
        """
        self.devices = devices
        self.emulated_devices: Dict[int, EmulatedDeviceData] = {}

        # Инициализируем эмулируемые устройства
        for device in devices:
            self.emulated_devices[device.device_id] = self._create_emulated_device(device)

    def _create_emulated_device(self, device: DeviceInfo) -> EmulatedDeviceData:
        """
        Создать эмулируемое устройство с реалистичными параметрами

        Args:
            device: Информация об устройстве

        Returns:
            Эмулируемые данные устройства
        """
        # КУБы обычно быстрее и надежнее
        if device.device_type in [DeviceType.KUB_1063, DeviceType.KUB_1112]:
            return EmulatedDeviceData(
                device_id=device.device_id,
                device_type=device.device_type,
                state=DeviceEmulatorState.ONLINE,
                response_time_ms=random.uniform(10, 30),  # 10-30ms
                failure_rate=0.01  # 1% сбоев
            )

        # VFD могут быть медленнее
        elif device.device_type == DeviceType.VFD_INVERTER:
            return EmulatedDeviceData(
                device_id=device.device_id,
                device_type=device.device_type,
                state=DeviceEmulatorState.ONLINE,
                response_time_ms=random.uniform(20, 50),  # 20-50ms
                failure_rate=0.05  # 5% сбоев
            )

        else:
            return EmulatedDeviceData(
                device_id=device.device_id,
                device_type=device.device_type,
                state=DeviceEmulatorState.ONLINE,
                response_time_ms=random.uniform(30, 100),
                failure_rate=0.1
            )

    def poll_device(self, device_id: int) -> tuple[bool, Optional[Dict], float]:
        """
        Эмулировать опрос устройства

        Args:
            device_id: ID устройства

        Returns:
            (success, data, response_time_ms)
        """
        if device_id not in self.emulated_devices:
            return False, None, 0.0

        emulated = self.emulated_devices[device_id]
        emulated.poll_count += 1

        # Симулируем время отклика
        response_time = emulated.response_time_ms

        # Добавляем случайную вариацию ±20%
        response_time *= random.uniform(0.8, 1.2)

        # Симулируем задержку (в реальности это Modbus RTU/TCP запрос)
        time.sleep(response_time / 1000.0)

        # Определяем успех/неудачу опроса
        success = random.random() > emulated.failure_rate

        if emulated.state == DeviceEmulatorState.OFFLINE:
            success = False
        elif emulated.state == DeviceEmulatorState.INTERMITTENT:
            success = random.random() > 0.5
        elif emulated.state == DeviceEmulatorState.SLOW_RESPONSE:
            response_time *= 3.0  # В 3 раза медленнее

        # Обновляем счетчики
        emulated.total_response_time_ms += response_time

        if success:
            emulated.success_count += 1

            # Генерируем реалистичные данные
            data = self._generate_device_data(emulated)
            return True, data, response_time
        else:
            emulated.failure_count += 1
            return False, None, response_time

    def _generate_device_data(self, emulated: EmulatedDeviceData) -> Dict:
        """
        Генерировать реалистичные данные устройства

        Args:
            emulated: Эмулируемое устройство

        Returns:
            Словарь с данными устройства
        """
        # Медленное изменение температуры
        emulated.temperature += random.uniform(-0.1, 0.1)
        emulated.temperature = max(15.0, min(30.0, emulated.temperature))

        # Медленное изменение влажности
        emulated.humidity += random.uniform(-0.5, 0.5)
        emulated.humidity = max(30.0, min(80.0, emulated.humidity))

        if emulated.device_type == DeviceType.KUB_1063:
            return {
                'temperature': round(emulated.temperature, 1),
                'humidity': round(emulated.humidity, 1),
                'fan_speed': random.randint(0, 100),
                'heater_status': random.choice([0, 1]),
            }

        elif emulated.device_type == DeviceType.KUB_1112:
            return {
                'temperature': round(emulated.temperature, 1),
                'heater_power': random.randint(0, 100),
                'setpoint': 23.0,
            }

        elif emulated.device_type == DeviceType.VFD_INVERTER:
            # Медленное изменение частоты
            emulated.frequency += random.uniform(-0.5, 0.5)
            emulated.frequency = max(0.0, min(60.0, emulated.frequency))

            return {
                'frequency': round(emulated.frequency, 1),
                'current': round(random.uniform(0.0, 10.0), 2),
                'voltage': round(random.uniform(380.0, 400.0), 1),
                'power': round(random.uniform(0.0, 5.5), 2),
                'status': random.choice(['running', 'stopped', 'fault']),
            }

        return {}

    def set_device_state(self, device_id: int, state: DeviceEmulatorState):
        """
        Изменить состояние устройства

        Args:
            device_id: ID устройства
            state: Новое состояние
        """
        if device_id in self.emulated_devices:
            self.emulated_devices[device_id].state = state

    def get_statistics(self, device_id: Optional[int] = None) -> Dict:
        """
        Получить статистику эмулятора

        Args:
            device_id: ID устройства (None для общей статистики)

        Returns:
            Статистика
        """
        if device_id is not None:
            if device_id not in self.emulated_devices:
                return {}

            emulated = self.emulated_devices[device_id]
            avg_response_time = (
                emulated.total_response_time_ms / emulated.poll_count
                if emulated.poll_count > 0 else 0.0
            )

            return {
                'device_id': device_id,
                'poll_count': emulated.poll_count,
                'success_count': emulated.success_count,
                'failure_count': emulated.failure_count,
                'success_rate': (
                    f"{100.0 * emulated.success_count / emulated.poll_count:.1f}%"
                    if emulated.poll_count > 0 else "0%"
                ),
                'avg_response_time_ms': round(avg_response_time, 1),
                'state': emulated.state.value,
            }

        # Общая статистика
        total_polls = sum(d.poll_count for d in self.emulated_devices.values())
        total_success = sum(d.success_count for d in self.emulated_devices.values())
        total_failures = sum(d.failure_count for d in self.emulated_devices.values())
        total_response_time = sum(
            d.total_response_time_ms for d in self.emulated_devices.values()
        )

        return {
            'total_devices': len(self.emulated_devices),
            'total_polls': total_polls,
            'total_success': total_success,
            'total_failures': total_failures,
            'success_rate': (
                f"{100.0 * total_success / total_polls:.1f}%"
                if total_polls > 0 else "0%"
            ),
            'avg_response_time_ms': (
                round(total_response_time / total_polls, 1)
                if total_polls > 0 else 0.0
            ),
        }


def create_production_network() -> List[DeviceInfo]:
    """
    Создать эмулируемую производственную сеть: 6 КУБов + 18 VFD

    Returns:
        Список устройств
    """
    devices = []

    # 6 КУБов (3 КУБ-1063 + 3 КУБ-1112)
    for i in range(1, 4):
        devices.append(DeviceInfo(
            device_id=i,
            device_type=DeviceType.KUB_1063,
            slave_id=i,
            name=f"КУБ-1063 №{i}",
            description="Система вентиляции",
            enabled=True,
            location=f"Корпус {i}",
            poll_interval=1.0,
            priority="CRITICAL"
        ))

    for i in range(4, 7):
        devices.append(DeviceInfo(
            device_id=i,
            device_type=DeviceType.KUB_1112,
            slave_id=i,
            name=f"КУБ-1112 №{i-3}",
            description="Система обогрева",
            enabled=True,
            location=f"Корпус {i-3}",
            poll_interval=1.0,
            priority="CRITICAL"
        ))

    # 24 VFD инверторов
    # 6 важных VFD (каждые 2 секунды)
    for i in range(7, 13):
        devices.append(DeviceInfo(
            device_id=i,
            device_type=DeviceType.VFD_INVERTER,
            slave_id=i,
            name=f"VFD Важный №{i-6}",
            description="Основной вентилятор",
            enabled=True,
            location=f"Зона A-{i-6}",
            poll_interval=2.0,
            priority="HIGH"
        ))

    # 18 обычных VFD (каждые 5 секунд)
    for i in range(13, 31):
        devices.append(DeviceInfo(
            device_id=i,
            device_type=DeviceType.VFD_INVERTER,
            slave_id=i,
            name=f"VFD Обычный №{i-12}",
            description="Вспомогательное оборудование",
            enabled=True,
            location=f"Зона B-{i-12}",
            poll_interval=5.0,
            priority="LOW"
        ))

    return devices


# Пример использования
if __name__ == "__main__":
    print("🌐 Эмулятор сети устройств")
    print("=" * 60)

    # Создаем производственную сеть
    devices = create_production_network()
    print(f"📋 Создано устройств: {len(devices)}")
    print(f"   - КУБ-1063: 3 устройства")
    print(f"   - КУБ-1112: 3 устройства")
    print(f"   - VFD Важные: 6 устройств")
    print(f"   - VFD Обычные: 18 устройств")

    # Создаем эмулятор
    emulator = DeviceNetworkEmulator(devices)

    # Создаем планировщик
    scheduler = DeviceScheduler(devices)

    print("\n🚀 Запуск эмуляции (10 секунд)...")
    print("-" * 60)

    start_time = time.time()
    cycle_count = 0

    while time.time() - start_time < 10.0:
        cycle_start = time.time()
        cycle_count += 1

        # Получаем устройства для опроса
        devices_to_poll = scheduler.get_devices_to_poll(max_devices=5)

        if devices_to_poll:
            print(f"\n⏱️  Цикл #{cycle_count} ({len(devices_to_poll)} устройств)")

            for device in devices_to_poll:
                # Эмулируем опрос
                success, data, response_time = emulator.poll_device(device.device_id)

                # Отмечаем результат в планировщике
                scheduler.mark_poll_result(device.device_id, success=success)

                status = "✅" if success else "❌"
                print(f"  {status} {device.name} ({response_time:.1f}ms)")

                if success and data:
                    # Показываем данные для первых КУБов
                    if device.device_type in [DeviceType.KUB_1063, DeviceType.KUB_1112]:
                        print(f"      Температура: {data.get('temperature', 'N/A')}°C")

        # Ждем до следующего опроса
        next_poll_time = scheduler.get_next_poll_time()
        if next_poll_time > 0:
            time.sleep(min(next_poll_time, 0.1))

    # Выводим статистику
    print("\n" + "=" * 60)
    print("📊 СТАТИСТИКА ЭМУЛЯЦИИ")
    print("=" * 60)

    # Статистика эмулятора
    emulator_stats = emulator.get_statistics()
    print(f"\n🌐 Эмулятор сети:")
    print(f"   Всего опросов: {emulator_stats['total_polls']}")
    print(f"   Успешных: {emulator_stats['total_success']}")
    print(f"   Неудачных: {emulator_stats['total_failures']}")
    print(f"   Процент успеха: {emulator_stats['success_rate']}")
    print(f"   Среднее время отклика: {emulator_stats['avg_response_time_ms']}ms")

    # Статистика планировщика
    scheduler_stats = scheduler.get_statistics()
    print(f"\n📅 Планировщик:")
    print(f"   Всего устройств: {scheduler_stats['total_devices']}")
    print(f"   Активных: {scheduler_stats['enabled_devices']}")
    print(f"   Всего опросов: {scheduler_stats['total_polls']}")
    print(f"   Успешных: {scheduler_stats['successful_polls']}")
    print(f"   Неудачных: {scheduler_stats['failed_polls']}")
    print(f"   Процент успеха: {scheduler_stats['success_rate']}")

    # Статистика по приоритетам
    print(f"\n🎯 По приоритетам:")
    critical_devices = [
        d for d in scheduler.scheduled_devices.values()
        if d.priority == PollPriority.CRITICAL
    ]
    high_devices = [
        d for d in scheduler.scheduled_devices.values()
        if d.priority == PollPriority.HIGH
    ]
    normal_devices = [
        d for d in scheduler.scheduled_devices.values()
        if d.priority == PollPriority.NORMAL
    ]
    low_devices = [
        d for d in scheduler.scheduled_devices.values()
        if d.priority == PollPriority.LOW
    ]

    print(f"   CRITICAL: {len(critical_devices)} устройств (poll_interval: 1.0s)")
    print(f"   HIGH: {len(high_devices)} устройств (poll_interval: 2.0s)")
    print(f"   NORMAL: {len(normal_devices)} устройств")
    print(f"   LOW: {len(low_devices)} устройств (poll_interval: 5.0s)")

    # Топ-5 устройств по количеству опросов
    print(f"\n🏆 Топ-5 устройств по опросам:")
    sorted_devices = sorted(
        emulator.emulated_devices.values(),
        key=lambda d: d.poll_count,
        reverse=True
    )

    for i, emulated in enumerate(sorted_devices[:5], 1):
        device = next(d for d in devices if d.device_id == emulated.device_id)
        stats = emulator.get_statistics(emulated.device_id)
        print(f"   {i}. {device.name}")
        print(f"      Опросов: {stats['poll_count']}, "
              f"Успех: {stats['success_rate']}, "
              f"Время: {stats['avg_response_time_ms']}ms")

    print("\n✅ Эмуляция завершена")
