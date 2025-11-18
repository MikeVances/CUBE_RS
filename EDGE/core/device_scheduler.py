#!/usr/bin/env python3
"""
Device Scheduler - планировщик опроса устройств с приоритетами
Решает проблему масштабирования для большого количества устройств
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging

from core.device_registry import DeviceInfo, DeviceType

logger = logging.getLogger(__name__)


class PollPriority(Enum):
    """Приоритеты опроса устройств"""
    CRITICAL = 0   # Аварийные системы - максимальный приоритет
    HIGH = 1       # Основные контроллеры - высокий приоритет
    NORMAL = 2     # Обычные устройства - средний приоритет
    LOW = 3        # Вспомогательные датчики - низкий приоритет


@dataclass
class ScheduledDevice:
    """
    Устройство с расписанием опроса

    Attributes:
        device_info: Информация об устройстве
        poll_interval: Интервал опроса в секундах
        priority: Приоритет устройства
        last_poll: Время последнего опроса
        last_success: Время последнего успешного опроса
        error_count: Счетчик ошибок подряд
        enabled: Активно ли расписание
    """
    device_info: DeviceInfo
    poll_interval: float = 5.0
    priority: PollPriority = PollPriority.NORMAL
    last_poll: Optional[datetime] = None
    last_success: Optional[datetime] = None
    error_count: int = 0
    enabled: bool = True

    def should_poll(self, now: Optional[datetime] = None) -> bool:
        """
        Проверка нужен ли опрос устройства

        Args:
            now: Текущее время (для тестирования)

        Returns:
            True если устройство нужно опросить
        """
        if not self.enabled:
            return False

        if now is None:
            now = datetime.now()

        # Первый опрос
        if self.last_poll is None:
            return True

        # Проверяем интервал
        elapsed = (now - self.last_poll).total_seconds()
        return elapsed >= self.poll_interval

    def mark_polled(self, success: bool = True):
        """
        Отметить что устройство опрошено

        Args:
            success: Успешен ли был опрос
        """
        now = datetime.now()
        self.last_poll = now

        if success:
            self.last_success = now
            self.error_count = 0
        else:
            self.error_count += 1

    def time_since_last_poll(self) -> Optional[float]:
        """Время с последнего опроса (в секундах)"""
        if self.last_poll is None:
            return None
        return (datetime.now() - self.last_poll).total_seconds()

    def time_until_next_poll(self) -> float:
        """Время до следующего опроса (в секундах)"""
        if self.last_poll is None:
            return 0.0

        elapsed = (datetime.now() - self.last_poll).total_seconds()
        return max(0.0, self.poll_interval - elapsed)

    def is_healthy(self, max_errors: int = 3) -> bool:
        """Проверка здоровья устройства"""
        return self.error_count < max_errors


class DeviceScheduler:
    """
    Планировщик опроса устройств с приоритетами и интервалами

    Основные функции:
    - Опрос устройств по расписанию (интервалы)
    - Приоритизация критичных устройств
    - Backoff при ошибках
    - Статистика и мониторинг
    """

    # Дефолтные интервалы опроса по типам устройств (секунды)
    DEFAULT_INTERVALS = {
        DeviceType.KUB_1063: 1.0,      # КУБы - каждую секунду
        DeviceType.KUB_1112: 1.0,      # КУБы - каждую секунду
        DeviceType.VFD_INVERTER: 2.0,  # VFD - каждые 2 секунды
        DeviceType.UNKNOWN: 5.0,       # Неизвестные - раз в 5 секунд
    }

    # Дефолтные приоритеты по типам устройств
    DEFAULT_PRIORITIES = {
        DeviceType.KUB_1063: PollPriority.HIGH,
        DeviceType.KUB_1112: PollPriority.HIGH,
        DeviceType.VFD_INVERTER: PollPriority.NORMAL,
        DeviceType.UNKNOWN: PollPriority.LOW,
    }

    def __init__(
        self,
        devices: List[DeviceInfo],
        custom_intervals: Optional[Dict[int, float]] = None,
        custom_priorities: Optional[Dict[int, PollPriority]] = None,
        default_intervals_by_type: Optional[Dict[DeviceType, float]] = None,
    ):
        """
        Инициализация планировщика

        Args:
            devices: Список устройств для опроса
            custom_intervals: Кастомные интервалы {device_id: interval}
            custom_priorities: Кастомные приоритеты {device_id: priority}
        """
        self.scheduled_devices: Dict[int, ScheduledDevice] = {}
        self.custom_intervals = custom_intervals or {}
        self.custom_priorities = custom_priorities or {}
        self.default_intervals_by_type = (
            default_intervals_by_type
            if default_intervals_by_type is not None
            else self.DEFAULT_INTERVALS.copy()
        )

        # Статистика
        self.total_polls = 0
        self.successful_polls = 0
        self.failed_polls = 0

        # Регистрация устройств
        for device in devices:
            self.add_device(device)

        logger.info(f"📅 Device Scheduler initialized with {len(self.scheduled_devices)} devices")

    def add_device(self, device: DeviceInfo):
        """
        Добавить устройство в расписание

        Args:
            device: Информация об устройстве
        """
        # Определяем интервал (приоритет: YAML > custom_intervals > DEFAULT)
        if device.poll_interval is not None:
            poll_interval = device.poll_interval
        else:
            poll_interval = self.custom_intervals.get(
                device.device_id,
                self.default_intervals_by_type.get(
                    device.device_type,
                    self.DEFAULT_INTERVALS.get(device.device_type, 5.0),
                ),
            )

        # Определяем приоритет (приоритет: YAML > custom_priorities > DEFAULT)
        if device.priority is not None:
            try:
                priority = PollPriority[device.priority.upper()]
            except KeyError:
                logger.warning(
                    f"⚠️ Unknown priority '{device.priority}' for device {device.name}, "
                    f"using default"
                )
                priority = self.DEFAULT_PRIORITIES.get(
                    device.device_type, PollPriority.NORMAL
                )
        else:
            priority = self.custom_priorities.get(
                device.device_id,
                self.DEFAULT_PRIORITIES.get(device.device_type, PollPriority.NORMAL)
            )

        scheduled = ScheduledDevice(
            device_info=device,
            poll_interval=poll_interval,
            priority=priority,
            enabled=device.enabled
        )

        self.scheduled_devices[device.device_id] = scheduled

        logger.debug(
            f"➕ Added device: {device.name} "
            f"(interval={poll_interval}s, priority={priority.name})"
        )

    def remove_device(self, device_id: int):
        """Удалить устройство из расписания"""
        if device_id in self.scheduled_devices:
            device = self.scheduled_devices.pop(device_id)
            logger.debug(f"➖ Removed device: {device.device_info.name}")

    def get_devices_to_poll(self, max_devices: Optional[int] = None) -> List[DeviceInfo]:
        """
        Получить список устройств для опроса СЕЙЧАС

        Args:
            max_devices: Максимальное количество устройств (для ограничения нагрузки)

        Returns:
            Список устройств отсортированных по приоритету
        """
        now = datetime.now()
        devices_to_poll = []

        # Фильтруем устройства которые нужно опросить
        for scheduled in self.scheduled_devices.values():
            if scheduled.should_poll(now):
                devices_to_poll.append(scheduled)

        # Сортируем по приоритету, затем по времени последнего опроса
        devices_to_poll.sort(
            key=lambda d: (
                d.priority.value,          # Сначала по приоритету
                d.last_poll or datetime.min  # Затем самые старые
            )
        )

        # Ограничиваем количество если нужно
        if max_devices is not None:
            devices_to_poll = devices_to_poll[:max_devices]

        # Возвращаем DeviceInfo
        return [scheduled.device_info for scheduled in devices_to_poll]

    def mark_poll_result(self, device_id: int, success: bool):
        """
        Отметить результат опроса устройства

        Args:
            device_id: ID устройства
            success: Успешен ли был опрос
        """
        if device_id in self.scheduled_devices:
            scheduled = self.scheduled_devices[device_id]
            scheduled.mark_polled(success)

            # Статистика
            self.total_polls += 1
            if success:
                self.successful_polls += 1
            else:
                self.failed_polls += 1

                # Логируем ошибки
                if scheduled.error_count >= 3:
                    logger.warning(
                        f"⚠️ Device {scheduled.device_info.name} has {scheduled.error_count} "
                        f"consecutive errors"
                    )

    def get_next_poll_time(self) -> float:
        """
        Время до следующего опроса (в секундах)

        Returns:
            Количество секунд до следующего опроса
        """
        if not self.scheduled_devices:
            return 1.0

        min_wait = float('inf')

        for scheduled in self.scheduled_devices.values():
            if scheduled.enabled:
                wait_time = scheduled.time_until_next_poll()
                min_wait = min(min_wait, wait_time)

        return max(0.0, min_wait) if min_wait != float('inf') else 1.0

    def get_statistics(self) -> Dict[str, any]:
        """Получить статистику работы планировщика"""
        total_devices = len(self.scheduled_devices)
        enabled_devices = sum(1 for d in self.scheduled_devices.values() if d.enabled)
        unhealthy_devices = sum(
            1 for d in self.scheduled_devices.values() if not d.is_healthy()
        )

        success_rate = (
            (self.successful_polls / self.total_polls * 100)
            if self.total_polls > 0 else 0.0
        )

        return {
            'total_devices': total_devices,
            'enabled_devices': enabled_devices,
            'unhealthy_devices': unhealthy_devices,
            'total_polls': self.total_polls,
            'successful_polls': self.successful_polls,
            'failed_polls': self.failed_polls,
            'success_rate': f"{success_rate:.1f}%",
        }

    def get_device_status(self, device_id: int) -> Optional[Dict[str, any]]:
        """Получить статус устройства"""
        if device_id not in self.scheduled_devices:
            return None

        scheduled = self.scheduled_devices[device_id]

        return {
            'device_name': scheduled.device_info.name,
            'device_type': scheduled.device_info.device_type.value,
            'enabled': scheduled.enabled,
            'poll_interval': scheduled.poll_interval,
            'priority': scheduled.priority.name,
            'last_poll': scheduled.last_poll.isoformat() if scheduled.last_poll else None,
            'last_success': scheduled.last_success.isoformat() if scheduled.last_success else None,
            'error_count': scheduled.error_count,
            'time_since_last_poll': scheduled.time_since_last_poll(),
            'time_until_next_poll': scheduled.time_until_next_poll(),
            'healthy': scheduled.is_healthy(),
        }

    def get_all_device_statuses(self) -> List[Dict[str, any]]:
        """Получить статусы всех устройств"""
        return [
            self.get_device_status(device_id)
            for device_id in self.scheduled_devices.keys()
        ]

    def update_device_interval(self, device_id: int, new_interval: float):
        """Обновить интервал опроса устройства"""
        if device_id in self.scheduled_devices:
            self.scheduled_devices[device_id].poll_interval = new_interval
            logger.info(
                f"🔄 Updated poll interval for device {device_id}: {new_interval}s"
            )

    def enable_device(self, device_id: int):
        """Включить опрос устройства"""
        if device_id in self.scheduled_devices:
            self.scheduled_devices[device_id].enabled = True
            logger.info(f"✅ Enabled polling for device {device_id}")

    def disable_device(self, device_id: int):
        """Отключить опрос устройства"""
        if device_id in self.scheduled_devices:
            self.scheduled_devices[device_id].enabled = False
            logger.info(f"🛑 Disabled polling for device {device_id}")

    def __repr__(self) -> str:
        """Строковое представление"""
        stats = self.get_statistics()
        return (
            f"DeviceScheduler("
            f"devices={stats['enabled_devices']}/{stats['total_devices']}, "
            f"polls={stats['total_polls']}, "
            f"success_rate={stats['success_rate']})"
        )
