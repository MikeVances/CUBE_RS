# 🏗️ АРХИТЕКТУРНАЯ РЕСТРУКТУРИЗАЦИЯ CUBE_RS

## 📋 Текущие проблемы

### 🚨 Критические проблемы
1. **Разбросанная архитектура** - компоненты смешаны по папкам
2. **Тестовые ключи в продакшене** - API ключи-заглушки в коде
3. **Широкие Exception блоки** - потеря точности обработки ошибок
4. **Дублирование кода** - похожие функции в разных модулях

## 🎯 Предлагаемая структура

```
CUBE_RS/
├── apps/                           # 🖥️ ПРИЛОЖЕНИЯ
│   ├── server/                     # 🌐 SERVER APPS
│   │   ├── web_dashboard/          # Flask веб-приложение
│   │   ├── api_gateway/            # API Gateway
│   │   ├── tunnel_broker/          # P2P туннельный брокер
│   │   └── telegram_service/       # Telegram бот сервис
│   ├── client/                     # 📱 CLIENT APPS  
│   │   ├── mobile_app/             # PWA мобильное приложение
│   │   ├── farm_client/            # Клиент фермы
│   │   └── discovery_client/       # Клиент обнаружения
│   └── gateway/                    # 🔌 GATEWAY APPS
│       ├── modbus_gateway/         # Modbus TCP Gateway
│       ├── protocol_gateway/       # Протокольный шлюз
│       └── data_gateway/           # Шлюз данных
├── core/                           # ⚙️ ЯДРО СИСТЕМЫ
│   ├── config/                     # Управление конфигурацией
│   ├── security/                   # Система безопасности
│   ├── database/                   # Базы данных и ORM
│   ├── messaging/                  # Система сообщений
│   ├── monitoring/                 # Мониторинг и логирование
│   └── utils/                      # Утилиты
├── services/                       # 🛠️ БИЗНЕС СЕРВИСЫ
│   ├── device_management/          # Управление устройствами
│   ├── data_processing/            # Обработка данных
│   ├── user_management/            # Управление пользователями
│   ├── notification/               # Система уведомлений
│   └── analytics/                  # Аналитика
├── infrastructure/                 # 🚀 ИНФРАСТРУКТУРА
│   ├── docker/                     # Docker контейнеры
│   ├── deployment/                 # Скрипты развёртывания
│   ├── monitoring/                 # Мониторинг инфраструктуры
│   └── backup/                     # Резервное копирование
├── tests/                          # 🧪 ТЕСТЫ
│   ├── unit/                       # Модульные тесты
│   ├── integration/                # Интеграционные тесты
│   ├── e2e/                        # End-to-end тесты
│   └── performance/                # Тесты производительности
├── docs/                           # 📚 ДОКУМЕНТАЦИЯ
└── tools/                          # 🔧 ИНСТРУМЕНТЫ РАЗРАБОТКИ
```

## 🚀 План миграции

### Phase 1: Реорганизация структуры
1. Создание новой структуры папок
2. Перемещение файлов по новым директориям
3. Обновление импортов

### Phase 2: Рефакторинг компонентов
1. Выделение общих интерфейсов
2. Создание базовых классов
3. Унификация обработки ошибок

### Phase 3: Безопасность и тестирование
1. Замена тестовых ключей на конфигурацию
2. Улучшение обработки исключений
3. Добавление тестов

## 🔧 Детали реструктуризации

### SERVER APPS
- `web_dashboard/` ← `web_app/`
- `api_gateway/` ← `web_app/api_gateway.py`
- `tunnel_broker/` ← `tunnel_system/tunnel_broker.py`
- `telegram_service/` ← `telegram_bot/`

### CLIENT APPS
- `mobile_app/` ← `tunnel_system/mobile_app.py`
- `farm_client/` ← `tunnel_system/*_farm_client.py`
- `discovery_client/` ← `tunnel_system/tailscale_discovery_service.py`

### GATEWAY APPS
- `modbus_gateway/` ← `modbus/gateway.py`
- `protocol_gateway/` ← новый компонент
- `data_gateway/` ← `publish/`

### CORE MODULES
- `config/` ← `core/config_manager.py` + `config/`
- `security/` ← `core/security_manager.py`
- `database/` ← `*.db` + ORM слой
- `messaging/` ← `publish/websocket_server.py`

## ⚡ Преимущества новой структуры

1. **Чёткое разделение ответственности**
2. **Упрощение навигации по коду**
3. **Лучшая масштабируемость**
4. **Упрощение тестирования**
5. **Стандартизированная архитектура**

## 🎯 Следующие шаги

1. Создать новую структуру
2. Переместить файлы
3. Обновить импорты
4. Запустить тесты
5. Обновить документацию