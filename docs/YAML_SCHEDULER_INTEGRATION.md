# YAML Scheduler Integration - Complete Guide

## Обзор

Интеграция DeviceScheduler с YAML конфигурацией позволяет управлять параметрами опроса устройств (интервал и приоритет) напрямую из файла `devices.yaml` без изменения кода.

## Новые поля в devices.yaml

### `poll_interval` (опционально)
- **Тип**: `float`
- **Единицы**: секунды
- **Описание**: Интервал опроса устройства
- **Пример**: `poll_interval: 0.5` (опрос каждые 0.5 секунды)

### `priority` (опционально)
- **Тип**: `string`
- **Допустимые значения**: `CRITICAL`, `HIGH`, `NORMAL`, `LOW`
- **Описание**: Приоритет устройства при опросе
- **Пример**: `priority: CRITICAL`

## Приоритет настроек

Система использует каскадную схему определения параметров:

```
1. YAML (poll_interval, priority)          ← Наивысший приоритет
   ↓
2. custom_intervals, custom_priorities      ← Программные переопределения
   ↓
3. DEFAULT_INTERVALS, DEFAULT_PRIORITIES    ← Базовые значения по типу устройства
```

### DEFAULT значения по типам устройств

| Тип устройства | poll_interval | priority |
|----------------|---------------|----------|
| КУБ-1063       | 1.0 сек       | HIGH     |
| КУБ-1112       | 1.0 сек       | HIGH     |
| VFD-INVERTER   | 2.0 сек       | NORMAL   |
| UNKNOWN        | 5.0 сек       | LOW      |

## Примеры конфигурации

### Пример 1: Критическое устройство (0.5 секунды)

```yaml
- device_id: 1
  device_type: KUB-1063
  slave_id: 1
  name: "КУБ Основной"
  enabled: true
  poll_interval: 0.5  # Каждые 0.5 секунды
  priority: CRITICAL  # Критический приоритет
```

### Пример 2: Обычное устройство (2 секунды)

```yaml
- device_id: 2
  device_type: VFD-INVERTER
  slave_id: 2
  name: "VFD Вентилятор"
  enabled: true
  poll_interval: 2.0  # Каждые 2 секунды
  priority: NORMAL    # Нормальный приоритет
```

### Пример 3: Использование DEFAULT значений

```yaml
- device_id: 3
  device_type: VFD-INVERTER
  slave_id: 3
  name: "VFD Резервный"
  enabled: true
  # poll_interval не указан → DEFAULT 2.0 сек для VFD
  # priority не указан → DEFAULT NORMAL для VFD
```

## Производственный сценарий: 6 КУБов + 18 VFD

### Конфигурация для оптимальной производительности

```yaml
devices:
  # 6 КУБов - критические устройства (опрос каждую секунду)
  - device_id: 1
    device_type: KUB-1063
    slave_id: 1
    name: "КУБ №1"
    poll_interval: 1.0
    priority: CRITICAL

  - device_id: 2
    device_type: KUB-1063
    slave_id: 2
    name: "КУБ №2"
    poll_interval: 1.0
    priority: CRITICAL

  # ... еще 4 КУБа с аналогичными настройками

  # 6 важных VFD (опрос каждые 2 секунды)
  - device_id: 7
    device_type: VFD-INVERTER
    slave_id: 7
    name: "VFD Основной №1"
    poll_interval: 2.0
    priority: HIGH

  # ... еще 5 VFD с priority: HIGH

  # 12 обычных VFD (опрос каждые 5 секунд)
  - device_id: 13
    device_type: VFD-INVERTER
    slave_id: 13
    name: "VFD Вспомогательный №1"
    poll_interval: 5.0
    priority: LOW

  # ... еще 11 VFD с priority: LOW
```

### Ожидаемая производительность

| Категория | Устройств | Интервал | Частота опроса |
|-----------|-----------|----------|----------------|
| Критические (КУБы) | 6 | 1.0 сек | 1 Hz |
| Важные (VFD) | 6 | 2.0 сек | 0.5 Hz |
| Обычные (VFD) | 12 | 5.0 сек | 0.2 Hz |

**Результат**: Критические данные обновляются каждую секунду, полный цикл завершается за 5.4 секунды.

## Использование в коде

### Загрузка из YAML

```python
from core.device_registry import DeviceInfo
import yaml

# Загрузка из YAML
with open('config/devices.yaml') as f:
    config = yaml.safe_load(f)

devices = [DeviceInfo.from_dict(d) for d in config['devices']]
```

### Создание DeviceScheduler

```python
from core.device_scheduler import DeviceScheduler

# YAML параметры используются автоматически
scheduler = DeviceScheduler(devices)

# Можно переопределить программно для отдельных устройств
scheduler = DeviceScheduler(
    devices,
    custom_intervals={99: 0.1},  # device_id=99 опрашивать каждые 0.1 сек
    custom_priorities={99: PollPriority.CRITICAL}
)
```

### Приоритетный опрос

```python
# Получить устройства для опроса (автоматически отсортированы по приоритету)
devices_to_poll = scheduler.get_devices_to_poll(max_devices=10)

# Опросить устройства
for device in devices_to_poll:
    success = poll_device(device)
    scheduler.mark_poll_result(device.device_id, success=success)

# Узнать время до следующего опроса
next_poll = scheduler.get_next_poll_time()
time.sleep(next_poll)
```

## Валидация и обработка ошибок

### Некорректный приоритет

Если в YAML указано некорректное значение `priority`:

```yaml
- device_id: 1
  priority: INVALID_VALUE  # ← Некорректно
```

Система:
1. Логирует предупреждение: `⚠️ Unknown priority 'INVALID_VALUE' for device X, using default`
2. Использует DEFAULT приоритет для этого типа устройства

### Некорректный poll_interval

```yaml
- device_id: 1
  poll_interval: -1  # ← Некорректно (отрицательное значение)
```

Система использует значение как есть, но может привести к ошибкам. **Рекомендация**: Валидировать в приложении.

## Мониторинг и отладка

### Получение статистики планировщика

```python
stats = scheduler.get_statistics()
print(f"Всего устройств: {stats['total_devices']}")
print(f"Активных: {stats['enabled_devices']}")
print(f"Успешных опросов: {stats['successful_polls']}")
print(f"Процент успеха: {stats['success_rate']}")
```

### Проверка конфигурации устройства

```python
status = scheduler.get_device_status(device_id=1)
print(f"Устройство: {status['device_name']}")
print(f"Интервал: {status['poll_interval']}s")
print(f"Приоритет: {status['priority']}")
print(f"Последний опрос: {status['last_poll']}")
print(f"Здоровье: {status['healthy']}")
```

### Динамическое изменение параметров

```python
# Изменить интервал опроса во время работы
scheduler.update_device_interval(device_id=1, interval=0.25)

# Отключить устройство
scheduler.disable_device(device_id=1)

# Включить обратно
scheduler.enable_device(device_id=1)
```

## Тестирование

### Юнит-тесты

Проект включает комплексное тестовое покрытие:

```bash
# Тесты приоритета конфигурации
pytest tests/test_device_scheduler.py::TestDeviceScheduler::test_yaml_configuration_priority -v

# Тесты обработки некорректных значений
pytest tests/test_device_scheduler.py::TestDeviceScheduler::test_yaml_priority_invalid_value -v

# Тесты from_dict() интеграции
pytest tests/test_device_scheduler.py::TestDeviceScheduler::test_yaml_from_dict_integration -v

# Все тесты планировщика (24 теста)
pytest tests/test_device_scheduler.py -v
```

### Тест производственного сценария

```bash
# Тест для 6 КУБов + 18 VFD
pytest tests/test_device_scheduler.py::TestRealWorldScenario::test_production_scenario -v
```

## Рекомендации по использованию

### Когда использовать YAML конфигурацию

✅ **Используйте YAML для**:
- Стандартных производственных настроек
- Устройств с постоянными параметрами
- Конфигурации, которая должна переживать перезапуск

❌ **Не используйте YAML для**:
- Динамических изменений во время работы
- Временных переопределений для отладки
- Параметров, зависящих от runtime условий

### Когда использовать custom_intervals/custom_priorities

✅ **Используйте программные переопределения для**:
- A/B тестирования разных интервалов
- Временной приоритизации во время инцидентов
- Адаптивного изменения параметров на основе нагрузки

### Рекомендации по интервалам опроса

| Применение | Рекомендуемый интервал |
|------------|------------------------|
| Критические системы безопасности | 0.5 - 1.0 сек |
| Основное производственное оборудование | 1.0 - 2.0 сек |
| Вспомогательное оборудование | 2.0 - 5.0 сек |
| Мониторинг и статистика | 5.0 - 10.0 сек |
| Архивные/резервные устройства | 10.0 - 60.0 сек |

### Рекомендации по приоритетам

| Приоритет | Применение |
|-----------|------------|
| CRITICAL | Аварийное оборудование, системы безопасности |
| HIGH | Основное производственное оборудование (КУБы) |
| NORMAL | Периферийное оборудование (VFD, датчики) |
| LOW | Вспомогательные, резервные устройства |

## Миграция с предыдущих версий

### До интеграции (программная конфигурация)

```python
scheduler = DeviceScheduler(
    devices,
    custom_intervals={
        1: 0.5,
        2: 1.0,
        3: 2.0
    },
    custom_priorities={
        1: PollPriority.CRITICAL,
        2: PollPriority.HIGH,
        3: PollPriority.NORMAL
    }
)
```

### После интеграции (YAML конфигурация)

**devices.yaml**:
```yaml
- device_id: 1
  poll_interval: 0.5
  priority: CRITICAL

- device_id: 2
  poll_interval: 1.0
  priority: HIGH

- device_id: 3
  poll_interval: 2.0
  priority: NORMAL
```

**Код**:
```python
# Загружаем из YAML - параметры применяются автоматически
devices = load_devices_from_yaml('config/devices.yaml')
scheduler = DeviceScheduler(devices)
```

## Ссылки

- **Исходный код**:
  - [device_scheduler.py](../EDGE/core/device_scheduler.py)
  - [device_registry.py](../EDGE/core/device_registry.py)
- **Тесты**: [test_device_scheduler.py](../EDGE/tests/test_device_scheduler.py)
- **Пример конфигурации**: [devices_with_scheduler.yaml](../EDGE/examples/config/devices_with_scheduler.yaml)
- **Анализ производительности**: [SCALING_ANALYSIS.md](./SCALING_ANALYSIS.md)
- **ST_RS паттерны**: [ST_RS_PATTERNS_ANALYSIS.md](./ST_RS_PATTERNS_ANALYSIS.md)

## Changelog

### v1.0.0 (2025-11-14)
- ✅ Добавлены поля `poll_interval` и `priority` в `DeviceInfo`
- ✅ Реализована каскадная схема приоритетов (YAML > custom > DEFAULT)
- ✅ Обработка некорректных значений priority с fallback на DEFAULT
- ✅ Поддержка загрузки через `DeviceInfo.from_dict()`
- ✅ 3 новых юнит-теста (всего 24 теста, все проходят)
- ✅ Пример производственной конфигурации для 6 КУБов + 18 VFD
- ✅ Полная документация с примерами
