# Инструкция для ModScan

> **Примечание:** Все сервисные скрипты управления теперь находятся в папке `tools/` (например, запуск — `python tools/start_all_services.py`).

## 🔧 Настройки подключения

### Connection Settings:
- **Protocol**: Modbus TCP
- **IP Address**: `tcp.cloudpub.ru`
- **Port**: `32173`
- **Unit ID**: `1`
- **Timeout**: 5000 ms

### Register Settings:
- **Function**: Read Holding Registers (03)
- **Starting Address**: `0` ⚠️ **ВАЖНО: не 40001!**
- **Quantity**: `3`

## 📊 Ожидаемые данные

| Регистр | Адрес | Значение | Описание |
|---------|-------|----------|----------|
| 0 | 0 | 265 | Температура (26.5°C) |
| 1 | 1 | 0 | Влажность (0%) |
| 2 | 2 | 0 | CO2 (0 ppm) |

## 🔍 Диагностика

### Если видите 0x0000:

1. **Проверьте адрес**: должен быть `0`, а не `40001`
2. **Проверьте порт**: должен быть `32173`
3. **Проверьте Unit ID**: должен быть `1`
4. **Проверьте Function**: должен быть `03` (Read Holding Registers)

### Тестовые запросы:

**Правильный запрос:**
```
Function: 03 (Read Holding Registers)
Starting Address: 0
Quantity: 3
```

**Неправильный запрос:**
```
Function: 03 (Read Holding Registers)
Starting Address: 40001  ❌
Quantity: 3
```

## 🧪 Альтернативные тесты

### Через telnet:
```bash
telnet tcp.cloudpub.ru 32173
```

### Через curl:
```bash
echo -ne '\x00\x01\x00\x00\x00\x06\x01\x03\x00\x00\x00\x03' | nc tcp.cloudpub.ru 32173
```

## 📈 Интерпретация данных

- **Температура**: значение / 10 = градусы Цельсия
- **Влажность**: значение / 10 = проценты
- **CO2**: значение = ppm 