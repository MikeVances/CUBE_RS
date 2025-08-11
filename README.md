# CUBE_RS — Система мониторинга КУБ-1063

Система для чтения данных с контроллера КУБ-1063 и их визуализации через веб-интерфейс.

## 🚀 Быстрый старт

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск всех сервисов
python tools/start_all_services.py
```

## 📊 Доступные сервисы

- **📊 Streamlit Dashboard** — веб-интерфейс для визуализации данных
- **🧲 Gateway (Modbus TCP)** — Modbus TCP сервер (порт 5021)
- **🧲 TCP Duplicator** — JSON over TCP (порт 5022)
- **🛰️ WebSocket Server** — real-time данные (порт 8765)
- **🤖 Telegram Bot** — бот для получения данных
- **📡 MQTT Publisher** — публикация данных через MQTT

## 🛠️ Управление системой

### Запуск всех сервисов
```bash
python tools/start_all_services.py
```

### Остановка всех сервисов
```bash
python tools/stop_all_services.py
```

### Проверка статуса
```bash
python tools/check_services_status.py
```

### Экстренная остановка
```bash
python tools/kill_all.py
```

## 📁 Структура проекта

```
CUBE_RS/
├── main.py                  # Главный запускатель системы (Dashboard)
├── config.py                # Конфигурация
├── requirements.txt         # Зависимости Python
├── tools/                   # Скрипты управления и мониторинга
│   ├── start_all_services.py
│   ├── stop_all_services.py
│   ├── check_services_status.py
│   └── kill_all.py
├── modbus/                  # Модуль чтения данных
├── dashboard/               # Streamlit дашборд
├── publish/                 # Модули публикации данных
├── README_SERVICES.md       # Документация по сервисам
├── README_LAUNCH.md         # Инструкция по запуску
├── ModScan_Instructions.md  # Инструкция по ModScan
└── ...
```

## 📄 Документация

- [README_SERVICES.md](README_SERVICES.md) — управление сервисами
- [README_LAUNCH.md](README_LAUNCH.md) — инструкция по запуску
- [ModScan_Instructions.md](ModScan_Instructions.md) — инструкция по ModScan
- [КУБ-1063_modbus registers.md](КУБ-1063_modbus registers.md) — документация по Modbus-регистрам

## 🏁 Текущее состояние

✅ **Работает:**
- Все сервисы (Dashboard, Gateway, TCP Duplicator, WebSocket, Telegram Bot, MQTT)
- Нет конфликтов доступа к RS485
- Данные доступны локально и через интернет

## ⚠️ Важные замечания

1. **Перед запуском** убедитесь, что устройство КУБ-1063 подключено к `/dev/tty.usbserial-2110`
2. **Для остановки** используйте `python tools/stop_all_services.py` или `python tools/kill_all.py`
3. **Для диагностики** используйте `python tools/check_services_status.py`
4. **Логи** смотрите в терминале или используйте перенаправление в файл 