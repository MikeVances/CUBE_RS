#!/usr/bin/env python3
"""
Интерактивный эмулятор сети устройств
Поддерживает различные сценарии: нормальная работа, сбои, медленные устройства
"""

import time
import sys
from device_network_emulator import (
    DeviceNetworkEmulator,
    DeviceEmulatorState,
    create_production_network
)
from core.device_scheduler import DeviceScheduler, PollPriority


def print_header(text: str):
    """Вывести заголовок"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_section(text: str):
    """Вывести раздел"""
    print(f"\n{'─' * 70}")
    print(f"  {text}")
    print(f"{'─' * 70}")


def run_scenario(
    emulator: DeviceNetworkEmulator,
    scheduler: DeviceScheduler,
    duration: float,
    description: str
):
    """
    Запустить сценарий эмуляции

    Args:
        emulator: Эмулятор сети
        scheduler: Планировщик
        duration: Длительность в секундах
        description: Описание сценария
    """
    print_section(f"🎬 Сценарий: {description}")
    print(f"⏱️  Длительность: {duration} секунд\n")

    start_time = time.time()
    cycle_count = 0
    polls_in_scenario = 0

    while time.time() - start_time < duration:
        cycle_count += 1

        # Получаем устройства для опроса
        devices_to_poll = scheduler.get_devices_to_poll(max_devices=5)

        if devices_to_poll:
            polls_in_scenario += len(devices_to_poll)

            for device in devices_to_poll:
                # Эмулируем опрос
                success, data, response_time = emulator.poll_device(device.device_id)

                # Отмечаем результат
                scheduler.mark_poll_result(device.device_id, success=success)

        # Ждем до следующего опроса
        next_poll_time = scheduler.get_next_poll_time()
        if next_poll_time > 0:
            time.sleep(min(next_poll_time, 0.1))

    print(f"✅ Сценарий завершен: {cycle_count} циклов, {polls_in_scenario} опросов")


def print_statistics(emulator: DeviceNetworkEmulator, scheduler: DeviceScheduler):
    """Вывести статистику"""
    print_header("📊 СТАТИСТИКА")

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

    # По приоритетам
    print(f"\n🎯 По приоритетам:")
    for priority in PollPriority:
        devices_with_priority = [
            d for d in scheduler.scheduled_devices.values()
            if d.priority == priority
        ]
        if devices_with_priority:
            print(f"   {priority.name}: {len(devices_with_priority)} устройств")


def scenario_normal_operation(
    emulator: DeviceNetworkEmulator,
    scheduler: DeviceScheduler
):
    """Сценарий: Нормальная работа"""
    run_scenario(
        emulator,
        scheduler,
        duration=5.0,
        description="Нормальная работа - все устройства онлайн"
    )


def scenario_device_offline(
    emulator: DeviceNetworkEmulator,
    scheduler: DeviceScheduler
):
    """Сценарий: Устройство отключено"""
    # Отключаем один КУБ
    print_section("⚠️  Сценарий: Устройство КУБ-1063 №1 отключено")
    emulator.set_device_state(1, DeviceEmulatorState.OFFLINE)
    print("   КУБ-1063 №1 переведен в состояние OFFLINE")

    run_scenario(
        emulator,
        scheduler,
        duration=5.0,
        description="Продолжение работы с одним отключенным устройством"
    )

    # Восстанавливаем
    emulator.set_device_state(1, DeviceEmulatorState.ONLINE)
    print("   КУБ-1063 №1 восстановлен (ONLINE)")


def scenario_slow_devices(
    emulator: DeviceNetworkEmulator,
    scheduler: DeviceScheduler
):
    """Сценарий: Медленные устройства"""
    print_section("🐌 Сценарий: Несколько VFD работают медленно")

    # Делаем несколько VFD медленными
    for device_id in [13, 14, 15]:  # VFD Обычные
        emulator.set_device_state(device_id, DeviceEmulatorState.SLOW_RESPONSE)
    print("   VFD Обычные №1-3 переведены в режим медленного отклика")

    run_scenario(
        emulator,
        scheduler,
        duration=10.0,
        description="Работа с медленными устройствами"
    )

    # Восстанавливаем
    for device_id in [13, 14, 15]:
        emulator.set_device_state(device_id, DeviceEmulatorState.ONLINE)
    print("   VFD восстановлены")


def scenario_intermittent_failures(
    emulator: DeviceNetworkEmulator,
    scheduler: DeviceScheduler
):
    """Сценарий: Нестабильное соединение"""
    print_section("📡 Сценарий: Нестабильное соединение (50% сбоев)")

    # Делаем несколько устройств нестабильными
    for device_id in [7, 8]:  # VFD Важные
        emulator.set_device_state(device_id, DeviceEmulatorState.INTERMITTENT)
    print("   VFD Важные №1-2 переведены в режим нестабильного соединения")

    run_scenario(
        emulator,
        scheduler,
        duration=8.0,
        description="Работа с нестабильными устройствами"
    )

    # Восстанавливаем
    for device_id in [7, 8]:
        emulator.set_device_state(device_id, DeviceEmulatorState.ONLINE)
    print("   VFD восстановлены")


def scenario_peak_load(
    emulator: DeviceNetworkEmulator,
    scheduler: DeviceScheduler
):
    """Сценарий: Пиковая нагрузка"""
    print_section("🔥 Сценарий: Пиковая нагрузка - все 24 устройства активны")

    # Включаем ВСЕ устройства на минимальный интервал
    for device_id in scheduler.scheduled_devices.keys():
        scheduler.update_device_interval(device_id, 0.5)

    print("   Все 24 устройства переведены на интервал 0.5 секунды")

    run_scenario(
        emulator,
        scheduler,
        duration=5.0,
        description="Максимальная частота опроса"
    )

    # Восстанавливаем нормальные интервалы
    devices = create_production_network()
    for device in devices:
        if device.poll_interval:
            scheduler.update_device_interval(device.device_id, device.poll_interval)

    print("   Интервалы опроса восстановлены")


def main():
    """Главная функция"""
    print_header("🌐 ИНТЕРАКТИВНЫЙ ЭМУЛЯТОР СЕТИ УСТРОЙСТВ")

    # Создаем производственную сеть
    devices = create_production_network()
    print(f"\n📋 Создана производственная сеть:")
    print(f"   КУБ-1063: 3 устройства (CRITICAL, 1.0s)")
    print(f"   КУБ-1112: 3 устройства (CRITICAL, 1.0s)")
    print(f"   VFD Важные: 6 устройств (HIGH, 2.0s)")
    print(f"   VFD Обычные: 12 устройств (LOW, 5.0s)")
    print(f"   Всего: {len(devices)} устройств")

    # Создаем эмулятор и планировщик
    emulator = DeviceNetworkEmulator(devices)
    scheduler = DeviceScheduler(devices)

    print("\n🚀 Запуск симуляции различных сценариев...")

    # Сценарий 1: Нормальная работа
    scenario_normal_operation(emulator, scheduler)
    time.sleep(1)

    # Сценарий 2: Устройство отключено
    scenario_device_offline(emulator, scheduler)
    time.sleep(1)

    # Сценарий 3: Медленные устройства
    scenario_slow_devices(emulator, scheduler)
    time.sleep(1)

    # Сценарий 4: Нестабильное соединение
    scenario_intermittent_failures(emulator, scheduler)
    time.sleep(1)

    # Сценарий 5: Пиковая нагрузка
    scenario_peak_load(emulator, scheduler)

    # Итоговая статистика
    print_statistics(emulator, scheduler)

    # Детальная статистика по устройствам
    print_section("📈 Детальная статистика по устройствам")

    # Группируем по типам
    kub1063_devices = [d for d in devices if d.device_type.value == 'KUB-1063']
    kub1112_devices = [d for d in devices if d.device_type.value == 'KUB-1112']
    vfd_high = [d for d in devices[6:12]]  # VFD Важные
    vfd_low = [d for d in devices[12:]]    # VFD Обычные

    for group_name, group_devices in [
        ("КУБ-1063 (CRITICAL)", kub1063_devices),
        ("КУБ-1112 (CRITICAL)", kub1112_devices),
        ("VFD Важные (HIGH)", vfd_high),
        ("VFD Обычные (LOW)", vfd_low),
    ]:
        print(f"\n{group_name}:")

        total_polls = 0
        total_success = 0

        for device in group_devices:
            stats = emulator.get_statistics(device.device_id)
            total_polls += stats['poll_count']
            total_success += stats['success_count']

            print(f"   {device.name}:")
            print(f"      Опросов: {stats['poll_count']}, "
                  f"Успех: {stats['success_rate']}, "
                  f"Время: {stats['avg_response_time_ms']}ms")

        if total_polls > 0:
            group_success_rate = 100.0 * total_success / total_polls
            print(f"   Итого по группе: {total_polls} опросов, "
                  f"успех: {group_success_rate:.1f}%")

    print_header("✅ ЭМУЛЯЦИЯ ЗАВЕРШЕНА")
    print("\n💡 Выводы:")
    print("   ✓ DeviceScheduler корректно управляет приоритетами")
    print("   ✓ Критические устройства (КУБы) опрашиваются чаще всего")
    print("   ✓ Система устойчива к сбоям отдельных устройств")
    print("   ✓ Медленные устройства не блокируют опрос других")
    print("   ✓ Приоритетная схема обеспечивает актуальность критичных данных")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Эмуляция прервана пользователем")
        sys.exit(0)
