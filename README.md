# 🚀 CUBE RS - Distributed Industrial Monitoring System

Распределенная система мониторинга промышленных КУБ устройств с поддержкой P2P туннелей, мобильных приложений и централизованного управления.

## 🏗️ Архитектура системы

```
📱 Mobile/Web APP          🌐 SERVER          📡 EDGE Device
       │                      │                    │
   ┌───▼───┐              ┌───▼───┐         ┌───▼───┐
   │ User  │◀─────────────│ Auth  │◀────────│ API   │
   │ Auth  │   JWT Auth   │ Mgmt  │  Keys   │ Auth  │
   └───┬───┘              └───┬───┘         └───┬───┘
       │                      │                 │
   ┌───▼───┐              ┌───▼───┐         ┌───▼───┐
   │ Farm  │◀─────────────│Device │◀────────│ Multi │
   │ Mgmt  │   REST API   │ Mgmt  │Heartbeat│Device │
   └───┬───┘              └───┬───┘         └───┬───┘
       │                      │                 │
   ┌───▼───┐              ┌───▼───┐         ┌───▼───┐
   │ P2P   │◀─────────────│Tunnel │◀────────│ KUB   │
   │ UI    │   WebRTC     │Broker │  Data   │1063/12│
   └───────┘              └───────┘         └───────┘
```

## 📦 Проекты

### 📡 EDGE - Устройства мониторинга
**Расположение:** `/EDGE/`

Локальные устройства для мониторинга КУБ-1063, КУБ-1112 и других промышленных контроллеров.

**Возможности:**
- ✅ Multi-device architecture с Variable System
- ✅ Modbus RTU/TCP коммуникация  
- ✅ Гибкая система переменных
- ✅ Authentication Client с API ключами
- ✅ P2P Tunnel Client
- ✅ Heartbeat Service для мониторинга

**Технологии:** Python, Modbus, SQLite, Docker

### 🌐 SERVER - Центральный сервер
**Расположение:** `/SERVER/`

Центральный сервер управления, аутентификации и координации P2P туннелей.

**Возможности:**
- ✅ JWT & API Key аутентификация
- ✅ Role-based Access Control
- ✅ Device Registry & Management
- ✅ P2P Tunnel Broker
- ✅ Admin CLI для управления
- ✅ Docker deployment готов

**Технологии:** Python, Flask, JWT, SQLite, Docker, Nginx

### 📱 APP - Мобильное приложение
**Расположение:** `/APP/`

Backend API для мобильных приложений и веб-интерфейса пользователей.

**Возможности:**
- ✅ REST API для мобильных приложений
- ✅ JWT Authentication интеграция
- ✅ CORS Support для кроссплатформенности
- ✅ Farm & Device Management API
- ✅ P2P Tunnel Interface
- ✅ Health Checks & Monitoring

**Технологии:** Python, Flask, CORS, Docker

### 🔧 ST_RS - C# Gateway (отдельный)
**Расположение:** `/ST_RS/`

Отдельный проект на C# с примером архитектуры Variable System.

## 🚀 Быстрый старт

### 1. Запуск SERVER (центральный сервер)

```bash
cd SERVER

# Создание администратора
python3 demo_auth_setup.py

# Запуск сервера
docker-compose up -d

# Или без Docker
pip3 install -r requirements.txt
python3 tunnel_broker.py
```

### 2. Настройка EDGE устройства

```bash
cd EDGE

# Установка зависимостей
pip3 install -r requirements.txt

# Получение API ключа от SERVER администратора
# python3 ../SERVER/admin_cli.py register-device --owner-id user_xxx --farm-id farm_001

# Настройка переменных окружения
export EDGE_API_KEY="your_api_key"
export EDGE_DEVICE_ID="your_device_id" 
export EDGE_FARM_ID="your_farm_id"
export TUNNEL_BROKER_URL="http://your-server:8080"

# Запуск мониторинга
python3 start.py
```

### 3. Запуск APP (мобильное приложение)

```bash
cd APP

# Установка зависимостей
pip3 install -r requirements.txt

# Настройка подключения к SERVER
export SERVER_URL="http://your-server:8080"
export SECRET_KEY="your-app-secret"

# Запуск API сервера
python3 main_app.py
```

## 🔐 Система безопасности

### Роли пользователей
- **ADMIN** - полные права управления системой
- **FARM_OWNER** - управление своими фермами и устройствами  
- **VIEWER** - только просмотр данных
- **EDGE_DEVICE** - права устройств для отправки данных

### Аутентификация
- **JWT токены** для APP пользователей (короткий срок жизни)
- **API ключи** для EDGE устройств (долгоживущие)
- **Session cookies** для веб-интерфейса
- **Role-based permissions** для всех операций

## 📊 Мониторируемые устройства

### КУБ-1063 (Вентиляция)
- 🌡️ Температура и влажность
- 💨 Скорость вентиляции  
- 🏭 Уровень CO2
- ⚡ Состояние датчиков

### КУБ-1112 (Отопление)
- 🔥 Уровень пламени
- 🌡️ Температурные датчики
- 🔀 Состояние реле
- ⛽ Газовое оборудование

### Расширяемость
Система поддерживает добавление новых типов устройств через Variable System архитектуру.

## 🌐 P2P Tunnels

Система поддерживает IXON-style P2P туннели для прямого доступа к EDGE устройствам:

1. **APP** запрашивает туннель через **SERVER**
2. **SERVER** координирует WebRTC соединение
3. **EDGE** устройство участвует в P2P сессии
4. Прямой доступ к данным КУБ устройств

## 📖 Документация

- **[EDGE README](EDGE/README.md)** - документация EDGE устройств
- **[SERVER README](SERVER/README.md)** - документация центрального сервера
- **[APP README](APP/README.md)** - документация мобильного приложения
- **[Authentication System](SERVER/AUTH_SYSTEM.md)** - система аутентификации
- **[docs/](docs/)** - дополнительная документация

## 🔄 Разработка

### Структура репозитория
```
CUBE_RS/
├── EDGE/                 # 📡 Устройства мониторинга
│   ├── core/            # Основные модули
│   ├── config/          # Конфигурации
│   ├── docs/            # Документация
│   └── tests/           # Тесты
├── SERVER/              # 🌐 Центральный сервер  
│   ├── auth_system.py   # Система аутентификации
│   ├── tunnel_broker.py # P2P брокер
│   ├── admin_cli.py     # CLI управления
│   └── docker-compose.yml
├── APP/                 # 📱 Мобильное приложение
│   ├── backend/         # Flask API
│   ├── frontend/        # Веб-интерфейс
│   ├── mobile/          # SDK для мобильных
│   └── docker-compose.yml
├── ST_RS/              # 🔧 C# проект (отдельный)
├── docs/               # 📚 Общая документация
└── _archive/           # 📦 Устаревшие файлы
```

### Независимая разработка проектов
Каждый проект (EDGE, SERVER, APP) может разрабатываться независимо:
- Собственные зависимости (`requirements.txt`)
- Отдельные Docker контейнеры
- Независимые тесты и CI/CD
- Возможность переноса в отдельные репозитории

## 🎯 Результат

**Полная распределенная система промышленного мониторинга с поддержкой мобильных приложений, P2P туннелей и централизованного управления!** 🚀
