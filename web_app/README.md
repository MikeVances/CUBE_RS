# CUBE_RS Web Application

Современное веб-приложение для мониторинга и управления системами КУБ-1063 с интегрированной Tailscale mesh-сетью и ролевой системой доступа.

## 🏗️ Архитектура

```
CUBE-1063 ──► Modbus Gateway ──► Web Dashboard
    │              │                   │
    │              │                   ├─ Tailscale Management  
    │              │                   ├─ Device Registry
    │              │                   └─ RBAC System
    │              │
    └──► Tailscale ◄──────────────────────┘
         Mesh Network
```

## 🔧 Компоненты

### 1. **Основное приложение** (`app.py`)
- Flask веб-сервер с современным Bootstrap UI
- Интеграция с Modbus Gateway через защищенный API
- Две основные страницы: Dashboard КУБ-1063 и Tailscale Management

### 2. **Tailscale Integration** (`tailscale_integration.py`)  
- Полная интеграция с Tailscale API для управления mesh-сетью
- Мониторинг устройств, создание ключей авторизации
- Проверка доступности API и статуса подключения

### 3. **Device Registry** (`device_registry.py`)
- Система регистрации и управления устройствами (аналог IXON)
- Создание временных ключей авторизации с ограничениями
- Процесс одобрения регистрации устройств

### 4. **RBAC System** (`rbac_system.py`)
- Ролевая система управления доступом
- 5 предустановленных ролей от Read Only до System Administrator  
- Группы устройств и политики доступа с временными ограничениями

## 🚀 Развертывание на Render

### Шаг 1: Запуск API Gateway локально

```bash
# Запуск API Gateway на порту 8000
python web_app/api_gateway.py
```

API будет доступен на `http://localhost:8000`

### Шаг 2: Настройка доступа через интернет

Для доступа к локальному API Gateway из интернета используйте:

**Вариант A: ngrok**
```bash
# Установите ngrok и запустите
ngrok http 8000
# Получите публичный URL типа https://abc123.ngrok.io
```

**Вариант B: CloudFlare Tunnel**
```bash
# Установите cloudflared и запустите
cloudflared tunnel --url http://localhost:8000
```

### Шаг 3: Развертывание на Render

1. **Создайте новый Web Service на Render**
2. **Подключите этот репозиторий**
3. **Настройте переменные окружения:**

```env
GATEWAY_URL=https://your-ngrok-url.ngrok.io  # URL вашего API Gateway
API_KEY=dev-api-key                          # API ключ (смотри логи api_gateway.py)
API_SECRET=ваш_секрет_из_логов              # API секрет из логов
SECRET_KEY=случайная_строка_для_flask       # Flask secret key
DEBUG=false
```

4. **Build Command:** `pip install -r requirements.txt`
5. **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2`

### Шаг 4: Получение API ключей

При запуске `api_gateway.py` в логах появятся ключи:

```
🔑 API Key: dev-api-key
🔐 API Secret: 1a2b3c4d5e6f7g8h9i0j...
```

Используйте эти ключи в настройках Render.

## 🔐 Безопасность

### API Аутентификация
- **API Key**: Идентификация клиента
- **HMAC Signature**: Подпись запроса с timestamp
- **Временные метки**: Защита от replay-атак (5 минут)

### Пример подписи запроса
```python
timestamp = str(int(time.time()))
payload = ""  # Пустой для GET запросов
message = f"{timestamp}{payload}"
signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
```

### Заголовки запроса
```
X-API-Key: dev-api-key
X-Timestamp: 1693123456
X-Signature: abcdef1234567890...
Content-Type: application/json
```

## 🌐 API Endpoints

### КУБ-1063 Monitoring API

- `GET /api/status` - Статус подключения к Gateway
- `GET /api/data/current` - Текущие показания КУБ-1063
- `GET /api/data/history?hours=6` - Исторические данные
- `GET /api/data/statistics` - Статистика системы

### Tailscale Management API

- `GET /api/tailscale/status` - Статус Tailscale mesh-сети  
- `GET /api/tailscale/devices` - Список всех устройств в tailnet
- `GET /api/tailscale/farms` - Список ферм (устройства с тегом farm)
- `GET /api/tailscale/devices/{id}` - Детали конкретного устройства
- `POST /api/tailscale/auth-key` - Создание ключа авторизации
- `POST /api/tailscale/connectivity/check` - Проверка подключения к ферме

### Device Registry API

- `POST /api/registry/register` - Регистрация нового устройства
- `GET /api/registry/devices` - Список зарегистрированных устройств
- `GET /api/registry/requests` - Ожидающие одобрения запросы
- `POST /api/registry/requests/{id}/approve` - Одобрение запроса регистрации
- `POST /api/registry/auth-key` - Создание ключа для регистрации
- `POST /api/registry/devices/{id}/revoke` - Отзыв устройства
- `POST /api/registry/devices/{id}/heartbeat` - Обновление статуса устройства
- `GET /api/registry/stats` - Статистика реестра устройств

## 🎨 Веб-интерфейс

### Главная страница (`/`)
- **Responsive дизайн** с Bootstrap 5 и градиентными фонами
- **Живые графики** температуры, влажности, CO₂, вентиляции на Chart.js
- **Автообновление** каждые 30 секунд
- **Метрики в реальном времени** с цветовой индикацией
- **Адаптивная верстка** для мобильных устройств

### Страница Tailscale (`/tailscale`)
- **Управление mesh-сетью** с визуализацией устройств
- **Табы для устройств и ферм** с детальной информацией
- **Создание ключей авторизации** через модальные окна
- **Проверка подключения** к устройствам одним кликом
- **Real-time статус** устройств с API reachability индикаторами

## 🗄️ База данных

Приложение использует 3 SQLite базы данных:

### 1. **kub_data.db** - Данные КУБ-1063
```sql
-- Временные ряды показаний
kub_readings: timestamp, temp_inside, temp_target, humidity, co2, ventilation_level
-- Статистика и метаданные  
kub_statistics: success_rate, total_readings, error_count
```

### 2. **device_registry.db** - Реестр устройств  
```sql
-- Зарегистрированные устройства
registered_devices: device_id, hostname, tailscale_ip, status, device_type, metadata
-- Ключи авторизации
auth_keys: key_id, key_hash, created_time, expires_time, usage_count
-- Запросы на регистрацию  
device_registration_requests: request_id, device_hostname, status
```

### 3. **rbac_system.db** - Система доступа
```sql  
-- Пользователи и роли
users: user_id, username, email, roles, device_groups
roles: role_id, name, permissions, is_system_role
-- Группы устройств и политики
device_groups: group_id, name, device_ids, device_types, tags_filter  
access_policies: policy_id, device_group_id, role_id, permissions
```

## 🔧 Настройка переменных окружения

```bash
# Подключение к Gateway API
GATEWAY_URL=http://localhost:8000
API_KEY=your-gateway-api-key
API_SECRET=your-gateway-api-secret

# Tailscale интеграция (опционально)
TAILSCALE_ENABLED=true
TAILSCALE_TAILNET=your-tailnet.ts.net  
TAILSCALE_API_KEY=tskey-api-xxxxxxxxxx

# Flask настройки
SECRET_KEY=your-flask-secret-key
DEBUG=false
PORT=5000
```

## 🚀 Локальная разработка

```bash
# 1. Установка зависимостей
pip install -r requirements.txt

# 2. Запуск Modbus Gateway (в отдельном терминале)
python modbus/gateway.py

# 3. Настройка переменных окружения
export GATEWAY_URL=http://localhost:8000
export API_KEY=dev-api-key
export API_SECRET=your-secret-from-gateway-logs

# 4. Запуск веб-приложения  
python app.py
```

Приложение будет доступно на `http://localhost:5000`

## 🐛 Отладка

### Проверка статуса системы
```bash
# Проверка Gateway API
curl http://localhost:8000/api/health

# Проверка веб-приложения
curl http://localhost:5000/api/status  

# Проверка Tailscale статуса
curl http://localhost:5000/api/tailscale/status
```

### Логирование
- **Консольные логи**: уровень INFO для основных операций
- **Файлы логов**: `config/logs/` для Gateway, `tunnel_system/config/logs/` для Tailscale
- **Debug режим**: установить `DEBUG=true` для детальных логов

### Частые проблемы
1. **Connection refused**: Проверьте запуск Modbus Gateway на порту 8000
2. **Tailscale not configured**: Убедитесь в настройке `TAILSCALE_*` переменных
3. **Database locks**: Перезапустите все сервисы при блокировке SQLite
4. **CORS errors**: Проверьте настройки Flask-CORS

## 📊 Мониторинг

### Dashboard КУБ-1063 показывает:
- **Текущие показания**: температура (°C), влажность (%), CO₂ (ppm), вентиляция (%)
- **Исторические графики**: временные ряды за последние 6 часов
- **Статистику системы**: успешность опросов, общее количество измерений
- **Статус подключения**: индикатор связи с Gateway

### Tailscale Dashboard показывает:  
- **Статус mesh-сети**: количество устройств онлайн/офлайн
- **Список всех устройств**: с Tailscale IP и статусом API
- **Фермы КУБ-1063**: устройства с тегом "farm"
- **Управление ключами**: создание auth keys для регистрации

## 🔄 Обновления и развертывание

### Для локальной разработки:
```bash
git pull origin main
pip install -r requirements.txt  
python app.py
```

### Для production (Render/Docker):
1. Обновите код в репозитории
2. Render/Docker автоматически пересобирает приложение
3. Убедитесь в правильности переменных окружения
4. Modbus Gateway должен быть доступен по GATEWAY_URL