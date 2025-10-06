# 📱 CUBE RS Mobile APP

Мобильное приложение и веб-интерфейс для управления EDGE устройствами через SERVER.

## 🏗️ Архитектура

```
📱 Mobile/Web APP          🌐 SERVER          📡 EDGE
       │                      │                 │
   ┌───▼───┐              ┌───▼───┐         ┌───▼───┐
   │ User  │◀─────────────│ Auth  │◀────────│ API   │
   │ Auth  │              │ JWT   │         │ Keys  │
   └───┬───┘              └───┬───┘         └───┬───┘
       │                      │                 │
   ┌───▼───┐              ┌───▼───┐         ┌───▼───┐
   │ Farm  │◀─────────────│ Device│◀────────│ Data  │
   │ View  │              │ Mgmt  │         │ Send  │
   └───┬───┘              └───┬───┘         └───┬───┘
       │                      │                 │
   ┌───▼───┐              ┌───▼───┐         ┌───▼───┐
   │ P2P   │◀─────────────│Tunnel │◀────────│ KUB   │
   │ Tunnel│              │Broker │         │ Data  │
   └───────┘              └───────┘         └───────┘
```

## 🚀 Быстрый запуск

### Разработка

```bash
cd APP

# Установка зависимостей
pip3 install -r requirements.txt

# Переменные окружения
export SERVER_URL="http://localhost:8080"
export SECRET_KEY="development-secret"
export DEBUG="true"

# Запуск
python3 main_app.py
```

### Продакшен

```bash
# Docker build
docker build -t cube-rs-app .

# Docker run
docker run -p 5000:5000 \
  -e SERVER_URL="https://your-server.com:8080" \
  -e SECRET_KEY="production-secret-key" \
  -e DEBUG="false" \
  cube-rs-app
```

## 📋 API Endpoints

### Аутентификация

| Method | Endpoint | Описание |
|--------|----------|----------|
| POST | `/api/auth/login` | Вход в систему |
| POST | `/api/auth/refresh` | Обновление токена |
| GET | `/api/user/profile` | Профиль пользователя |

### Фермы и устройства

| Method | Endpoint | Описание |
|--------|----------|----------|
| GET | `/api/farms` | Список ферм |
| GET | `/api/farms/{farm_id}/devices` | Устройства фермы |
| GET | `/api/devices/{device_id}/data` | Данные устройства |
| GET | `/api/devices/{device_id}/history` | История данных |

### Real-time данные

| Method | Endpoint | Описание |
|--------|----------|----------|
| GET | `/api/realtime/status` | Статус устройств |
| POST | `/api/tunnel/connect` | P2P туннель |

### Система

| Method | Endpoint | Описание |
|--------|----------|----------|
| GET | `/health` | Health check |
| GET | `/api/system/status` | Системная информация |

## 🔐 Аутентификация

APP использует JWT токены от SERVER для аутентификации:

### Мобильное приложение
```javascript
// Login
const response = await fetch('/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username, password })
});

const { token } = await response.json();

// Использование токена
const apiResponse = await fetch('/api/farms', {
  headers: { 
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
});
```

### Веб-интерфейс
```html
<!-- Форма входа -->
<form method="post" action="/login">
  <input name="username" required>
  <input name="password" type="password" required>
  <button type="submit">Login</button>
</form>
```

## 📊 Мониторинг ферм

### Получение данных фермы
```javascript
const farmData = await fetch(`/api/farms/${farmId}/devices`, {
  headers: { 'Authorization': `Bearer ${token}` }
}).then(r => r.json());

farmData.devices.forEach(device => {
  console.log(`${device.name}: ${device.status}`);
  
  // Данные КУБ устройств
  if (device.kub_devices) {
    device.kub_devices.forEach(kub => {
      console.log(`КУБ-${kub.type}: T=${kub.temperature}°C, H=${kub.humidity}%`);
    });
  }
});
```

### Real-time обновления
```javascript
// Периодическое обновление статуса
setInterval(async () => {
  const status = await fetch('/api/realtime/status', {
    headers: { 'Authorization': `Bearer ${token}` }
  }).then(r => r.json());
  
  updateDashboard(status);
}, 10000); // каждые 10 секунд
```

## 🔗 P2P туннели

### Подключение к EDGE устройству
```javascript
const tunnelRequest = {
  device_id: 'edge_abc123',
  connection_type: 'direct_access'
};

const tunnel = await fetch('/api/tunnel/connect', {
  method: 'POST',
  headers: { 
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify(tunnelRequest)
}).then(r => r.json());

if (tunnel.status === 'connected') {
  console.log(`Tunnel URL: ${tunnel.tunnel_url}`);
  console.log(`WebRTC Peer ID: ${tunnel.peer_id}`);
}
```

## 📱 Мобильное приложение

### React Native интеграция
```javascript
import AsyncStorage from '@react-native-async-storage/async-storage';

class CubeRSAPI {
  constructor() {
    this.baseURL = 'https://your-app-server.com';
  }

  async login(username, password) {
    const response = await fetch(`${this.baseURL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });

    const data = await response.json();
    
    if (data.token) {
      await AsyncStorage.setItem('auth_token', data.token);
    }
    
    return data;
  }

  async getFarms() {
    const token = await AsyncStorage.getItem('auth_token');
    
    const response = await fetch(`${this.baseURL}/api/farms`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });

    return response.json();
  }

  async getDeviceData(deviceId) {
    const token = await AsyncStorage.getItem('auth_token');
    
    const response = await fetch(`${this.baseURL}/api/devices/${deviceId}/data`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });

    return response.json();
  }
}
```

### Flutter интеграция  
```dart
class CubeRSAPI {
  final String baseURL = 'https://your-app-server.com';
  final SharedPreferences prefs;

  Future<Map<String, dynamic>> login(String username, String password) async {
    final response = await http.post(
      Uri.parse('$baseURL/api/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({'username': username, 'password': password}),
    );

    final data = json.decode(response.body);
    
    if (data['token'] != null) {
      await prefs.setString('auth_token', data['token']);
    }
    
    return data;
  }

  Future<List<dynamic>> getFarms() async {
    final token = prefs.getString('auth_token');
    
    final response = await http.get(
      Uri.parse('$baseURL/api/farms'),
      headers: {'Authorization': 'Bearer $token'},
    );

    final data = json.decode(response.body);
    return data['farms'] ?? [];
  }
}
```

## 🔧 Конфигурация

### Переменные окружения

```bash
# SERVER подключение
SERVER_URL=https://your-server.com:8080
TUNNEL_BROKER_URL=https://your-server.com:8080

# Безопасность  
SECRET_KEY=your-very-long-secret-key-here
DEBUG=false

# Веб-сервер
PORT=5000
FLASK_ENV=production

# CORS
ALLOWED_ORIGINS=https://your-mobile-app.com,https://your-web-app.com
```

### Docker Compose
```yaml
version: '3.8'

services:
  cube-rs-app:
    build: .
    ports:
      - "5000:5000"
    environment:
      - SERVER_URL=http://server:8080
      - SECRET_KEY=production-secret-key
      - DEBUG=false
    depends_on:
      - server
    restart: unless-stopped
    
  server:
    image: cube-rs-server
    ports:
      - "8080:8080"
    # ... SERVER конфигурация
```

## 🔍 Разработка

### Структура проекта
```
APP/
├── backend/
│   ├── main_app.py      # Основное приложение
│   ├── api.py           # Расширенные API маршруты
│   └── requirements.txt
├── frontend/
│   ├── static/          # CSS, JS, изображения
│   └── templates/       # HTML шаблоны
├── mobile/
│   ├── react_native/    # React Native код
│   └── flutter/         # Flutter код
├── tests/
│   ├── test_auth.py
│   ├── test_api.py
│   └── test_integration.py
├── config/
│   └── app_config.yaml
├── docs/
│   └── API.md
├── Dockerfile
├── docker-compose.yml
└── README.md
```

### Локальная разработка
```bash
# Запуск с live reload
export FLASK_ENV=development
export DEBUG=true
python3 main_app.py

# Тестирование
pytest tests/

# Линтинг
flake8 backend/
black backend/
```

## 🐞 Отладка

### Логи
```bash
# Просмотр логов
docker logs cube-rs-app

# Логи в реальном времени
docker logs -f cube-rs-app
```

### Health check
```bash
# Проверка состояния
curl http://localhost:5000/health

# Ответ:
{
  "status": "healthy",
  "timestamp": "2025-09-07T12:00:00Z",
  "app_version": "1.0.0", 
  "server_connection": true,
  "server_url": "http://localhost:8080"
}
```

## 📈 Масштабирование

### Load Balancer
```nginx
upstream cube_rs_app {
    server app1:5000;
    server app2:5000;
    server app3:5000;
}

server {
    listen 80;
    
    location / {
        proxy_pass http://cube_rs_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Мониторинг
- **Prometheus**: метрики производительности
- **Grafana**: визуализация статистики
- **ELK Stack**: централизованные логи

## 🎯 Результат

**Полный APP проект готов к развертыванию:**

✅ **Flask Backend** с API для мобильных приложений  
✅ **JWT Authentication** интеграция с SERVER  
✅ **CORS Support** для кроссплатформенных запросов  
✅ **Docker Container** для легкого развертывания  
✅ **Health Checks** для мониторинга  
✅ **Error Handling** и логирование  
✅ **Mobile SDK Examples** для React Native и Flutter  

APP готов к подключению мобильных и веб-приложений! 🚀