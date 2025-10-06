# 🔧 Руководство по добавлению нового типа устройства в EDGE систему

Благодаря гибкой архитектуре Variable System, добавление нового устройства занимает минимальное время. Рассмотрим пример добавления **КУБ-1150** (новое устройство освещения).

## 📋 **ШАГ 1: Анализ карты регистров нового устройства**

### 1.1 Изучите документацию устройства:
```
Пример КУБ-1150 регистры:
0x0090 - brightness_zone_1 (0-100%, scale: 0.1)
0x0091 - brightness_zone_2 (0-100%, scale: 0.1) 
0x0092 - lighting_mode (0=manual, 1=auto, 2=schedule)
0x0093 - power_consumption (Watts, scale: 1.0)
0x0094 - operating_hours (часы работы)
0x00C0 - active_alarms (битовое поле)
```

### 1.2 Определите специальные значения:
```
0x7FFF = "pending" (ожидание измерения)
0x7FFE = "break" (обрыв датчика)  
0x7FFD = "error" (ошибка измерения)
0x7FFC = "disabled" (отключен)
```

---

## 📝 **ШАГ 2: Добавление типа устройства**

### 2.1 Обновите `core/device_registry.py`:
```python
class DeviceType(Enum):
    """Поддерживаемые типы устройств"""
    KUB_1063 = "KUB-1063"  # Вентиляция
    KUB_1112 = "KUB-1112"  # Обогрев
    KUB_1150 = "KUB-1150"  # Освещение ← ДОБАВИТЬ
    UNKNOWN = "UNKNOWN"
```

---

## 🏗️ **ШАГ 3: Создание адаптера устройства**

### 3.1 Создайте файл `core/device_adapters/kub1150.py`:

Полная структура адаптера включает:
- **Определения типов переменных** - `VariableTypeDefinition` для каждого типа данных
- **Ссылки на регистры** - `VariableReference` связывающие переменные с адресами Modbus
- **Форматирование для бота** - красивый вывод с эмодзи
- **Обработка аварий** - критичные аварии и предупреждения
- **Legacy совместимость** - для работы со старым API

**Структура переменных КУБ-1150:**
```python
def _setup_variable_definitions(self):
    """Настройка определений типов переменных КУБ-1150"""
    type_definitions = [
        # Яркость освещения (процентные значения)
        VariableTypeDefinition(
            id=1, name="Brightness", var_type=VariableType.PERCENTAGE,
            scale=0.1, signed=False, unit="%", min_val=0.0, max_val=100.0,
            special_values={0x7FFF: "pending", 0x7FFE: "break", 0x7FFD: "error", 0x7FFC: "disabled"},
            description="Уровень яркости освещения"
        ),
        # Режим освещения
        VariableTypeDefinition(
            id=2, name="LightingMode", var_type=VariableType.INTEGER,
            scale=1.0, signed=False, unit="", min_val=0, max_val=2,
            description="Режим: 0=ручной, 1=авто, 2=расписание"
        ),
        # ... остальные типы
    ]
```

**Маппинг регистров:**
```python
def _setup_variable_references(self):
    """Привязка переменных к конкретным Modbus адресам"""
    variable_references = [
        VariableReference("brightness_zone_1", 0x0090, 1, description="Яркость зона 1"),
        VariableReference("brightness_zone_2", 0x0091, 1, description="Яркость зона 2"),
        VariableReference("lighting_mode", 0x0092, 2, description="Режим освещения"),
        VariableReference("power_consumption", 0x0093, 3, description="Потребляемая мощность"),
        # ... остальные переменные
    ]
```

**Форматирование для Telegram:**
```python
def format_for_display(self, device_manager) -> str:
    """Красивый вывод для Telegram бота"""
    lines = []
    lines.append("💡 <b>КУБ-1150 ОСВЕЩЕНИЕ:</b>")
    
    # Яркость по зонам
    lines.append("\n🌞 <b>ЯРКОСТЬ:</b>")
    for var_name, label in [("brightness_zone_1", "Зона 1"), ("brightness_zone_2", "Зона 2")]:
        value = device_manager.get_variable_value(var_name)
        if value is not None:
            lines.append(f"  • {label}: <code>{value:.1f}%</code>")
    
    return "\n".join(lines)
```

---

## 🔧 **ШАГ 4: Регистрация адаптера**

### 4.1 Обновите `core/device_adapters/factory.py`:
```python
from .kub1150 import KUB1150Adapter  # ← ДОБАВИТЬ

def get_device_adapter(device_type: DeviceType) -> Optional[DeviceAdapter]:
    """Фабрика адаптеров устройств с кэшированием"""
    # ... существующий код ...
    elif device_type == DeviceType.KUB_1150:  # ← ДОБАВИТЬ
        adapter = KUB1150Adapter()
    # ... остальной код ...
```

### 4.2 Обновите `core/device_adapters/__init__.py`:
```python
from .kub1150 import KUB1150Adapter  # ← ДОБАВИТЬ

__all__ = [
    "DeviceAdapter", 
    "get_device_adapter",
    "KUB1063Adapter",
    "KUB1112Adapter", 
    "KUB1150Adapter",  # ← ДОБАВИТЬ
]
```

---

## 🧪 **ШАГ 5: Создание теста**

### 5.1 Создайте тест `test_kub1150.py`:
```python
#!/usr/bin/env python3
"""Тест адаптера КУБ-1150"""

from core.device_adapters import get_device_adapter
from core.device_registry import DeviceType

def test_kub1150_adapter():
    """Тест КУБ-1150 адаптера"""
    print("🧪 Тестируем KUB1150 Adapter...")
    
    # Создаём адаптер
    adapter = get_device_adapter(DeviceType.KUB_1150)
    print(f"✅ Адаптер создан: {adapter.device_type}")
    
    # Создаём менеджер переменных
    device_manager = adapter.create_device_manager(device_id=1)
    
    # Тестовые данные регистров
    test_register_data = {
        0x0090: 750,    # brightness_zone_1 = 75.0%
        0x0091: 500,    # brightness_zone_2 = 50.0%  
        0x0092: 1,      # lighting_mode = автоматический
        0x0093: 2500,   # power_consumption = 2500W
        0x00C0: 0,      # active_alarms = нет аварий
    }
    
    # Обновляем данные и тестируем
    device_manager.update_from_registers(test_register_data)
    
    # Проверяем форматирование
    display_text = adapter.format_for_display(device_manager)
    print("✅ Форматированный текст для бота:")
    print(display_text)

if __name__ == "__main__":
    test_kub1150_adapter()
```

---

## 🏭 **ШАГ 6: Обновление конфигурации**

### 6.1 Добавьте устройство в `config/devices.yaml`:
```yaml
devices:
  # ... существующие устройства ...
  
  # Новое устройство КУБ-1150
  - device_id: 11
    device_type: "KUB-1150"
    slave_id: 11
    name: "Освещение корпус 1"
    description: "Система освещения и энергоменеджмента"
    enabled: true
    location: "Корпус №1"
    
  - device_id: 12
    device_type: "KUB-1150"
    slave_id: 12
    name: "Освещение корпус 2" 
    description: "Система освещения и энергоменеджмента"
    enabled: true
    location: "Корпус №2"
```

---

## 🧪 **ШАГ 7: Тестирование**

### 7.1 Запустите тесты:
```bash
# Тест нового адаптера
python test_kub1150.py

# Общий тест архитектуры
python test_flexible_architecture.py

# Тест работы с ботом
python apps/edge/telegram_bot/bot_main.py
```

### 7.2 Проверьте в Telegram боте:
```
/devices - Должны появиться новые КУБ-1150 устройства
/device_11 - Подробная информация по освещению
/status - Общий статус включает освещение
```

---

## 📱 **ШАГ 8: Расширение команд бота (опционально)**

### 8.1 Специальные команды для нового устройства:
```python
# В apps/edge/telegram_bot/bot_main.py

@dp.message_handler(commands=['lighting'])
async def lighting_status(message: types.Message):
    """Статус всех систем освещения"""
    lighting_devices = registry.get_devices_by_type(DeviceType.KUB_1150)
    
    if not lighting_devices:
        await message.reply("💡 Системы освещения не найдены")
        return
    
    lines = ["💡 <b>СОСТОЯНИЕ ОСВЕЩЕНИЯ:</b>\n"]
    
    for device in lighting_devices:
        adapter = get_device_adapter(DeviceType.KUB_1150)
        device_manager = adapter.create_device_manager(device.device_id)
        
        # Получение актуальных данных...
        status = adapter.format_for_display(device_manager)
        lines.append(f"<b>{device.name}:</b>")
        lines.append(status)
        lines.append("")
    
    await message.reply("\n".join(lines), parse_mode="HTML")
```

---

## 📊 **ШАГ 9: Документирование (рекомендуется)**

### 9.1 Создайте техническую документацию:
- **Карта регистров** в формате PDF или MD
- **Примеры значений** и их интерпретация  
- **Специальные случаи** и обработка ошибок

### 9.2 Обновите пользовательскую документацию:
- Добавьте новый тип в `USER_DEPLOYMENT_GUIDE.md`
- Опишите новые команды и возможности
- Приведите примеры конфигурации

---

## ✅ **ИТОГО: Checklist добавления нового устройства**

### 🔥 **Минимальный набор (30 минут работы):**
- [ ] Добавить `DeviceType.NEW_DEVICE` в `core/device_registry.py`
- [ ] Создать адаптер `core/device_adapters/new_device.py`
- [ ] Зарегистрировать в фабрике `core/device_adapters/factory.py`
- [ ] Добавить импорт в `core/device_adapters/__init__.py`
- [ ] Добавить устройства в `config/devices.yaml`

### 🎯 **Расширенный набор (1 час работы):**
- [ ] Создать тест `test_new_device.py`
- [ ] Добавить специальные команды в бот
- [ ] Протестировать интеграцию с системой
- [ ] Создать документацию регистров
- [ ] Обновить пользовательскую документацию

### 🚀 **Полная интеграция (2 часа работы):**
- [ ] Добавить аварийные уведомления
- [ ] Настроить пороговые значения
- [ ] Создать графики и отчеты
- [ ] Добавить автоматизацию и сценарии
- [ ] Провести нагрузочное тестирование

---

## 🎯 **ПРЕИМУЩЕСТВА АРХИТЕКТУРЫ VARIABLE SYSTEM:**

### ✅ **Быстрое развитие:**
- **30 минут** на добавление базовой поддержки устройства
- **Автоматическая** обработка специальных значений (break, error, disabled)
- **Готовое** форматирование для Telegram бота с эмодзи

### ✅ **Надежность:**
- **Типобезопасность** - все переменные имеют строгие типы
- **Валидация** - автоматическая проверка диапазонов значений
- **Legacy совместимость** - работает со старым API

### ✅ **Масштабируемость:**
- **Кэширование адаптеров** - один экземпляр на тип устройства
- **Гибкий маппинг** - переменные независимы от регистров
- **Расширяемость** - легко добавить новые типы данных

**Благодаря Variable System добавление нового типа устройства не требует изменения основного кода системы!** 🚀

---

## 📚 **ССЫЛКИ НА ДОКУМЕНТАЦИЮ:**

- **`USER_DEPLOYMENT_GUIDE.md`** - Руководство пользователя
- **`MULTI_DEVICE_ARCHITECTURE.md`** - Техническая архитектура
- **`test_flexible_architecture.py`** - Примеры использования Variable System
- **`core/device_adapters/`** - Существующие адаптеры КУБ-1063/1112

**Добро пожаловать в мир гибкой архитектуры EDGE!** 🎉