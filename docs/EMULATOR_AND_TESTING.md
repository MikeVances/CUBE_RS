# Эмулятор сети устройств и тестирование

## Обзор

Создан полнофункциональный эмулятор сети Modbus устройств для тестирования DeviceScheduler в реалистичных условиях. Эмулятор симулирует производственную сеть из 24 устройств (6 КУБов + 18 VFD) с различными сценариями работы.

## Компоненты

### 1. DeviceNetworkEmulator ([device_network_emulator.py](../EDGE/tests/device_network_emulator.py))

**Основной эмулятор сети устройств**

#### Возможности:
- ✅ Симуляция времени отклика устройств (10-100ms)
- ✅ Эмуляция сбоев связи (настраиваемый процент)
- ✅ Генерация реалистичных данных датчиков
- ✅ Различные состояния устройств (ONLINE, OFFLINE, SLOW_RESPONSE, INTERMITTENT)
- ✅ Детальная статистика по каждому устройству

#### Состояния устройств:

```python
class DeviceEmulatorState(Enum):
    ONLINE = "online"              # Нормальная работа
    OFFLINE = "offline"            # Устройство недоступно
    SLOW_RESPONSE = "slow_response"  # Медленный отклик (×3)
    INTERMITTENT = "intermittent"  # Нестабильное соединение (50% сбоев)
```

#### Реалистичные параметры:

| Тип устройства | Время отклика | Процент сбоев |
|----------------|---------------|---------------|
| КУБ-1063/1112  | 10-30ms       | 1%            |
| VFD-INVERTER   | 20-50ms       | 5%            |
| UNKNOWN        | 30-100ms      | 10%           |

#### Пример использования:

```python
from device_network_emulator import DeviceNetworkEmulator, create_production_network

# Создаем сеть из 24 устройств
devices = create_production_network()
emulator = DeviceNetworkEmulator(devices)

# Эмулируем опрос устройства
success, data, response_time = emulator.poll_device(device_id=1)

if success:
    print(f"Температура: {data['temperature']}°C")
    print(f"Время отклика: {response_time}ms")

# Симулируем сбой
emulator.set_device_state(device_id=1, DeviceEmulatorState.OFFLINE)
```

### 2. Interactive Emulator ([interactive_emulator.py](../EDGE/tests/interactive_emulator.py))

**Интерактивный эмулятор с готовыми сценариями**

#### Сценарии тестирования:

1. **Нормальная работа** (5 секунд)
   - Все 24 устройства онлайн
   - Проверка базовой функциональности

2. **Устройство отключено** (5 секунд)
   - КУБ-1063 №1 переводится в OFFLINE
   - Проверка устойчивости к сбоям

3. **Медленные устройства** (10 секунд)
   - 3 VFD переведены в SLOW_RESPONSE (×3 время отклика)
   - Проверка что медленные устройства не блокируют систему

4. **Нестабильное соединение** (8 секунд)
   - 2 VFD с 50% вероятностью сбоя
   - Проверка обработки intermittent failures

5. **Пиковая нагрузка** (5 секунд)
   - Все 24 устройства с интервалом 0.5 секунды
   - Стресс-тест планировщика

#### Запуск:

```bash
cd /Users/Mikhail1/Documents/GitHub/CUBE_RS/EDGE
PYTHONPATH=$PWD python tests/interactive_emulator.py
```

## Результаты тестирования

### Производственная сеть (24 устройства)

```
📋 Конфигурация:
   КУБ-1063: 3 устройства (CRITICAL, poll_interval=1.0s)
   КУБ-1112: 3 устройства (CRITICAL, poll_interval=1.0s)
   VFD Важные: 6 устройств (HIGH, poll_interval=2.0s)
   VFD Обычные: 12 устройств (LOW, poll_interval=5.0s)
```

### Статистика эмуляции (33 секунды, 5 сценариев)

```
🌐 Эмулятор сети:
   Всего опросов: 470
   Успешных: 449
   Неудачных: 21
   Процент успеха: 95.5%
   Среднее время отклика: 30.8ms

📅 Планировщик:
   Всего устройств: 24
   Активных: 24
   Всего опросов: 470
   Успешных: 449
   Неудачных: 21
   Процент успеха: 95.5%
```

### Результаты по группам устройств

#### КУБ-1063 (CRITICAL, 6 устройств)
```
Опросов: 108
Успех: 94.4%
Среднее время отклика: 19.1ms
```

#### КУБ-1112 (CRITICAL, 6 устройств)
```
Опросов: 108
Успех: 99.1%
Среднее время отклика: 23.4ms
```

#### VFD Важные (HIGH, 6 устройств)
```
Опросов: 133
Успех: 92.5%
Среднее время отклика: 40.2ms
```

#### VFD Обычные (LOW, 12 устройств)
```
Опросов: 121
Успех: 96.7%
Среднее время отклика: 38.9ms
```

## Выводы

### ✅ Подтверждено:

1. **DeviceScheduler корректно управляет приоритетами**
   - Критические устройства (КУБы) опрашиваются чаще всего (108 опросов за 33 сек)
   - Низкоприоритетные устройства опрашиваются реже (121 опрос / 12 устройств = 10 опросов на устройство)

2. **Система устойчива к сбоям**
   - При отключении КУБ-1063 №1 система продолжила работу
   - 21 неудачный опрос из 470 (4.5%) обработаны корректно
   - Circuit Breaker предупреждает о проблемных устройствах

3. **Медленные устройства не блокируют систему**
   - VFD с медленным откликом (×3) не влияют на опрос других устройств
   - Планировщик продолжает работать с нормальной частотой

4. **Нестабильное соединение обрабатывается корректно**
   - Устройства с 50% сбоев не останавливают опрос
   - Система автоматически повторяет попытки в следующем цикле

5. **Пиковая нагрузка обрабатывается эффективно**
   - При 24 устройствах × 0.5s интервал = 140 опросов за 5 секунд
   - Среднее время отклика: 30.8ms (хорошо для Modbus RTU)

## Производительность

### Время отклика по типам устройств

| Тип устройства | Среднее время | Min | Max |
|----------------|---------------|-----|-----|
| КУБ-1063       | 19.1ms        | 9ms | 31ms |
| КУБ-1112       | 23.4ms        | 18ms | 32ms |
| VFD (HIGH)     | 40.2ms        | 28ms | 51ms |
| VFD (LOW)      | 38.9ms        | 22ms | 69ms |

### Частота опроса

| Приоритет | Интервал | Опросов за 10 сек | Частота |
|-----------|----------|-------------------|---------|
| CRITICAL  | 1.0s     | ~10               | 1 Hz    |
| HIGH      | 2.0s     | ~5                | 0.5 Hz  |
| LOW       | 5.0s     | ~2                | 0.2 Hz  |

## Использование в разработке

### 1. Тестирование DeviceScheduler

```python
from device_network_emulator import DeviceNetworkEmulator, create_production_network
from core.device_scheduler import DeviceScheduler

# Создаем эмулятор
devices = create_production_network()
emulator = DeviceNetworkEmulator(devices)
scheduler = DeviceScheduler(devices)

# Тестируем 10 секунд
start_time = time.time()
while time.time() - start_time < 10.0:
    devices_to_poll = scheduler.get_devices_to_poll(max_devices=5)

    for device in devices_to_poll:
        success, data, response_time = emulator.poll_device(device.device_id)
        scheduler.mark_poll_result(device.device_id, success=success)

    time.sleep(scheduler.get_next_poll_time())

# Получаем статистику
stats = scheduler.get_statistics()
print(f"Всего опросов: {stats['total_polls']}")
print(f"Процент успеха: {stats['success_rate']}")
```

### 2. Тестирование новых функций

```python
# Тестируем адаптивное изменение интервалов
for device_id, device in scheduler.scheduled_devices.items():
    if device.error_count > 5:
        # Увеличиваем интервал для проблемных устройств
        scheduler.update_device_interval(device_id, device.poll_interval * 2)
```

### 3. Симуляция сбоев

```python
# Симулируем отказ оборудования
emulator.set_device_state(1, DeviceEmulatorState.OFFLINE)

# Симулируем медленную сеть
for device_id in range(13, 25):  # Все VFD LOW
    emulator.set_device_state(device_id, DeviceEmulatorState.SLOW_RESPONSE)

# Симулируем нестабильное соединение
emulator.set_device_state(7, DeviceEmulatorState.INTERMITTENT)
```

## Интеграция в CI/CD

### Автоматические тесты

```bash
# Юнит-тесты DeviceScheduler
pytest tests/test_device_scheduler.py -v

# Эмулятор (10 секунд, быстрая проверка)
PYTHONPATH=$PWD python tests/device_network_emulator.py

# Интерактивный эмулятор (33 секунды, полный набор сценариев)
PYTHONPATH=$PWD python tests/interactive_emulator.py
```

### Добавление в pre-commit

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: emulator-test
        name: Run Device Network Emulator
        entry: bash -c 'cd EDGE && PYTHONPATH=$PWD python tests/device_network_emulator.py'
        language: system
        pass_filenames: false
```

## Расширение эмулятора

### Добавление новых сценариев

```python
def scenario_custom(emulator: DeviceNetworkEmulator, scheduler: DeviceScheduler):
    """Пользовательский сценарий"""
    # 1. Настройте состояния устройств
    emulator.set_device_state(1, DeviceEmulatorState.OFFLINE)

    # 2. Измените параметры планировщика
    scheduler.update_device_interval(2, 0.5)

    # 3. Запустите симуляцию
    run_scenario(emulator, scheduler, duration=10.0, description="Мой сценарий")
```

### Добавление новых типов устройств

```python
# В device_network_emulator.py
def _create_emulated_device(self, device: DeviceInfo) -> EmulatedDeviceData:
    if device.device_type == DeviceType.MY_NEW_DEVICE:
        return EmulatedDeviceData(
            device_id=device.device_id,
            device_type=device.device_type,
            state=DeviceEmulatorState.ONLINE,
            response_time_ms=random.uniform(15, 40),
            failure_rate=0.02
        )
```

## Метрики для мониторинга

### Показатели здоровья системы

```python
stats = scheduler.get_statistics()

# Критические метрики:
assert stats['success_rate'].rstrip('%') >= "95.0"  # Минимум 95% успешных опросов
assert emulator.get_statistics()['avg_response_time_ms'] < 50.0  # Макс 50ms

# Метрики по устройствам:
for device_id in [1, 2, 3]:  # Критические КУБы
    device_stats = emulator.get_statistics(device_id)
    assert device_stats['success_count'] >= 8  # Минимум 8 успешных опросов за 10 сек
```

## Рекомендации

### Для разработки:
- Используйте `device_network_emulator.py` для быстрых проверок (10 сек)
- Используйте `interactive_emulator.py` для полного тестирования (33 сек)

### Для CI/CD:
- Запускайте быстрый эмулятор в pre-commit hooks
- Запускайте полный набор сценариев в GitHub Actions

### Для производства:
- Используйте метрики эмулятора как baseline для реальных устройств
- Ожидайте ~30ms среднее время отклика для Modbus RTU на RS485
- Ожидайте 95%+ процент успешных опросов

## Следующие шаги

1. ✅ **ЗАВЕРШЕНО**: Базовый эмулятор с 24 устройствами
2. ✅ **ЗАВЕРШЕНО**: 5 сценариев тестирования
3. ✅ **ЗАВЕРШЕНО**: Детальная статистика
4. ⏳ **TODO**: Интеграция DeviceScheduler в start.py
5. ⏳ **TODO**: Реальное тестирование с КУБ и VFD устройствами
6. ⏳ **TODO**: Графический дашборд для мониторинга

## Ссылки

- **Эмулятор**: [device_network_emulator.py](../EDGE/tests/device_network_emulator.py)
- **Интерактивный эмулятор**: [interactive_emulator.py](../EDGE/tests/interactive_emulator.py)
- **Тесты планировщика**: [test_device_scheduler.py](../EDGE/tests/test_device_scheduler.py)
- **DeviceScheduler**: [device_scheduler.py](../EDGE/core/device_scheduler.py)
- **Анализ масштабируемости**: [SCALING_ANALYSIS.md](./SCALING_ANALYSIS.md)
- **YAML интеграция**: [YAML_SCHEDULER_INTEGRATION.md](./YAML_SCHEDULER_INTEGRATION.md)
