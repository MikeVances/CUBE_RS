# Возможности тестирования EDGE узла

## Обзор

Система CUBE_RS теперь имеет полнофункциональную среду для тестирования EDGE узла без реального оборудования. Эмулятор сети устройств позволяет проверять работу всех компонентов в реалистичных условиях.

## Что можно тестировать?

### ✅ 1. Работу EDGE узла с сетью из 24 устройств

```python
devices = create_production_network()  # 6 КУБов + 18 VFD
edge = EDGENodeEmulator(devices, storage)
edge.run(duration=10.0)  # Запуск на 10 секунд
```

**Результат**: EDGE узел опрашивает 24 устройства с приоритетами, сохраняет данные в storage.

### ✅ 2. Приоритетную схему опроса

```
CRITICAL (КУБы): 60 опросов за 10 сек (10 опросов на устройство)
HIGH (VFD важные): 30 опросов за 10 сек (5 опросов на устройство)
LOW (VFD обычные): 24 опроса за 10 сек (2 опроса на устройство)
```

**Подтверждено**: Критические устройства опрашиваются в 5 раз чаще низкоприоритетных.

### ✅ 3. Устойчивость к сбоям

```python
# Отключаем устройство
emulator.set_device_state(1, DeviceEmulatorState.OFFLINE)

# EDGE продолжает работать с остальными устройствами
edge.run(duration=5.0)
```

**Результат**: 92.9% успеха при одном отключенном устройстве из 24.

### ✅ 4. Работу с медленными устройствами

```python
# Устройства с медленным откликом (×3)
for device_id in [13, 14, 15]:
    emulator.set_device_state(device_id, DeviceEmulatorState.SLOW_RESPONSE)
```

**Результат**: КУБы сохраняют 100% успеха даже при медленных VFD.

### ✅ 5. YAML конфигурацию

Проверяется что параметры из `devices.yaml` применяются корректно:
- `poll_interval` для каждого устройства
- `priority` (CRITICAL, HIGH, LOW)

### ✅ 6. Формат данных в storage

```python
КУБ данные: ['device_type', 'slave_id', 'connection_status',
             'response_time_ms', 'temperature', 'humidity',
             'fan_speed', 'heater_status', 'last_update']

VFD данные: ['device_type', 'slave_id', 'connection_status',
             'response_time_ms', 'frequency', 'current',
             'voltage', 'power', 'status', 'last_update']
```

## Запуск тестов

### Юнит-тесты DeviceScheduler (24 теста)

```bash
cd EDGE
PYTHONPATH=$PWD pytest tests/test_device_scheduler.py -v
```

**Время выполнения**: ~1.3 секунды
**Покрытие**: Приоритеты, интервалы, YAML конфигурация, масштабируемость

### Интеграционные тесты с эмулятором (6 тестов)

```bash
cd EDGE
PYTHONPATH=$PWD pytest tests/test_edge_with_emulator.py -v -s
```

**Время выполнения**: ~25 секунд
**Покрытие**: Полный цикл работы EDGE с сетью устройств

### Интерактивный эмулятор (5 сценариев)

```bash
cd EDGE
PYTHONPATH=$PWD python tests/interactive_emulator.py
```

**Время выполнения**: ~33 секунды
**Сценарии**:
1. Нормальная работа (5 сек)
2. Устройство отключено (5 сек)
3. Медленные устройства (10 сек)
4. Нестабильное соединение (8 сек)
5. Пиковая нагрузка (5 сек)

## Результаты тестирования

### Производственный сценарий (10 секунд, 24 устройства)

```
📊 Результаты:
   Циклов: 140
   Опросов: 114
   Успех: 97.4%
   Среднее время: 27.9ms
   Устройств в storage: 24

🎯 По приоритетам:
   CRITICAL (КУБы): 60 опросов (avg 10.0 на устройство)
   HIGH (VFD важные): 30 опросов (avg 5.0 на устройство)
   LOW (VFD обычные): 24 опросов (avg 2.0 на устройство)
```

### Ключевые метрики

| Метрика | Значение | Цель | Статус |
|---------|----------|------|--------|
| Процент успеха | 97.4% | >95% | ✅ |
| Среднее время отклика | 27.9ms | <50ms | ✅ |
| КУБы: опросов/сек | 1.0 Hz | 1 Hz | ✅ |
| VFD HIGH: опросов/сек | 0.5 Hz | 0.5 Hz | ✅ |
| VFD LOW: опросов/сек | 0.2 Hz | 0.2 Hz | ✅ |

## Архитектура тестирования

```
┌─────────────────────────────────────────────────────────┐
│                  EDGENodeEmulator                        │
│  (Эмулятор полного EDGE узла)                           │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────┐      ┌──────────────────┐        │
│  │ DeviceScheduler  │◄────►│ NetworkEmulator  │        │
│  │ (Приоритеты)     │      │ (24 устройства)  │        │
│  └──────────────────┘      └──────────────────┘        │
│           │                         │                   │
│           ▼                         ▼                   │
│  ┌──────────────────────────────────────────┐          │
│  │         MockModbusStorage                │          │
│  │  (Хранилище данных устройств)           │          │
│  └──────────────────────────────────────────┘          │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## Компоненты

### 1. DeviceNetworkEmulator
**Файл**: [device_network_emulator.py](../EDGE/tests/device_network_emulator.py)

**Функции**:
- Эмуляция Modbus устройств (КУБ-1063, КУБ-1112, VFD-INVERTER)
- Реалистичное время отклика (10-100ms)
- Симуляция сбоев (1-10% в зависимости от типа)
- Генерация данных датчиков (температура, влажность, частота, ток)
- 4 состояния: ONLINE, OFFLINE, SLOW_RESPONSE, INTERMITTENT

### 2. EDGENodeEmulator
**Файл**: [test_edge_with_emulator.py](../EDGE/tests/test_edge_with_emulator.py)

**Функции**:
- Симуляция основного цикла EDGE узла
- Интеграция DeviceScheduler + NetworkEmulator
- Сохранение данных в MockModbusStorage
- Статистика и метрики работы

### 3. MockModbusStorage
**Файл**: [test_edge_with_emulator.py](../EDGE/tests/test_edge_with_emulator.py)

**Функции**:
- Эмуляция modbus_storage из start.py
- Хранение данных устройств
- Счетчик обновлений

## Примеры использования

### Пример 1: Базовое тестирование

```python
from device_network_emulator import create_production_network
from test_edge_with_emulator import EDGENodeEmulator, MockModbusStorage

# Создаем сеть
devices = create_production_network()
storage = MockModbusStorage()

# Создаем EDGE узел
edge = EDGENodeEmulator(devices, storage)

# Запускаем на 10 секунд
edge.run(duration=10.0)

# Получаем статистику
stats = edge.get_statistics()
print(f"Опросов: {stats['total_polls']}")
print(f"Успех: {stats['success_rate']}")
```

### Пример 2: Тестирование устойчивости к сбоям

```python
# Отключаем несколько устройств
edge.network_emulator.set_device_state(1, DeviceEmulatorState.OFFLINE)
edge.network_emulator.set_device_state(7, DeviceEmulatorState.OFFLINE)

# Запускаем
edge.run(duration=5.0)

# Проверяем что система работает
stats = edge.get_statistics()
assert float(stats['success_rate'].rstrip('%')) > 85.0
```

### Пример 3: Тестирование медленной сети

```python
# Делаем все VFD медленными
for device_id in range(7, 25):
    edge.network_emulator.set_device_state(
        device_id,
        DeviceEmulatorState.SLOW_RESPONSE
    )

# КУБы должны продолжать работать нормально
edge.run(duration=10.0)

# Проверяем КУБы
for device_id in range(1, 7):
    data = storage.get_data(device_id)
    assert data['connection_status'] == 'connected'
```

### Пример 4: Проверка данных в storage

```python
# Запускаем
edge.run(duration=5.0)

# Получаем данные КУБ-1063
kub_data = storage.get_data(1)

assert 'temperature' in kub_data
assert 'humidity' in kub_data
assert kub_data['connection_status'] == 'connected'
assert kub_data['response_time_ms'] < 50.0

print(f"Температура: {kub_data['temperature']}°C")
print(f"Влажность: {kub_data['humidity']}%")
```

## Интеграция в CI/CD

### GitHub Actions

```yaml
# .github/workflows/test.yml
name: EDGE Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd EDGE
          pip install -r requirements.txt

      - name: Run unit tests
        run: |
          cd EDGE
          PYTHONPATH=$PWD pytest tests/test_device_scheduler.py -v

      - name: Run integration tests
        run: |
          cd EDGE
          PYTHONPATH=$PWD pytest tests/test_edge_with_emulator.py -v
```

### Pre-commit hook

```bash
# .git/hooks/pre-commit
#!/bin/bash
cd EDGE
PYTHONPATH=$PWD pytest tests/test_device_scheduler.py -v
```

## Сравнение с реальными устройствами

| Аспект | Эмулятор | Реальные устройства |
|--------|----------|---------------------|
| Время отклика | 10-100ms | 50-200ms (RS485) |
| Процент сбоев | 1-10% | 1-5% (зависит от сети) |
| Стабильность данных | Медленное изменение | Реальные изменения |
| Скорость тестирования | 10 сек для 24 устройств | Требуется физическая сеть |
| Воспроизводимость | 100% | Зависит от окружения |
| Стоимость | Бесплатно | Требуется оборудование |

## Следующие шаги

### ✅ Реализовано:
1. DeviceNetworkEmulator с 24 устройствами
2. EDGENodeEmulator с полным циклом опроса
3. 6 интеграционных тестов
4. 24 юнит-теста DeviceScheduler
5. Интерактивный эмулятор с 5 сценариями
6. Полная документация

### ⏳ В планах:
1. **Интеграция DeviceScheduler в start.py**
   - Заменить текущий последовательный опрос на приоритетный
   - Использовать YAML конфигурацию для параметров опроса

2. **Расширение эмулятора**
   - Добавить симуляцию RS485 коллизий
   - Эмуляция CRC ошибок
   - Таймауты и повторные попытки

3. **Графический мониторинг**
   - Дашборд для визуализации опроса устройств
   - Real-time графики температуры, влажности
   - Алерты при сбоях

4. **Тестирование производительности**
   - Нагрузочное тестирование с 100+ устройств
   - Профилирование производительности
   - Оптимизация узких мест

5. **Тестирование с реальным оборудованием**
   - Сравнение эмулятора с реальными КУБ/VFD
   - Калибровка параметров эмулятора
   - Документация отличий

## Преимущества текущей системы

### 1. Быстрое тестирование
- **Полный цикл**: 25 секунд для 6 интеграционных тестов
- **Юнит-тесты**: 1.3 секунды для 24 тестов
- **Без оборудования**: Не требуется физическая сеть Modbus

### 2. Воспроизводимость
- Одинаковые результаты при повторных запусках
- Детерминированные сценарии
- Возможность отладки сложных ситуаций

### 3. Гибкость
- Легко добавлять новые сценарии
- Симуляция различных сбоев
- Тестирование edge cases

### 4. Покрытие
- ✅ Приоритетная схема опроса
- ✅ YAML конфигурация
- ✅ Устойчивость к сбоям
- ✅ Медленные устройства
- ✅ Формат данных storage
- ✅ Масштабируемость (24 устройства)

## Документация

- **Эмулятор**: [EMULATOR_AND_TESTING.md](./EMULATOR_AND_TESTING.md)
- **YAML интеграция**: [YAML_SCHEDULER_INTEGRATION.md](./YAML_SCHEDULER_INTEGRATION.md)
- **Масштабируемость**: [SCALING_ANALYSIS.md](./SCALING_ANALYSIS.md)
- **ST_RS паттерны**: [ST_RS_PATTERNS_ANALYSIS.md](./ST_RS_PATTERNS_ANALYSIS.md)

## Заключение

Система тестирования CUBE_RS EDGE позволяет:
- ✅ Разрабатывать без физического оборудования
- ✅ Быстро проверять изменения (25 сек полный цикл)
- ✅ Тестировать сложные сценарии (сбои, медленная сеть)
- ✅ Гарантировать качество через автоматические тесты
- ✅ Масштабировать систему с уверенностью

**Готовы к интеграции в production!** 🚀
