"""
file: docs/edge/DEVICE_ADAPTER_GUIDE.md
description: Руководство для производителя по разработке адаптера устройства EDGE.
author: EDGE Full-Stack RS485 Senior Engineer GPT
"""

# Руководство по разработке адаптера устройства для EDGE

Это руководство предназначено для производителей, которые хотят интегрировать своё RS‑485/Modbus устройство в EDGE‑узел. Документ описывает полный цикл работ — от подготовки Modbus‑карты до отображения метрик и аварий на дашборде. В качестве референса используется адаптер КУБ‑1063, так как он покрывает большинство типовых сценариев.

## 1. Архитектура EDGE

Пайплайн обработки данных выглядит так:

```
RS-485 → UniversalModbusReader → DeviceAdapter → DeviceRegistry/SQLite → Room snapshots → Telegram/Streamlit UI
```

Адаптер отвечает за:

1. Описание регистров (адрес, тип, единицы измерения).
2. Парсинг сырых значений и нормализацию (масштаб, знак, спец‑коды «обрыв», «ожидание»).
3. Построение человекочитаемых аварий/предупреждений.
4. Экспорт ключевых метрик для UI (атрибут `DEFAULT_DASHBOARD_METRICS`).

## 2. Подготовка Modbus‑карты

Составьте таблицу регистров с колонками:

| Адрес | Название | FC | Тип (INT/FLOAT/BITFIELD) | Масштаб | Ед. изм. | Описание | Спец‑коды |

Пример из КУБ‑1063 (`docs/Cube-1063_modbus registers.md`).

Рекомендуется: 
- Сгруппировать регистры по функциям (аналоговые входы, выходы, таймеры).
- Прописать спецзначения (`0x7FFF` – ожидание данных, `0x7FFE` – обрыв и т.п.).
- Для битовых полей (digital outputs/alarms) составить словари значений.

## 3. Создание класса адаптера

1. Разместите файл в `EDGE/core/device_adapters/<название>.py`.
2. Зарегистрируйте устройство в `core/device_adapters/device_catalog.yaml`:

```yaml
- type: "KUB-1063"
  adapter: "core.device_adapters.kub1063.KUB1063Adapter"
  poll_interval: 20.0
```

3. Реализуйте класс, наследующий `DeviceAdapter`. Минимальный скелет:

```python
from .base import DeviceAdapter, RegisterInfo, DeviceData, ValueType, RegisterType

class MyDeviceAdapter(DeviceAdapter):
    device_type = "MY-DEVICE"
    DEFAULT_DASHBOARD_METRICS = ["temp_inside", "pressure", ...]

    def __init__(self):
        self._registers = {
            "software_version": RegisterInfo(0x0301, "software_version", ValueType.VERSION,
                                             description="Версия ПО", register_type=RegisterType.INPUT),
            # ... остальные регистры
        }

    @property
    def register_map(self) -> Dict[str, RegisterInfo]:
        return self._registers

    def parse_register_value(self, register_name: str, raw_value: int) -> tuple[Any, str]:
        # применяем знаковость, масштаб и спецзначения
        info = self._registers[register_name]
        special = self._check_special_values(raw_value, info)
        if special:
            return special, special
        value = self._apply_scale_and_sign(raw_value, info)
        return value, "ok"

    def format_for_display(self, data: DeviceData) -> str:
        # текст для Telegram/бота
        return "..."

    def get_critical_alarms(self, data: DeviceData) -> List[str]:
        return []

    def get_warnings(self, data: DeviceData) -> List[str]:
        return []
```

### 3.1. DEFAULT_DASHBOARD_METRICS

Укажите список ключей (из `register_map` или Variable System), которые должны отображаться на дашборде сразу после добавления устройства. Это позволяет автоматизировать выбор чекбоксов.

Для КУБ‑1063:

```python
DEFAULT_DASHBOARD_METRICS = [
    "temp_inside",
    "temp_target",
    "humidity",
    "pressure",
    "ventilation_level",
    "ventilation_target",
]
```

### 3.2. RegisterInfo

`RegisterInfo` описывает каждый регистр:

```python
RegisterInfo(
    address=0x008D,
    name="temp_inside_1",
    value_type=ValueType.TEMPERATURE,
    scale=0.1,
    signed=True,
    description="Температура внутри 1",
    special_values={0x7FFF: "pending", 0x7FFE: "break"},
    register_type=RegisterType.INPUT,
)
```

Используйте `RegisterType.INPUT` для FC04 и `RegisterType.HOLDING` для FC03.

### 3.3. Обработка спецзначений

Метод `_check_special_values` возвращает статус, если значение равно одному из спецкодотов. Статус будет использован UI и ботом.

## 4. Variable System (для сложных устройств)

Если устройство имеет десятки переменных, используйте `KUBVariableMapper` (см. `kub1063.py`). Подход:

1. Описываете типы (`VariableTypeDefinition`): масштаб, знак, спецзначения.
2. Регистрируете переменные через `VariableReference(name, address, type_id, description="...")`.
3. Менеджер `DeviceVariableManager` позволяет собирать значения, статусы и предоставлять их боту/дашборду.

Плюсы: один раз описываете тип — далее масштаб/единицы подтягиваются автоматически.

## 5. Аварии и предупреждения

Используйте карты аварий КУБ‑1063 как пример (словарь `ACTIVE_ALARM_DESCRIPTIONS`). Алгоритм:

```python
alarm_hex_values = []
for i in range(4):
    alarm_val = device_manager.get_variable_value(f"active_alarms_{i}")
    if alarm_val:
        for bit in range(16):
            if alarm_val & (1 << bit):
                bit_index = i * 16 + bit
                description = ACTIVE_ALARM_DESCRIPTIONS.get(bit_index)
                if description:
                    alarms.append(f"🚨 {description}")
```

Если важно знать состояние конкретного реле (например, аварийного) — определите соответствующий бит и предоставьте helper для UI. В КУБ‑1063 бит 47 сигнализирует «Аварийное реле включено», и дашборд выводит «Состояние аварийного реле: ВКЛ/ВЫКЛ».

## 6. Сохранение метрик для UI

`DEFAULT_DASHBOARD_METRICS` задаёт дефолтные чекбоксы. Дополнительно можно переопределить подписи через `DEVICE_METRIC_LABEL_OVERRIDES` (в `app.py`).

## 7. Интеграция с Device Registry

После добавления адаптера и записи в `device_catalog.yaml` можно добавить устройство через `config/devices.yaml` или автоматический сканер. Формат:

```yaml
- device_id: 5
  device_type: MY-DEVICE
  slave_id: 7
  name: 'My Device #7'
  enabled: true
  room: 'Птичник-1'
  poll_interval: 15.0
```

`DeviceRegistry` проверит уникальность `slave_id` и сохранит конфигурацию в `config/devices.yaml`.

## 8. Тестирование адаптера

1. Создайте скрипт в `EDGE/tests/test_<device>.py` по аналогии с `test_kub1063.py`. Полезно иметь:
   - живой опрос (`run_live_*`),
   - эмулятор (`DeviceNetworkEmulator`).
2. Обратите внимание на `UniversalModbusReader`: адаптер должен корректно отвечать на любые ошибки (CRC, timeout).
3. Перед релизом прогоняйте `pytest EDGE/tests/test_<device>.py`.

## 9. Проверка UI и Telegram

- Запустите `EDGE/start.py` с включённым Telegram и Streamlit дашбордом (см. сервисы в `config/app_config.yaml`).
- Убедитесь, что новые метрики отображаются автоматически и аварии генерируют сообщения в боте.

## 10. Чеклист для производителя

1. **Документация Modbus**: подготовлен файл регистров с описаниями.
2. **Класс адаптера**:
   - описаны все регистры (`register_map`),
   - реализованы `parse_register_value`, `format_for_display`, `get_critical_alarms`, `get_warnings`,
   - указан `DEFAULT_DASHBOARD_METRICS`.
3. **device_catalog.yaml**: добавлена запись о типе.
4. **Тесты**: создан файл в `EDGE/tests/`, проверены основные случаи.
5. **UI**: проверено, что метрики и аварии отображаются корректно в Streamlit и Telegram.
6. **Документация**: описаны особенности протокола (скейлы, спецзначения, аварийные битовые поля).

Следуя этому пособию, производитель сможет быстро подготовить адаптер для своего устройства, а EDGE‑узел автоматически подхватит все необходимые настройки.
