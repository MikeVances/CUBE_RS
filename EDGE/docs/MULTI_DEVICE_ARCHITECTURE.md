# Multi-Device Architecture для EDGE

## Проблема
Система сейчас жёстко привязана к КУБ-1063. Для поддержки КУБ-1112 и других типов устройств нужна гибкая архитектура.

## Решение: Device Registry + Device Adapters

### 1. Device Registry
```yaml
# config/devices.yaml
devices:
  - device_id: 1
    device_type: "KUB-1063"
    slave_id: 1
    name: "Корпус 1 - Вентиляция"
    enabled: true
    
  - device_id: 2  
    device_type: "KUB-1112"
    slave_id: 2
    name: "Корпус 1 - Обогрев"
    enabled: true
```

### 2. Device Adapters Pattern
```python
# core/device_adapters/base.py
class DeviceAdapter:
    def get_register_map(self) -> Dict[str, int]
    def parse_register(self, register: int, value: int) -> Any
    def format_for_display(self, data: Dict) -> str
    def get_critical_alarms(self, data: Dict) -> List[str]

# core/device_adapters/kub1063.py  
class KUB1063Adapter(DeviceAdapter):
    REGISTER_MAP = {
        "pressure": 0x0083,
        "humidity": 0x0084,
        # ... существующая карта
    }

# core/device_adapters/kub1112.py
class KUB1112Adapter(DeviceAdapter):
    REGISTER_MAP = {
        "software_version": 0x0301,
        "flame_level": 0x0400,
        "flame_present": 0x0401,
        "temperature": 0x0405,
        "relay_state": 0x0407,
        # ...
    }
```

### 3. Universal Reader/Writer
```python
# modbus/universal_reader.py
class UniversalModbusReader:
    def __init__(self):
        self.adapters = {
            "KUB-1063": KUB1063Adapter(),
            "KUB-1112": KUB1112Adapter(),
        }
    
    async def read_device(self, device_id: int):
        device_info = self.device_registry.get(device_id)
        adapter = self.adapters[device_info.device_type]
        
        for reg_name, reg_addr in adapter.get_register_map().items():
            raw_value = await self.read_register(device_info.slave_id, reg_addr)
            parsed_value = adapter.parse_register(reg_addr, raw_value)
            # Store with device_id
```

### 4. Universal Storage
```sql
-- Заменить latest_data на:
CREATE TABLE device_data (
    device_id INTEGER NOT NULL,
    register_name TEXT NOT NULL,
    raw_value INTEGER,
    parsed_value TEXT,
    value_type TEXT, -- 'temperature', 'percentage', 'boolean', etc
    unit TEXT,       -- '°C', '%', etc
    status TEXT,     -- 'ok', 'error', 'disabled' 
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (device_id, register_name)
);

CREATE INDEX idx_device_updated ON device_data(device_id, updated_at);
```

### 5. Universal Bot Interface  
```python
# telegram_bot/device_handler.py
async def show_device_status(device_id: int):
    device_info = device_registry.get(device_id)
    adapter = adapters[device_info.device_type]
    data = storage.get_device_data(device_id)
    
    formatted_text = adapter.format_for_display(data)
    alarms = adapter.get_critical_alarms(data)
    
    return f"📊 {device_info.name}\n{formatted_text}\n🚨 {alarms}"
```

## Преимущества

1. **Масштабируемость** - легко добавить КУБ-1114, КУБ-1115...
2. **Изоляция** - каждый тип устройства в своём адаптере
3. **Переиспользование** - общий код для Modbus, storage, bot
4. **Совместимость** - KUB1063Adapter повторяет текущую логику

## Этапы миграции

1. Создать базовую архитектуру адаптеров
2. Мигрировать KUB-1063 в KUB1063Adapter  
3. Обновить storage на универсальный
4. Добавить KUB1112Adapter
5. Обновить Bot для выбора устройств