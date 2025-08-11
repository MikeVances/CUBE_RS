# 🚀 Инструкция по запуску CUBE_RS

## 📋 Доступные сервисы

### 1. 📊 Streamlit Dashboard (основной)
```bash
python tools/start_all_services.py
```
- **URL:** http://localhost:8501
- **Функции:** Веб-интерфейс для мониторинга КУБ-1063
- **Статус:** ✅ Работает стабильно

### 2. 🤖 Telegram Bot (отдельно)
```bash
python tools/start_all_services.py  # Запустит все сервисы, включая Telegram Bot
```
или вручную:
```bash
python publish/telegram_bot.py
```
- **Функции:** Мониторинг через Telegram
- **Статус:** ✅ Работает
- **Команды:** `/start`, `/status`, `/stats`, `/help`

## 🛠️ Управление сервисами

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

## 📁 Структура файлов

```
CUBE_RS/
├── main.py                    # Основной запускатель (Dashboard)
├── tools/                     # Скрипты управления и мониторинга
│   ├── start_all_services.py
│   ├── stop_all_services.py
│   ├── check_services_status.py
│   └── kill_all.py
├── publish/
│   └── telegram_bot.py        # Telegram Bot
├── dashboard/
│   └── app.py                 # Streamlit приложение
├── config.py                  # Конфигурация
└── ...
```

## 🎯 Рекомендации

1. **Для мониторинга:** используйте `python tools/start_all_services.py` (Dashboard и все сервисы)
2. **Для Telegram:** сервис запускается вместе с остальными или отдельно через `python publish/telegram_bot.py`
3. **Для диагностики:** используйте `python tools/check_services_status.py`

## ⚠️ Известные проблемы

- Telegram Bot: Event loop ошибки (не критичны)
- Конфликты портов: используйте `tools/stop_all_services.py` или `tools/kill_all.py` для полной остановки

## 🆘 Поддержка

При проблемах:
1. Проверьте логи в терминале
2. Убедитесь в подключении устройства
3. Перезапустите сервисы через `tools/stop_all_services.py` и `tools/start_all_services.py` 