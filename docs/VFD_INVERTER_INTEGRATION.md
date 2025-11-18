# 🔌 Интеграция VFD Inverter в EDGE систему

## Описание

VFD (Variable Frequency Drive) Inverter - это частотный преобразователь (регулятор скорости) для управления электродвигателями. Устройство поддерживает протокол Modbus RTU/TCP и предоставляет 72 регистра мониторинга.

## ✅ Что реализовано

### 1. Адаптер устройства
**Файл:** `EDGE/core/device_adapters/vfd_inverter.py`

**Поддерживаемые регистры (71 регистр):**

#### Основные параметры мониторинга:
- `running_state` - Состояние работы (1=вперед, 2=назад, 3=стоп)
- `fault_code` - Код ошибки
- `set_frequency` - Заданная частота (Hz)
- `running_frequency` - Текущая частота (Hz)
- `running_speed` - Скорость двигателя (RPM)
- `output_voltage` - Выходное напряжение (V)
- `output_current` - Выходной ток (A)
- `output_power` - Выходная мощность (kW)
- `dc_bus_voltage` - Напряжение DC шины (V)
- `output_torque` - Момент на валу (Nm)

#### Температуры:
- `motor_temperature` - Температура двигателя (°C)
- `igbt_temperature` - Температура IGBT/радиатора (°C)

#### Время работы и энергия:
- `cumulative_running_time` - Общее время работы (Hour)
- `accumulated_power_on_time` - Общее время под напряжением (Hour)
- `cumulative_power_consumption` - Общее потребление энергии (kWh)

#### История ошибок (последние 3):
- `fault_third_code` - Последняя ошибка
- `fault_second_code` - Предпоследняя ошибка
- `fault_first_code` - Третья с конца ошибка
- Для каждой ошибки: частота, ток, напряжение, температура, время

#### Информация об устройстве:
- `serial_number_low` / `serial_number_high` - Серийный номер
- `motor_boot_version` - Версия загрузчика
- `cpu_type` - Тип CPU
- `power_board_hw_version` - Версия hardware платы питания
- `power_board_sw_version` - Версия software платы питания
- `control_board_sw_version` - Версия software платы управления
- `product_number` - Номер модели
- `manufacturer_code` - Код производителя

### 2. Регистрация в системе
- ✅ Добавлен тип `DeviceType.VFD_INVERTER` в `device_registry.py`
- ✅ Зарегистрирован в `factory.py`
- ✅ Автоматическое создание через Device Registry

### 3. Тестовое покрытие
**Файл:** `EDGE/tests/test_vfd_inverter.py`

**6 тестов:**
1. ✅ Базовая проверка адаптера
2. ✅ Парсинг значений регистров
3. ✅ Парсинг данных устройства
4. ✅ Форматирование для отображения
5. ✅ Аварии и предупреждения
6. ✅ Проверка адресов регистров

**Запуск тестов:**
```bash
cd EDGE
python tests/test_vfd_inverter.py
```

## 📝 Как добавить VFD устройство

### Шаг 1: Настройте физическое подключение

**Modbus RTU (RS485):**
- Подключите VFD к RS485 порту EDGE устройства
- Настройте параметры связи на VFD:
  - Скорость: 9600 baud (по умолчанию)
  - Формат: 8N1
  - Slave ID: установите уникальный адрес (например, 10)

**Modbus TCP:**
- Настройте IP адрес VFD
- Убедитесь что порт 502 доступен

### Шаг 2: Добавьте устройство в конфигурацию

Отредактируйте файл `config/devices.yaml`:

```yaml
devices:
  # Ваши существующие устройства...

  # Новый VFD Inverter
  - device_id: 10
    device_type: "VFD-INVERTER"
    slave_id: 10  # Modbus Slave ID устройства
    name: "Вентилятор главный - VFD"
    description: "Частотный преобразователь основного вентилятора"
    location: "Вентиляционная система"
    enabled: true
```

**Параметры:**
- `device_id` - уникальный ID в системе EDGE (любое число)
- `device_type` - обязательно `"VFD-INVERTER"`
- `slave_id` - Modbus Slave ID (должен совпадать с настройкой VFD)
- `name` - понятное имя устройства
- `enabled` - `true` для активации опроса

### Шаг 3: Перезапустите EDGE

```bash
cd EDGE
python start.py
```

Или если используете системный сервис:
```bash
sudo systemctl restart edge
```

## 🔍 Проверка работы

### 1. Через Health API

```bash
# Проверка общего состояния
curl http://localhost:8090/health

# Проверка конкретного устройства
curl http://localhost:8090/devices/10
```

### 2. Через логи

```bash
tail -f EDGE/logs/edge.log | grep VFD
```

Вы должны увидеть:
```
✅ Загружено устройство: Вентилятор главный - VFD (ID: 10)
📖 Начат опрос устройства VFD-INVERTER (slave_id=10)
📊 VFD-10: running_state=forward, freq=50.0Hz, current=12.5A
```

### 3. Через Telegram bot (если настроен)

Отправьте команду боту:
```
/devices
/device 10
/status
```

## 📊 Мониторинг данных

### Доступ к данным через Device Registry

```python
from core.device_registry import get_device_registry

registry = get_device_registry()

# Получить данные VFD
vfd_data = registry.get_device_data(device_id=10)

print(f"Частота: {vfd_data['running_frequency']} Hz")
print(f"Ток: {vfd_data['output_current']} A")
print(f"Температура: {vfd_data['motor_temperature']}°C")
```

### WebSocket подписка (если включен)

```javascript
const ws = new WebSocket('ws://edge-ip:8000');

ws.on('message', (data) => {
  const device_data = JSON.parse(data);
  if (device_data.device_id === 10) {
    console.log('VFD data:', device_data);
  }
});
```

### MQTT подписка (если включен)

```bash
mosquitto_sub -h localhost -t "edge/devices/10/#"
```

## ⚠️ Аварии и предупреждения

Адаптер автоматически детектирует:

### Критические аварии:
- ❌ Активная ошибка (fault_code ≠ 0)
- ❌ Перегрев IGBT (>90°C)
- ❌ Перегрев мотора (>100°C)
- ❌ Перегрузка по току (>100A)
- ❌ Выход DC шины за пределы (200-450V)

### Предупреждения:
- ⚠️ Высокая температура IGBT (70-90°C)
- ⚠️ Высокая температура мотора (80-100°C)
- ⚠️ Высокий ток (80-100A)
- ⚠️ Наличие ошибок в истории

## 🎯 Примеры использования

### 1. Простой мониторинг VFD

```python
from core.device_registry import get_device_registry
from core.device_adapters import get_device_adapter
from core.device_registry import DeviceType

registry = get_device_registry()
adapter = get_device_adapter(DeviceType.VFD_INVERTER)

# Получаем данные
device_info = registry.get_device(device_id=10)
device_data_dict = registry.get_device_data(device_id=10)

# Форматируем для отображения
if adapter:
    # Конвертируем dict в DeviceData
    from core.device_adapters.base import DeviceData
    device_data = DeviceData(
        device_id=10,
        device_type="VFD-INVERTER",
        registers=device_data_dict,
        raw_registers={},
        status={}
    )

    print(adapter.format_for_display(device_data))
```

### 2. Проверка аварий

```python
# Проверяем критические аварии
alarms = adapter.get_critical_alarms(device_data)
if alarms:
    print("🚨 КРИТИЧЕСКИЕ АВАРИИ:")
    for alarm in alarms:
        print(f"  - {alarm}")
        # Отправить уведомление
        send_alert_to_telegram(alarm)

# Проверяем предупреждения
warnings = adapter.get_warnings(device_data)
if warnings:
    print("⚠️  ПРЕДУПРЕЖДЕНИЯ:")
    for warning in warnings:
        print(f"  - {warning}")
```

### 3. Множество VFD устройств

```yaml
# config/devices.yaml
devices:
  - device_id: 10
    device_type: "VFD-INVERTER"
    slave_id: 10
    name: "Вентилятор 1"

  - device_id: 11
    device_type: "VFD-INVERTER"
    slave_id: 11
    name: "Вентилятор 2"

  - device_id: 12
    device_type: "VFD-INVERTER"
    slave_id: 12
    name: "Насос"
```

## 🐛 Troubleshooting

### Проблема: Устройство не опрашивается

**Проверьте:**
1. Правильность Slave ID в конфигурации
2. Физическое подключение RS485
3. Настройки скорости (baudrate) совпадают
4. Устройство `enabled: true` в конфигурации

**Логи:**
```bash
grep "VFD" EDGE/logs/edge.log
```

### Проблема: Получаю ошибки Modbus

**Возможные причины:**
- Неправильный Slave ID
- Таймаут слишком короткий (увеличьте в `config/app_config.yaml`)
- Проблемы с RS485 линией (проверьте терминаторы)

**Решение:**
```yaml
# config/app_config.yaml
rs485:
  timeout: 3.0  # Увеличьте таймаут
  window_duration: 10  # Увеличьте окно опроса
```

### Проблема: Неправильные значения

**Проверьте:**
- Документацию вашего конкретного VFD (регистры могут отличаться)
- Масштабные коэффициенты (`scale` в RegisterInfo)
- Формат данных (signed/unsigned)

## 📚 Дополнительные ресурсы

- [EDGE README](../EDGE/README.md)
- [Device Adapters Architecture](./EDGE_AUDIT_REPORT_2025-11-13.md#31-процесс-добавления-нового-типа-устройства)
- [Modbus Configuration](../config/app_config.yaml)
- [Device Registry API](../EDGE/core/device_registry.py)

## 🎉 Готово!

Теперь ваш VFD Inverter полностью интегрирован в систему EDGE и будет:
- ✅ Автоматически опрашиваться каждые N секунд
- ✅ Сохранять данные в локальную БД
- ✅ Публиковать данные через WebSocket/MQTT (если включено)
- ✅ Отображаться в Telegram боте
- ✅ Отправлять аварии и предупреждения
- ✅ Доступен через Health API

---

**Автор:** Senior DevOps/Platform Engineer
**Дата:** 2025-11-14
**Версия:** 1.0
