# 🚀 Пошаговое руководство по развертыванию

## 📋 Готовые API ключи

После запуска API Gateway (`python web_app/api_gateway.py`) используйте эти ключи:

```
🔑 API Key: dev-api-key
🔐 API Secret: 4d8d11471b23dc17f7200dd70776e9d6b91a483b4f967146b608f872efd7720a
```

## 🛠️ Шаг 1: Запуск локального API Gateway

```bash
cd /path/to/CUBE_RS
python web_app/api_gateway.py
```

API будет доступен на:
- `http://localhost:8000`
- `http://192.168.10.42:8000` (локальная сеть)

## 🌐 Шаг 2: Открытие доступа через интернет

### Вариант A: ngrok (рекомендуется)

1. **Установите ngrok:** https://ngrok.com/download
2. **Запустите туннель:**
   ```bash
   ngrok http 8000
   ```
3. **Скопируйте публичный URL** (например: `https://abc123.ngrok.io`)

### Вариант B: CloudFlare Tunnel

1. **Установите cloudflared:** https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/
2. **Запустите туннель:**
   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```

### Вариант C: Собственный домен с проксированием

Настройте nginx/Apache для проксирования на локальный порт 8000.

## ☁️ Шаг 3: Развертывание на Render

### 3.1 Создание Web Service

1. Зайдите на **https://render.com**
2. Нажмите **"New +"** → **"Web Service"**
3. Подключите репозиторий GitHub с кодом
4. Настройте параметры:

```yaml
Name: kub-1063-web-app
Environment: Python 3
Build Command: pip install -r web_app/requirements.txt
Start Command: cd web_app && gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

### 3.2 Настройка переменных окружения

В разделе **Environment Variables** добавьте:

```env
GATEWAY_URL=https://your-ngrok-url.ngrok.io
API_KEY=dev-api-key
API_SECRET=4d8d11471b23dc17f7200dd70776e9d6b91a483b4f967146b608f872efd7720a
SECRET_KEY=your-random-flask-secret-key-here
DEBUG=false
API_TIMEOUT=10
```

⚠️ **ВАЖНО:** Замените `https://your-ngrok-url.ngrok.io` на реальный URL из шага 2!

### 3.3 Deploy

Нажмите **"Create Web Service"** - Render автоматически соберет и запустит приложение.

## 🧪 Шаг 4: Проверка работы

### Локальная проверка API
```bash
curl -H "X-API-Key: dev-api-key" \
     -H "X-Timestamp: $(date +%s)" \
     -H "X-Signature: your_signature" \
     http://localhost:8000/api/health
```

### Проверка Web App на Render
1. Откройте URL вашего приложения на Render
2. Проверьте статус подключения (зеленый индикатор)
3. Убедитесь, что данные загружаются

## 🔧 Настройка автозапуска (опционально)

### Создание systemd службы для API Gateway

```bash
sudo nano /etc/systemd/system/kub-api-gateway.service
```

```ini
[Unit]
Description=KUB-1063 API Gateway
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/CUBE_RS
ExecStart=/usr/bin/python3 web_app/api_gateway.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable kub-api-gateway
sudo systemctl start kub-api-gateway
```

## 📊 Мониторинг

### Логи API Gateway
```bash
# При работе через systemd
sudo journalctl -u kub-api-gateway -f

# При ручном запуске
# Логи выводятся в консоль
```

### Логи Web App на Render
- Заходите в дашборд Render
- Выберите ваш сервис
- Вкладка "Logs"

## 🐛 Решение проблем

### Проблема: Web App показывает "Отключено"

**Решение:**
1. Проверьте, что API Gateway запущен локально
2. Проверьте доступность ngrok туннеля
3. Убедитесь, что GATEWAY_URL в переменных Render корректный
4. Проверьте API ключи в логах API Gateway

### Проблема: 403 Forbidden при запросах к API

**Решение:**
1. Проверьте API_KEY и API_SECRET в переменных Render
2. Убедитесь, что они совпадают с выводом API Gateway
3. Проверьте временные метки (не старше 5 минут)

### Проблема: Timeout ошибки

**Решение:**
1. Увеличьте API_TIMEOUT в переменных до 30
2. Проверьте стабильность интернет-соединения
3. Рассмотрите использование CloudFlare Tunnel вместо ngrok

### Проблема: Нет данных в графиках

**Решение:**
1. Убедитесь, что система КУБ-1063 подключена и работает
2. Проверьте, что Gateway собирает данные в БД
3. Протестируйте API Gateway напрямую:
   ```bash
   python dashboard/dashboard_reader.py
   ```

## 🔒 Безопасность в продакшене

### Генерация новых API ключей
```python
import secrets
api_key = f"prod-{secrets.token_hex(8)}"
api_secret = secrets.token_hex(32)
print(f"API Key: {api_key}")  
print(f"API Secret: {api_secret}")
```

### Настройка HTTPS Only
В переменных Render добавьте:
```env
FORCE_HTTPS=true
```

### Ограничение CORS
Отредактируйте `api_gateway.py`:
```python
CORS(app, origins=["https://your-render-app.onrender.com"])
```

## 📈 Мониторинг производительности

### Health Check endpoints
- API Gateway: `http://localhost:8000/api/health`
- Web App: `https://your-app.onrender.com/health`

### Метрики для мониторинга
- Время ответа API Gateway
- Количество успешных/неуспешных запросов
- Использование памяти и CPU
- Стабильность ngrok туннеля

## 🚀 Готово!

После выполнения всех шагов у вас будет:
- ✅ Локальный API Gateway с защищенным доступом
- ✅ Публичный доступ через ngrok/CloudFlare
- ✅ Web приложение на Render с красивым интерфейсом
- ✅ Автоматическое обновление данных каждые 30 секунд

Ваша система КУБ-1063 теперь доступна из любой точки мира! 🌍