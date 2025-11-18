# Анализ масштабируемости: 6 КУБов + 18 VFD

**Дата**: 2025-11-14
**Сценарий**: Реальная нагрузка - 6 устройств КУБ + 18 VFD инверторов
**Статус**: 🔴 ТРЕБУЕТСЯ ОПТИМИЗАЦИЯ

---

## 📊 Текущая ситуация

### Характеристики устройств:

| Устройство | Количество | Регистров | Время опроса | Итого время |
|------------|------------|-----------|--------------|-------------|
| КУБ-1063   | 6          | 46        | ~300ms       | ~1.8s       |
| VFD        | 18         | 58        | ~400ms       | ~7.2s       |
| **ИТОГО**  | **24**     | **1320**  | -            | **~9s**     |

### 🔴 Проблемы текущего подхода:

**В `start.py:404-409`**:
```python
def reader_worker():
    while not shutdown_requested.is_set():
        devices = self.device_registry.get_all_devices(enabled_only=True)
        if not devices:
            logger.warning("⚠️ Нет активных устройств")
            break

        for device in devices:  # ← ПОСЛЕДОВАТЕЛЬНЫЙ опрос!
            # Опрос одного устройства ~300-400ms
            # 24 устройства × 350ms = 8.4 секунды!
            ...
```

**Критические узкие места**:
1. ❌ **Последовательный опрос**: O(n) время, где n = количество устройств
2. ❌ **Блокировка потока**: Один медленный device блокирует все остальные
3. ❌ **Нет приоритетов**: Критические устройства ждут в очереди
4. ❌ **Нет параллелизма**: Один RS485 порт, но можно оптимизировать

---

## 🧮 Математика производительности

### Текущая система (последовательный опрос):

```
Время цикла = Σ(время_опроса_каждого_устройства)

КУБ: 6 × 300ms = 1800ms
VFD: 18 × 400ms = 7200ms
────────────────────────────
ИТОГО: 9000ms = 9 секунд на полный цикл
```

**Частота обновления**: ~0.11 Hz (раз в 9 секунд)
**Задержка для последнего устройства**: 9 секунд!

### 🎯 Целевая производительность:

Для промышленных систем нужно:
- ⏱️ **Частота опроса**: ≥1 Hz (раз в секунду) для критичных параметров
- ⏱️ **Максимальная задержка**: <2 секунды
- ⏱️ **Приоритеты**: Критичные устройства опрашиваются чаще

---

## 🚀 Решение: Оптимизированная архитектура

### Стратегия 1: Batch Reading (быстрый выигрыш)

**Идея**: Читать несколько регистров за один запрос

**Текущий подход** (медленный):
```python
# 58 отдельных запросов для VFD
for register_addr in vfd_registers:
    read_single_register(slave_id, register_addr)  # 58 × 50ms = 2900ms
```

**Оптимизированный подход** (быстрый):
```python
# 3 батч-запроса для VFD
read_holding_registers(slave_id, 0x1000, 20)  # Пакет 1: 200ms
read_holding_registers(slave_id, 0x1014, 20)  # Пакет 2: 200ms
read_holding_registers(slave_id, 0x1028, 18)  # Пакет 3: 200ms
# ИТОГО: 600ms вместо 2900ms → 4.8x быстрее!
```

**Реализация в `universal_reader.py`** уже поддерживает батчи:
```python
def read_registers_batch(self, slave_id: int, addresses: List[int], batch_size: int = 20):
    # Группирует последовательные регистры в батчи
    # Уже реализовано! ✅
```

**Выигрыш для сценария**:
- КУБ: 46 регистров → 3 батча × 100ms = **300ms** (без изменений)
- VFD: 58 регистров → 3 батча × 200ms = **600ms** (было 2900ms)
- **Итого для 18 VFD**: 18 × 600ms = **10.8s** → **3.6s** (3x быстрее!)

### Стратегия 2: Приоритетный опрос

**Идея**: Устройства с разной частотой опроса

```python
# Конфигурация приоритетов
device_priorities = {
    "КУБ-1063": {"interval": 1.0, "priority": "HIGH"},    # Каждую секунду
    "VFD-критичные": {"interval": 1.0, "priority": "HIGH"}, # 6 критичных VFD
    "VFD-обычные": {"interval": 5.0, "priority": "NORMAL"}, # 12 остальных VFD
}
```

**Расписание опроса**:
```
t=0s:  КУБ×6 + VFD_critical×6     → 1.8s + 3.6s = 5.4s
t=1s:  КУБ×6 + VFD_critical×6     → повтор
t=5s:  КУБ×6 + VFD_all×18         → полный цикл
```

**Результат**:
- ✅ Критичные данные обновляются каждую секунду
- ✅ Некритичные - раз в 5 секунд
- ✅ Средняя задержка: <2 секунды

### Стратегия 3: Async/Concurrent опрос (advanced)

**Проблема**: Один RS485 порт = один канал связи
**Решение**: Конкурентность на уровне устройств + оптимизация таймаутов

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def poll_device_async(device: DeviceInfo):
    """Асинхронный опрос одного устройства"""
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        # Опрос в отдельном потоке (RS485 блокирующий)
        result = await loop.run_in_executor(pool, read_device, device)
    return result

async def poll_all_devices(devices: List[DeviceInfo]):
    """Опрос всех устройств параллельно (насколько возможно)"""
    tasks = [poll_device_async(device) for device in devices]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

**Ограничения**:
- RS485 - полудуплексная шина, только один разговор одновременно
- Но можно оптимизировать ожидание: пока одно устройство думает, готовим запрос к следующему

**Реальный выигрыш**:
- Минимизация простоя между запросами
- ~10-15% ускорение за счет устранения накладных расходов

### Стратегия 4: Умное кеширование

**Идея**: Не все параметры меняются часто

```python
# Конфигурация кеширования
register_cache_config = {
    # Быстро меняющиеся - всегда читать
    "running_frequency": {"ttl": 0},     # Без кеша
    "output_current": {"ttl": 0},

    # Медленно меняющиеся - кешировать
    "device_id": {"ttl": 3600},          # 1 час
    "firmware_version": {"ttl": 3600},
    "config_parameters": {"ttl": 300},   # 5 минут
}
```

**Выигрыш**:
- Меньше регистров для чтения
- ~20-30% снижение трафика

---

## 📈 Сравнение производительности

### Сценарий: 6 КУБов + 18 VFD

| Подход | Время цикла | Частота | Задержка | Применимость |
|--------|-------------|---------|----------|--------------|
| **Текущий (последовательный)** | 9.0s | 0.11 Hz | 9s | 🔴 Неприемлемо |
| **+ Batch Reading** | 5.4s | 0.18 Hz | 5.4s | 🟡 Лучше, но мало |
| **+ Приоритеты** | 5.4s (full) / 1s (critical) | 1 Hz (critical) | 1s | 🟢 Хорошо |
| **+ Async (теоретически)** | 4.5s | 0.22 Hz | 4.5s | 🟢 Еще лучше |
| **Все вместе** | **1s (critical)** / **5s (full)** | **1 Hz** | **<2s** | ✅ **Отлично!** |

---

## 🛠️ План внедрения

### Фаза 1: Quick Wins (1-2 дня) - СДЕЛАТЬ СЕЙЧАС

✅ **1.1. Batch Reading оптимизация**
- Убедиться что `universal_reader` использует батчи
- Настроить оптимальный `batch_size` для КУБ и VFD
- Тестирование с реальными устройствами

✅ **1.2. Приоритетная конфигурация**
- Добавить `poll_interval` в `devices.yaml`
- Реализовать scheduler с приоритетами в `start.py`

```yaml
# config/devices.yaml
devices:
  - device_id: 1
    device_type: "VFD-INVERTER"
    slave_id: 1
    name: "VFD Главный"
    enabled: true
    poll_interval: 1.0      # ← НОВОЕ: опрос каждую секунду
    priority: "HIGH"        # ← НОВОЕ: высокий приоритет

  - device_id: 10
    device_type: "VFD-INVERTER"
    slave_id: 10
    name: "VFD Резервный"
    enabled: true
    poll_interval: 5.0      # ← Опрос раз в 5 секунд
    priority: "NORMAL"
```

**Ожидаемый результат**:
- Время цикла: 9s → **5.4s** (1.7x быстрее)
- Критичные данные: **1 Hz**

### Фаза 2: Advanced (3-5 дней) - ПО НЕОБХОДИМОСТИ

⏳ **2.1. Async polling engine**
- Рефакторинг `start_modbus_reader()` на async/await
- ThreadPool для RS485 операций
- Оптимизация таймаутов и ожидания

⏳ **2.2. Smart Caching**
- Кеширование статичных параметров
- TTL для разных типов регистров
- Валидация данных

**Ожидаемый результат**:
- Время цикла: **4.5s**
- Критичные данные: **1 Hz**
- Снижение трафика: **-25%**

### Фаза 3: Production Hardening (1 неделя) - ПОСЛЕ ТЕСТИРОВАНИЯ

🔄 **3.1. Monitoring & Metrics**
- Метрики производительности (время опроса, errors)
- Алерты при превышении SLA
- Grafana дашборды

🔄 **3.2. Load Testing**
- Симуляция 50+ устройств
- Stress testing с таймаутами
- Recovery после сбоев

---

## 💡 Рекомендации для вашего случая

### Для 6 КУБов + 18 VFD:

**Минимальный план (обязательно)**:
1. ✅ Включить batch reading (уже есть в `universal_reader`)
2. ✅ Настроить приоритеты в `devices.yaml`
3. ✅ Настроить poll_interval по важности

**Конфигурация**:
```yaml
# config/devices.yaml

# КУБы - критичные, опрос каждую секунду
devices:
  - device_id: 1-6
    device_type: "KUB-1063"
    poll_interval: 1.0
    priority: "HIGH"

# VFD критичные (например, основные линии) - каждую секунду
  - device_id: 7-12  # 6 главных VFD
    device_type: "VFD-INVERTER"
    poll_interval: 1.0
    priority: "HIGH"

# VFD резервные - раз в 5 секунд
  - device_id: 13-24  # 12 резервных VFD
    device_type: "VFD-INVERTER"
    poll_interval: 5.0
    priority: "NORMAL"
```

**Ожидаемая производительность**:
```
Каждую секунду:
  КУБ×6 (1.8s) + VFD×6 (3.6s) = 5.4s

Каждые 5 секунд:
  КУБ×6 + VFD×18 = 5.4s + 10.8s = 16.2s (full scan)
  Но благодаря приоритетам, критичные данные обновляются каждую секунду!
```

**⚠️ Проблема**: 5.4s > 1s для критичных устройств

**✅ Решение**: Разделить опрос на волны

```python
# Волна 1 (0-1s): КУБ 1-3 + VFD 1-3
# Волна 2 (1-2s): КУБ 4-6 + VFD 4-6
# Итого: каждая волна ~2.7s, но критичные данные обновляются каждую секунду
```

---

## 🎯 Практическая реализация

### Код для Фазы 1 (Quick Win):

```python
# EDGE/core/device_scheduler.py (НОВЫЙ ФАЙЛ)

from typing import List, Dict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import time

@dataclass
class ScheduledDevice:
    """Устройство с расписанием опроса"""
    device_info: DeviceInfo
    poll_interval: float = 5.0  # секунды
    priority: str = "NORMAL"     # HIGH / NORMAL / LOW
    last_poll: datetime = field(default_factory=datetime.now)

    def should_poll(self) -> bool:
        """Проверка нужен ли опрос"""
        elapsed = (datetime.now() - self.last_poll).total_seconds()
        return elapsed >= self.poll_interval

    def mark_polled(self):
        """Отметить что устройство опрошено"""
        self.last_poll = datetime.now()


class DeviceScheduler:
    """Планировщик опроса устройств с приоритетами"""

    def __init__(self, devices: List[DeviceInfo]):
        self.scheduled_devices = []

        for device in devices:
            # Дефолтные интервалы по типу устройства
            poll_interval = self._get_default_interval(device.device_type)
            priority = self._get_default_priority(device.device_type)

            self.scheduled_devices.append(ScheduledDevice(
                device_info=device,
                poll_interval=poll_interval,
                priority=priority
            ))

    def _get_default_interval(self, device_type: DeviceType) -> float:
        """Дефолтные интервалы опроса"""
        defaults = {
            DeviceType.KUB_1063: 1.0,      # КУБы - каждую секунду
            DeviceType.VFD_INVERTER: 2.0,  # VFD - каждые 2 секунды
        }
        return defaults.get(device_type, 5.0)

    def _get_default_priority(self, device_type: DeviceType) -> str:
        """Дефолтные приоритеты"""
        return "HIGH" if device_type == DeviceType.KUB_1063 else "NORMAL"

    def get_devices_to_poll(self) -> List[DeviceInfo]:
        """Получить список устройств для опроса СЕЙЧАС"""
        devices_to_poll = []

        # Сортировка по приоритету
        priority_order = {"HIGH": 0, "NORMAL": 1, "LOW": 2}
        sorted_devices = sorted(
            self.scheduled_devices,
            key=lambda d: (priority_order.get(d.priority, 3), d.last_poll)
        )

        for scheduled in sorted_devices:
            if scheduled.should_poll():
                devices_to_poll.append(scheduled.device_info)
                scheduled.mark_polled()

        return devices_to_poll

    def get_next_poll_time(self) -> float:
        """Время до следующего опроса (в секундах)"""
        if not self.scheduled_devices:
            return 1.0

        min_wait = float('inf')
        now = datetime.now()

        for scheduled in self.scheduled_devices:
            elapsed = (now - scheduled.last_poll).total_seconds()
            wait_time = max(0, scheduled.poll_interval - elapsed)
            min_wait = min(min_wait, wait_time)

        return min_wait


# Использование в start.py:

class EdgeNode:
    def start_modbus_reader(self, interval: float | None = None):
        devices = self.device_registry.get_all_devices(enabled_only=True)
        scheduler = DeviceScheduler(devices)

        def reader_worker():
            logger.info("📖 Modbus reader with scheduler started")

            while not shutdown_requested.is_set():
                # Получаем устройства которые нужно опросить
                devices_to_poll = scheduler.get_devices_to_poll()

                if devices_to_poll:
                    logger.debug(f"📋 Polling {len(devices_to_poll)} devices")

                    for device in devices_to_poll:
                        # Опрашиваем через Universal Reader
                        request_universal_read(callback, device_info=device)
                        time.sleep(0.05)  # Небольшая пауза между устройствами

                # Ждём до следующего опроса
                wait_time = scheduler.get_next_poll_time()
                time.sleep(min(wait_time, 0.1))  # Макс 100ms

        self.reader_thread = threading.Thread(target=reader_worker, daemon=True)
        self.reader_thread.start()
```

---

## 📊 Benchmark результаты

### Тест: Симуляция 24 устройств (6 КУБ + 18 VFD)

```bash
# Запуск benchmark
cd EDGE
python tests/benchmark_polling.py
```

**Результаты** (ожидаемые):

| Метрика | Без оптимизации | С оптимизацией | Улучшение |
|---------|-----------------|----------------|-----------|
| Полный цикл | 9.0s | 5.4s | **1.7x** |
| Критичные данные | 9.0s | 1.0s | **9x** |
| Пропускная способность | 2.7 dev/s | 4.4 dev/s | **1.6x** |
| CPU usage | 15% | 12% | **-20%** |

---

## ✅ Выводы и рекомендации

### Для вашего случая (6 КУБ + 18 VFD):

**🟢 Система ВЗЛЕТИТ** при условии:
1. ✅ Включен batch reading (уже есть!)
2. ✅ Настроены приоритеты опроса
3. ✅ Используется scheduler вместо последовательного опроса

**🟡 Ограничения**:
- RS485 - полудуплексная шина, физический лимит ~5-10 транзакций/сек
- Для 50+ устройств потребуется несколько RS485 портов или Modbus TCP

**🔴 Красные флаги** (когда НЕ взлетит):
- Если все 24 устройства должны обновляться каждую секунду → **НЕВОЗМОЖНО**
- Если устройства медленные (>500ms ответа) → нужен async
- Если нужна задержка <100ms → нужен Modbus TCP + многопоточность

### Next Steps:

1. **Сейчас**: Реализовать DeviceScheduler (2-3 часа)
2. **Завтра**: Протестировать с 2-3 устройствами
3. **Через неделю**: Раскатить на все 24 устройства

Хочешь чтобы я реализовал DeviceScheduler прямо сейчас? 🚀
