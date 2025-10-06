# CUBE_RS EDGE - Промышленный IoT Gateway

EDGE компонент системы CUBE_RS для мониторинга и управления промышленным оборудованием КУБ-1063 и КУБ-1112 на фермах.

## 🏗️ Архитектура

EDGE - это автономный промышленный шлюз, который:
- Собирает данные с устройств КУБ через Modbus RTU/TCP
- Публикует данные в реальном времени (WebSocket, MQTT)
- Предоставляет Telegram бота для удаленного управления
- Автоматически регистрируется на SERVER через EDGE Ping Service
- Обеспечивает веб-интерфейс мониторинга и health checks

## 📋 Компоненты системы

### Основные сервисы:
- **Device Registry** - управление множественными устройствами
- **WebSocket Server** - real-time данные (порт 8000)
- **MQTT Publisher** - публикация в MQTT брокер
- **Telegram Bot** - удаленное управление и мониторинг
- **EDGE Ping Service** - автоматическая регистрация на SERVER
- **Health API** - мониторинг состояния системы (порт 8090)
- **Streamlit Dashboard** - веб-интерфейс (порт 8501)

### Система мониторинга:
- **Error Handler** - централизованная обработка ошибок с Circuit Breaker
- **Health Checker** - мониторинг компонентов и системных ресурсов
- **Security Manager** - шифрование конфигурации и секретов
- **MITM Protection** - защита от атак типа человек-в-середине

## 🚀 Быстрый запуск

### Полный стек (все сервисы):
```bash
python start.py
```

### Выборочный запуск:
```bash
# Без Telegram бота
python start.py --disable-telegram

# Только WebSocket и Health API
python start.py --disable-telegram --disable-mqtt --disable-edge-ping

# Показать все опции
python start.py --help
```

### Отдельные компоненты:
```bash
# Веб-интерфейс мониторинга
python start_dashboard.py

# TypedModbusGateway (требует портирования)
python start_typed_gateway.py
```

## ⚙️ Управление сервисами

В отличие от предыдущих версий, где сервисы включались через `config/app_config.yaml`, теперь используются **командные параметры**:

### Доступные опции запуска:

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `--disable-telegram` | Отключить Telegram бота | Включен |
| `--disable-websocket` | Отключить WebSocket сервер | Включен |
| `--disable-mqtt` | Отключить MQTT Publisher | Включен |
| `--disable-edge-ping` | Отключить EDGE Ping Service | Включен |
| `--disable-health-api` | Отключить Health API | Включен |
| `--log-level` | Уровень логирования | INFO |

### Примеры конфигурации:

```bash
# Минимальная конфигурация (только Device Registry)
python start.py --disable-telegram --disable-websocket --disable-mqtt --disable-edge-ping --disable-health-api

# Конфигурация для разработки (без внешних подключений)
python start.py --disable-mqtt --disable-edge-ping

# Пуск всего узла (gateway + runtime)
python start_edge.py --offline --log-level INFO --rs485-port /dev/tty.usbserial-2130

# При необходимости без Telegram бота
python start_edge.py --offline --disable-telegram --rs485-port /dev/tty.usbserial-2130
```

### Offline режим и защита локальных API

- `EDGE_OFFLINE_MODE=true` — включить автономный режим без обращения к центральному серверу (аналогично флагу `--offline`).
- `EDGE_CORS_ALLOWED_ORIGINS="http://localhost,http://edge.local"` — разрешённые origin'ы для удалённого дашборда/REST API.
- `EDGE_HEALTH_TOKEN=секрет` и `EDGE_REQUIRE_HEALTH_TOKEN=true` — включить проверку токена на эндпоинтах Health/metrics, передаётся в заголовке `X-EDGE-Health-Token` или query-параметре `token`.

## 🌐 Сетевые эндпоинты

После запуска доступны следующие эндпоинты:

### Health API (порт 8090):
- `GET /health` - общее состояние системы
- `GET /health/{component}` - состояние конкретного компонента
- `GET /metrics` - системные метрики (CPU, RAM, диск)
- `GET /errors` - статистика ошибок

### WebSocket Server (порт 8000):
- `ws://localhost:8000` - real-time данные устройств

### Web Dashboard (порт 8501):
- `http://localhost:8501` - веб-интерфейс мониторинга

### MQTT Publisher:
- Настраивается через переменные окружения:
  - `MQTT_BROKER_HOST` - хост брокера (по умолчанию: localhost)
  - `MQTT_BROKER_PORT` - порт брокера (по умолчанию: 1883)
  - `MQTT_TOPIC_PREFIX` - префикс топиков (по умолчанию: cube_rs)

## 🔐 Конфигурация безопасности

### Telegram Bot секреты:

```bash
# Показать замаскированные секреты
python tools/telegram_secrets_cli.py show

# Установить токен бота
python tools/telegram_secrets_cli.py set-token 123456:ABC-DEF...

# Установить админов (через запятую)
python tools/telegram_secrets_cli.py set-admins 111111111,222222222

# Добавить/удалить админа
python tools/telegram_secrets_cli.py add-admin 333333333
python tools/telegram_secrets_cli.py remove-admin 222222222
```

### EDGE Ping Service конфигурация:

```bash
# Через переменные окружения
export EDGE_PING_SERVERS="https://server1.com/api/edge/ping,https://server2.com/api/edge/ping"

# Или через зашифрованный файл config/secrets/edge_ping.enc
python tools/edge_ping_secrets_cli.py set-servers https://server.com/api/edge/ping
python tools/edge_ping_secrets_cli.py set-auth-token your_auth_token
```

## 📊 Конфигурация устройств

Устройства настраиваются через `config/app_config.yaml`:

```yaml
devices:
  - device_id: "КУБ-1063-001" 
    device_type: "КУБ-1063"
    connection:
      type: "modbus_rtu"
      port: "/dev/ttyUSB0"
      baudrate: 9600
      slave_id: 1
    variables:
      - name: "temp_inside"
        address: 0x00D5
        type: "temperature"
        unit: "°C"

  - device_id: "КУБ-1112-001"
    device_type: "КУБ-1112" 
    connection:
      type: "modbus_tcp"
      host: "192.168.1.100"
      port: 502
      slave_id: 2
```

## 📁 Структура проекта

```
EDGE/
├── start.py                    # 🚀 Главный launcher
├── start_dashboard.py          # 📊 Web Dashboard launcher  
├── start_typed_gateway.py      # 🔌 Gateway launcher (TODO)
├── config/
│   ├── app_config.yaml         # ⚙️ Конфигурация устройств
│   └── secrets/                # 🔐 Зашифрованные секреты
├── core/                       # 🏗️ Основные компоненты
│   ├── device_registry.py      # 📡 Управление устройствами
│   ├── edge_authentication.py  # 🔒 Аутентификация с SERVER
│   ├── edge_ping_service.py    # 📡 Автоматическая регистрация
│   ├── error_handler.py        # ❌ Обработка ошибок
│   ├── health_checker.py       # 🏥 Мониторинг здоровья
│   ├── health_api.py           # 🌐 Health API сервер
│   └── publishing/             # 📤 Real-time публикация
│       ├── websocket_server.py
│       └── mqtt.py
├── web_dashboard/              # 📊 Streamlit интерфейс
│   └── app.py
└── requirements.txt            # 📦 Зависимости
```

## 🔧 Разработка и отладка

### Режим разработки:
```bash
# Запуск с подробными логами
python start.py --log-level DEBUG

# Запуск только Dashboard для разработки UI
python start_dashboard.py
```

### Мониторинг системы:
```bash
# Проверить здоровье системы
curl http://localhost:8090/health

# Системные метрики
curl http://localhost:8090/metrics

# Статистика ошибок
curl http://localhost:8090/errors
```

## 🗄️ База данных

EDGE использует SQLite для хранения данных:
- `data/kub_data.db` - данные устройств
- `data/kub_commands.db` - команды и пользователи Telegram

База данных создается автоматически при первом запуске.

## 📝 Логирование

Логи сохраняются в:
- `logs/` - общие логи системы
- `config/logs/security.log` - безопасность
- `config/logs/telegram.log` - Telegram бот

## 🚨 Мониторинг и alerting

Health Checker автоматически отслеживает:
- 🖥️ **Система**: CPU, RAM, диск, uptime
- 🗄️ **База данных**: доступность, размер, время ответа
- 📡 **Modbus**: активные подключения, статистика запросов
- 🤖 **Telegram**: процесс бота, конфигурация токена
- 🌐 **API Gateway**: прослушиваемые порты
- 🔌 **Сеть**: активные соединения, интерфейсы

Circuit Breaker автоматически отключает неисправные компоненты для предотвращения каскадных сбоев.

## ⚠️ Troubleshooting

### Проблема: "Device Registry недоступен"
```bash
# Проверить конфигурацию устройств
cat config/app_config.yaml

# Проверить подключения к устройствам
ls -la /dev/ttyUSB*
```

### Проблема: "Telegram bot недоступен"  
```bash
# Проверить токен бота
python tools/telegram_secrets_cli.py show

# Проверить переменные окружения
echo $TELEGRAM_BOT_TOKEN
echo $TELEGRAM_ENV_OVERRIDE
```

### Проблема: "Health API не отвечает"
```bash
# Проверить что порт 8090 свободен
netstat -tlnp | grep 8090

# Проверить логи
tail -f logs/edge.log
```

## 🔮 Roadmap

- [ ] Портирование TypedModbusGateway в Device Registry архитектуру
- [ ] OPC UA поддержка для промышленных протоколов
- [ ] Grafana интеграция для профессионального мониторинга
- [ ] Docker контейнеризация для простого развертывания
- [ ] Kubernetes поддержка для масштабирования

## 📄 Лицензия

CUBE_RS EDGE - закрытый программный продукт для промышленного использования.
