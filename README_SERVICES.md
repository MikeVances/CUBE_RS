# Управление сервисами системы CUBE_RS

## 🚀 Быстрый старт

### Запуск всех сервисов
```bash
python tools/start_all_services.py
```

### Остановка всех сервисов
```bash
python tools/stop_all_services.py
```

### Проверка статуса сервисов
```bash
python tools/check_services_status.py
```

### Экстренная остановка
```bash
python tools/kill_all.py
```

## 📋 Описание сервисов

| Сервис                | Порт/URL              | Описание                | Источник данных |
|-----------------------|----------------------|-------------------------|-----------------|
| **Gateway (Modbus TCP)** | 5021                 | Modbus TCP сервер       | RS485 напрямую  |
| **TCP Duplicator**       | 5022                 | JSON over TCP           | RS485 через окна|
| **Dashboard (Streamlit)**| http://localhost:8501| Веб-интерфейс           | SQLite          |
| **WebSocket Server**     | ws://localhost:8765  | Real-time данные        | SQLite          |
| **Telegram Bot**         | -                    | Telegram интерфейс      | SQLite          |
| **MQTT Publisher**       | -                    | MQTT публикация         | SQLite          |

## 🏗️ Архитектура системы

```
RS485 (/dev/tty.usbserial-2110)
    ↓
┌───────────────────────┐
│ Time Window Manager   │ ← Временные окна доступа (5с окно, 10с cooldown)
└───────────────────────┘
    ↓
┌───────────────┐    ┌───────────────┐
│ Gateway       │    │ TCP Duplicator│
│ (Modbus TCP)  │    │ (JSON over TCP)│
│ Port: 5021    │    │ Port: 5022    │
└───────────────┘    └───────────────┘
    ↓                    ↓
┌───────────────┐    ┌───────────────┐
│ SQLite DB     │    │ Remote Clients│
└───────────────┘    └───────────────┘
    ↓
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│ Dashboard     │ │ WebSocket     │ │ Telegram Bot  │
│ (Streamlit)   │ │ Server        │ │               │
│ Port: 8501    │ │ Port: 8765    │ │               │
└───────────────┘ └───────────────┘ └───────────────┘
    ↓                ↓                ↓
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│ Web Browser   │ │ Web Clients   │ │ Telegram Users│
└───────────────┘ └───────────────┘ └───────────────┘
```

## 🛠️ Управление отдельными сервисами

### Gateway (Modbus TCP)
```bash
python modbus/gateway.py
pkill -f gateway.py
```

### TCP Duplicator
```bash
python modbus/tcp_duplicator.py
pkill -f tcp_duplicator.py
```

### Dashboard (Streamlit)
```bash
streamlit run dashboard/app.py --server.port 8501
pkill -f streamlit
```

### WebSocket Server
```bash
python publish/websocket_server.py
pkill -f websocket_server.py
```

### Telegram Bot
```bash
python publish/telegram_bot.py
pkill -f telegram_bot.py
```

### MQTT Publisher
```bash
python publish/mqtt.py
pkill -f mqtt.py
```

## 🔍 Мониторинг и отладка

### Проверка процессов
```bash
python tools/check_services_status.py
ps aux | grep -E "(gateway|dashboard|websocket|telegram|mqtt|tcp_duplicator)"
```

### Проверка портов
```bash
lsof -i :5021  # Gateway
lsof -i :5022  # TCP Duplicator
lsof -i :8501  # Dashboard
lsof -i :8765  # WebSocket
```

### Логи и отладка
```bash
python modbus/gateway.py 2>&1 | tee gateway.log
python modbus/tcp_duplicator.py 2>&1 | tee duplicator.log
```

## 🛡️ Устранение неполадок

- Проверьте зависимости: `pip install -r requirements.txt`
- Проверьте порты: `lsof -i :<PORT>`
- Проверьте права доступа к RS485: `ls -la /dev/tty.usbserial-2110`
- Используйте `python tools/check_services_status.py` для диагностики
- Перезапустите сервисы через `tools/stop_all_services.py` и `tools/start_all_services.py`

## 📄 Полезные команды

```bash
# Очистка кэша Python
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} +

# Проверка всех процессов
ps aux | grep python

# Мониторинг в реальном времени
watch -n 1 'python tools/check_services_status.py'

# Логи всех сервисов
tail -f *.log
```

## 🎯 Рекомендации

1. **Порядок запуска:** Gateway → TCP Duplicator → остальные сервисы
2. **Мониторинг:** регулярно проверяйте статус сервисов
3. **Логи:** ведите логи для отладки проблем
4. **Резервное копирование:** регулярно сохраняйте конфигурацию
5. **Безопасность:** используйте firewall для защиты портов 