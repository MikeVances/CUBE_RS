# КУБ-1063 Web Application

Веб-приложение для удаленного мониторинга системы КУБ-1063 через защищенный API.

## 🏗️ Архитектура

```
CUBE-1063 → Gateway (локальный) → API Gateway → WWW → Web App (Render)
```

## 🔧 Компоненты

### 1. **API Gateway** (`api_gateway.py`)
- Локальный сервер, предоставляющий защищенный API
- HMAC аутентификация с временными метками
- Доступ к данным через модули dashboard_reader

### 2. **Web Application** (`app.py`)
- Flask приложение для развертывания на Render
- Красивый дашборд с графиками Chart.js
- Автоматическое обновление данных

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

### Gateway API (локальный)

- `GET /api/health` - Статус системы
- `GET /api/data/current` - Текущие данные
- `GET /api/data/history?hours=6` - Исторические данные
- `GET /api/data/statistics` - Статистика системы
- `GET /api/keys/info` - Информация об API ключе

### Web App API

- `GET /api/status` - Статус подключения к Gateway
- `GET /api/data/current` - Проксирование текущих данных
- `GET /api/data/history` - Проксирование исторических данных
- `GET /api/data/statistics` - Проксирование статистики

## 🎨 Интерфейс

- **Responsive дизайн** с Bootstrap 5
- **Живые графики** на Chart.js с временными осями
- **Автообновление** каждые 30 секунд
- **Статусные индикаторы** подключения
- **Адаптивная верстка** для мобильных устройств

## 🐛 Отладка

### Проверка подключения
```bash
# Локально проверить API Gateway
curl -H "X-API-Key: dev-api-key" \
     -H "X-Timestamp: $(date +%s)" \
     -H "X-Signature: ваша_подпись" \
     http://localhost:8000/api/health
```

### Логи
- API Gateway: консольные логи
- Web App: логи Render в дашборде

### Частые проблемы
1. **API ключи не совпадают**: Проверьте логи api_gateway.py
2. **Timeout ошибки**: Увеличьте API_TIMEOUT в переменных окружения
3. **CORS ошибки**: Проверьте настройки CORS в api_gateway.py

## 📊 Мониторинг

Web приложение показывает:
- **Текущие значения**: температура, влажность, CO₂, вентиляция
- **Исторические графики**: за последние 6 часов
- **Статистику**: успешность, количество измерений, статус системы
- **Статус подключения**: индикатор связи с Gateway

## 🔄 Обновления

Для обновления кода:
1. Обновите код в репозитории
2. Render автоматически пересоберет приложение
3. API Gateway нужно перезапустить локально