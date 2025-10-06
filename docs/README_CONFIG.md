# 🔧 Централизованная конфигурация КУБ-1063

## 📋 Обзор системы

Система КУБ-1063 теперь использует **централизованный конфиг-менеджер** для управления всеми настройками. Это решает проблемы:

- ❌ **Разбросанные настройки** по разным файлам
- ❌ **Хардкод портов** в коде  
- ❌ **Конфликты конфигураций**
- ❌ **Сложность настройки** новых окружений

## 🏗️ Архитектура конфигурации

```
config/
├── app_config.yaml          # ✅ Основные настройки системы
├── bot_secrets.json         # 🔐 Токены и секреты (НЕ в git!)
└── logs/                    # 📝 Централизованные логи

core/
└── config_manager.py        # 🎯 Единая точка конфигурации
```

## ⚙️ Файл конфигурации

### `config/app_config.yaml`

```yaml
# Основные настройки системы
system:
  environment: development    # development, production, testing  
  log_level: INFO
  startup_timeout: 60

# RS485 подключение к КУБ-1063
rs485:
  port: /dev/tty.usbserial-21230
  baudrate: 9600
  timeout: 2.0
  slave_id: 1

# Modbus TCP сервер  
modbus_tcp:
  port: 5023                 # 🎯 Единственный порт для простоты!
  timeout: 3.0

# Включение/отключение сервисов  
services:
  gateway_enabled: true      # 🎛️ Простое управление сервисами
  dashboard_enabled: true
  telegram_enabled: true
  websocket_enabled: false
  
  dashboard_port: 8501
  websocket_port: 8765

# База данных
database:
  file: kub_data.db
  commands_db: kub_commands.db
  timeout: 5

# Все Modbus регистры КУБ-1063
modbus_registers:
  software_version: "0x0301"
  pressure: "0x0083"
  humidity: "0x0084"
  # ... все остальные
```

### `config/bot_secrets.json` 

```json
{
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN",
    "admin_users": [123456789]
  }
}
```

## 🚀 Использование ConfigManager

### В коде Python

```python
from core.config_manager import get_config

# Получаем глобальный конфиг
config = get_config()

# Читаем настройки
port = config.modbus_tcp.port              # 5023
rs485_port = config.rs485.port             # /dev/tty.usbserial-21230  
token = config.telegram.token              # Bot token
admins = config.telegram.admin_users       # [123456789]

# Проверяем включен ли сервис
if config.services.gateway_enabled:
    start_gateway()
```

### Shortcuts для частых настроек

```python
from core.config_manager import (
    get_gateway_port,
    get_telegram_token, 
    get_rs485_port
)

port = get_gateway_port()       # 5023
token = get_telegram_token()    # Bot token
```

## 🔄 Переменные окружения

ConfigManager автоматически считывает переменные окружения:

```bash
export TELEGRAM_BOT_TOKEN="your_token"
export RS485_PORT="/dev/ttyUSB0"  
export ENVIRONMENT="production"
export LOG_LEVEL="WARNING"
```

## 📊 Уровни приоритета

1. **Переменные окружения** (высший)
2. **config/app_config.yaml** 
3. **config/bot_secrets.json**
4. **Значения по умолчанию** (низший)

## 🛠️ Запуск системы

### Все сервисы сразу

```bash
python tools/start_all_services.py
```

Автоматически запустит только **включенные в конфиге** сервисы:

- ✅ Gateway (если `gateway_enabled: true`)
- ✅ Dashboard (если `dashboard_enabled: true`) 
- ✅ Telegram Bot (если `telegram_enabled: true`)
- ❌ WebSocket (если `websocket_enabled: false`)

### Отдельные сервисы

```bash
# Gateway с автонастройкой портов
python -m modbus.gateway

# Telegram Bot с централизованной конфигурацией  
python telegram_bot/async_bot_main.py

# Dashboard на настроенном порту
streamlit run dashboard/app.py --server.port 8501
```

## ✨ Преимущества новой системы

### 🎯 Централизация
- **Одно место** для всех настроек
- **Нет хардкода** в коде  
- **Единый формат** конфигурации

### 🔧 Простота настройки
- Меняете порт в **одном месте** → работает везде
- **Включил/выключил сервис** одной строкой
- **Environment-based** конфигурации

### 🚀 Масштабируемость  
- Легко добавлять **новые настройки**
- **Валидация** конфигурации при запуске
- **Hot reload** без перезапуска системы

### 🛡️ Безопасность
- **Секреты отдельно** от основного конфига
- **Переменные окружения** для production
- **Не попадают в git** (bot_secrets.json)

## 🔍 Отладка и логи

### Структура логов

```
logs/
├── gateway1.log          # Modbus TCP Gateway
├── telegram.log          # Telegram Bot  
├── dashboard.log         # Streamlit Dashboard
├── start_services.log    # Менеджер сервисов
└── system.log            # Общие системные события
```

### Проверка конфигурации

```bash
# Тест ConfigManager
python core/config_manager.py

# Вывод: 
🔧 Тестирование ConfigManager...
📡 RS485 порт: /dev/tty.usbserial-21230  
🌐 Gateway 1 порт: 5023
💾 База данных: kub_data.db
🤖 Telegram админы: 1
✅ ConfigManager протестирован успешно!
```

## 🚨 Решение проблем

### "Порт уже занят"
```bash
# Проверяем какие порты настроены
python -c "from core.config_manager import get_config; c=get_config(); print(f'Порты: {c.modbus_tcp.port}, {c.services.dashboard_port}')"

# Меняем в config/app_config.yaml:
modbus_tcp:
  port: 5024  # Новый свободный порт
```

### "Не найден токен бота"
```bash
# Создаём config/bot_secrets.json:
echo '{"telegram": {"bot_token": "YOUR_TOKEN", "admin_users": [YOUR_ID]}}' > config/bot_secrets.json

# Или через переменную окружения:
export TELEGRAM_BOT_TOKEN="your_token"
```

### "Ошибка импорта ConfigManager"
```bash
pip install PyYAML>=6.0.1
```

## 🎉 Миграция со старой системы

Старые конфигурационные файлы **удалены**:
- ❌ `config.json` 
- ❌ `telegram_bot/bot_config.json`
- ❌ Хардкод портов в коде

Все настройки теперь в `config/app_config.yaml` + `config/bot_secrets.json`.

---

**Система готова к масштабированию и простому управлению! 🚀**
