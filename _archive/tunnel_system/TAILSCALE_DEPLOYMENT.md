# 🚀 Tailscale-based Tunnel System - Руководство по развертыванию

## 🎯 Обзор системы

Полностью независимая система туннелирования на базе Tailscale mesh-сети для КУБ-1063 ферм. Заменяет WebRTC + централизованный broker на прямые зашифрованные соединения.

```
📱 Mobile App ←---Tailscale Mesh---→ 🏭 Farm Gateway
        ↑                               ↑
        └──────Discovery Service────────┘
              (упрощенный координатор)
```

## 📦 Компоненты системы

### 1. **TailscaleManager** (`tailscale_manager.py`)
- Базовая интеграция с Tailscale API
- Управление устройствами в mesh-сети
- Автоматическая регистрация и мониторинг

### 2. **Discovery Service** (`tailscale_discovery_service.py`)
- Замена tunnel_broker без координации WebRTC
- Хранение метаданных ферм
- REST API для обнаружения ферм

### 3. **Farm Client** (`tailscale_farm_client.py`)
- Клиент фермы с Tailscale интеграцией
- HTTP API для данных КУБ-1063
- Автоматическая регистрация и heartbeat

### 4. **Mobile App** (`tailscale_mobile_app.py`)
- Веб-интерфейс для мобильных устройств
- Прямые HTTP соединения к фермам
- Realtime мониторинг данных

## 🛠️ Требования

### Системные требования
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip python3-venv curl

# CentOS/RHEL  
sudo yum install python3 python3-pip curl
```

### Python зависимости
```bash
pip install aiohttp flask flask-cors asyncio
```

### Tailscale
```bash
# Установка на всех устройствах
curl -fsSL https://tailscale.com/install.sh | sh
```

## 🌐 Настройка Tailnet

### 1. Создание Tailnet
1. Зарегистрируйтесь на [tailscale.com](https://tailscale.com)
2. Создайте новый tailnet или используйте существующий
3. Получите имя tailnet (например: `your-company.ts.net`)

### 2. Создание API ключа
1. Перейдите в [Admin Console](https://login.tailscale.com/admin/settings/keys)
2. Generate API key
3. Сохраните ключ: `tskey-api-xxxxxxxxxxxxxxxx`

### 3. ACL конфигурация
```json
{
  "tagOwners": {
    "tag:farm": ["admin@your-company.com"],
    "tag:mobile": ["admin@your-company.com"],
    "tag:discovery": ["admin@your-company.com"]
  },
  "acls": [
    {
      "action": "accept",
      "src": ["tag:mobile"],
      "dst": ["tag:farm:8080", "tag:discovery:8082"]
    },
    {
      "action": "accept",
      "src": ["tag:farm"],
      "dst": ["tag:discovery:8082"]
    }
  ]
}
```

## 🏗️ Развертывание системы

### Шаг 1: Discovery Service (центральный сервер)

```bash
# 1. Установка Tailscale
sudo tailscale up --authkey=tskey-auth-xxxx --hostname=discovery-service

# 2. Настройка переменных окружения
export TAILNET="your-company.ts.net"
export TAILSCALE_API_KEY="tskey-api-xxxx"

# 3. Запуск Discovery Service
cd tunnel_system
python tailscale_discovery_service.py

# Сервис будет доступен на порту 8082
```

### Шаг 2: Farm Client (на каждой ферме)

```bash
# 1. Установка Tailscale на ферме
sudo tailscale up --authkey=tskey-auth-xxxx --hostname=farm-001

# 2. Настройка переменных окружения
export FARM_ID="farm-kub1063-001"
export FARM_NAME="Ферма КУБ-1063 Теплица №1"
export OWNER_ID="user_farmer1"
export TAILNET="your-company.ts.net"
export TAILSCALE_API_KEY="tskey-api-xxxx"
export DISCOVERY_SERVICE_URL="http://discovery-service-tailscale-ip:8082"

# 3. Запуск Farm Client
cd tunnel_system
python tailscale_farm_client.py

# API фермы будет доступен на порту 8080
```

### Шаг 3: Mobile App (веб-сервер)

```bash
# 1. Установка Tailscale (опционально, для доступа к внутренней сети)
sudo tailscale up --authkey=tskey-auth-xxxx --hostname=mobile-app

# 2. Настройка переменных окружения  
export DISCOVERY_SERVICE_URL="http://discovery-service-tailscale-ip:8082"
export TAILNET="your-company.ts.net"
export TAILSCALE_API_KEY="tskey-api-xxxx"

# 3. Запуск Mobile App
cd tunnel_system
python tailscale_mobile_app.py

# Веб-интерфейс будет доступен на порту 5000
```

## 🔧 Конфигурация

### Discovery Service конфиг
```yaml
# config.yaml
tailnet: "your-company.ts.net"
api_key: "tskey-api-xxxx"
database_path: "discovery.db"
host: "0.0.0.0" 
port: 8082
sync_interval: 300  # Синхронизация с Tailnet каждые 5 минут
```

### Farm Client конфиг
```yaml
# farm_config.yaml
farm:
  id: "farm-kub1063-001"
  name: "Ферма КУБ-1063 Теплица №1"  
  owner_id: "user_farmer1"
  location: "greenhouse-1"
  capabilities: ["kub1063", "monitoring", "control"]
  api_port: 8080

tailscale:
  tailnet: "your-company.ts.net"
  api_key: "tskey-api-xxxx"

discovery:
  service_url: "http://discovery-service-tailscale-ip:8082"
  heartbeat_interval: 300
```

## 🔐 Безопасность

### Tailscale ACL
```json
{
  "tagOwners": {
    "tag:farm": ["admin@company.com"],
    "tag:mobile": ["admin@company.com"]
  },
  "acls": [
    {
      "action": "accept",
      "src": ["tag:mobile"],
      "dst": ["tag:farm:8080"]
    },
    {
      "action": "deny",
      "src": ["tag:farm"],
      "dst": ["tag:farm:*"]
    }
  ]
}
```

### API ключи
- Используйте отдельные ключи для каждого компонента
- Ограничьте права доступа ключей
- Регулярно ротируйте ключи

### Firewall
```bash
# На фермах - только Tailscale трафик
sudo ufw allow in on tailscale0
sudo ufw deny 8080  # Блокируем внешний доступ к API
```

## 🚀 Автозапуск сервисов

### Systemd для Discovery Service
```ini
# /etc/systemd/system/tailscale-discovery.service
[Unit]
Description=Tailscale Discovery Service
After=network.target tailscaled.service
Requires=tailscaled.service

[Service]
Type=simple
User=discovery
WorkingDirectory=/opt/tunnel-system
Environment=TAILNET=your-company.ts.net
Environment=TAILSCALE_API_KEY=tskey-api-xxxx
ExecStart=/usr/bin/python3 tailscale_discovery_service.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Systemd для Farm Client
```ini
# /etc/systemd/system/tailscale-farm.service
[Unit]
Description=Tailscale Farm Client
After=network.target tailscaled.service
Requires=tailscaled.service

[Service]
Type=simple
User=farm
WorkingDirectory=/opt/tunnel-system
Environment=FARM_ID=farm-kub1063-001
Environment=TAILNET=your-company.ts.net
Environment=TAILSCALE_API_KEY=tskey-api-xxxx
ExecStart=/usr/bin/python3 tailscale_farm_client.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Docker Compose (опционально)
```yaml
version: '3.8'

services:
  discovery-service:
    build: .
    command: python tailscale_discovery_service.py
    environment:
      - TAILNET=your-company.ts.net
      - TAILSCALE_API_KEY=tskey-api-xxxx
    volumes:
      - ./data:/app/data
      - /dev/net/tun:/dev/net/tun
    cap_add:
      - NET_ADMIN
    ports:
      - "8082:8082"
      
  farm-client:
    build: .
    command: python tailscale_farm_client.py
    environment:
      - FARM_ID=farm-001
      - TAILNET=your-company.ts.net
      - TAILSCALE_API_KEY=tskey-api-xxxx
    volumes:
      - /dev/net/tun:/dev/net/tun
    cap_add:
      - NET_ADMIN
    ports:
      - "8080:8080"
```

## 📊 Мониторинг

### Health Checks
```bash
# Проверка Discovery Service
curl http://discovery-tailscale-ip:8082/health

# Проверка Farm Client
curl http://farm-tailscale-ip:8080/health

# Проверка Tailscale соединения
tailscale status
```

### Логирование
```bash
# Discovery Service логи
journalctl -u tailscale-discovery -f

# Farm Client логи  
journalctl -u tailscale-farm -f

# Tailscale логи
journalctl -u tailscaled -f
```

### Prometheus метрики (расширение)
```python
# В каждом сервисе добавить:
from prometheus_client import Counter, Histogram, start_http_server

requests_total = Counter('requests_total', 'Total requests')
response_time = Histogram('response_time_seconds', 'Response time')
```

## 🐛 Диагностика

### Типичные проблемы

**1. Ферма не появляется в Discovery Service**
```bash
# Проверяем Tailscale подключение
tailscale status

# Проверяем теги устройства
tailscale status --json | jq '.Peer[].Tags'

# Тестируем соединение с Discovery Service
curl http://discovery-ip:8082/health
```

**2. Mobile App не видит фермы**
```bash
# Проверяем API Discovery Service
curl http://discovery-ip:8082/api/farms

# Проверяем ACL права доступа
tailscale status --json | jq '.User.Permissions'
```

**3. Нет соединения между устройствами**
```bash
# Проверяем mesh соединения
tailscale ping farm-tailscale-ip

# Проверяем NAT traversal
tailscale netcheck
```

### Отладочные команды
```bash
# Детальная информация о Tailscale
tailscale status --json

# Список всех устройств в сети  
tailscale status --peers

# Проверка сетевой связности
tailscale ping <device-ip>

# Анализ трафика
tcpdump -i tailscale0
```

## 🔄 Обновления

### Обновление кода
```bash
# Остановка сервисов
sudo systemctl stop tailscale-discovery tailscale-farm

# Обновление кода
git pull origin main

# Перезапуск сервисов
sudo systemctl start tailscale-discovery tailscale-farm
```

### Обновление Tailscale
```bash
# Обновление Tailscale агента
sudo tailscale update

# Проверка версии
tailscale version
```

## 📈 Масштабирование

### Множественные Discovery Service
```bash
# Запуск нескольких экземпляров с балансировкой
# nginx.conf
upstream discovery_backend {
    server discovery-1-ip:8082;
    server discovery-2-ip:8082;
    server discovery-3-ip:8082;
}
```

### Региональное развертывание
```yaml
# Разные tailnet для разных регионов
regions:
  europe:
    tailnet: "europe.company.ts.net" 
    discovery: "discovery-eu.company.ts.net:8082"
  asia:
    tailnet: "asia.company.ts.net"
    discovery: "discovery-asia.company.ts.net:8082"
```

## ✅ Преимущества Tailscale решения

| Критерий | WebRTC + Broker | Tailscale Mesh |
|----------|-----------------|----------------|
| **Независимость** | Требует внешний broker | Полная автономность |
| **NAT traversal** | Сложная настройка STUN/TURN | Автоматический |
| **Безопасность** | Ручное управление ключами | Enterprise-grade из коробки |
| **Масштабирование** | Ограничено broker | Неограниченное mesh |
| **Простота развертывания** | Множество компонентов | Один агент на устройство |
| **Отказоустойчивость** | SPOF broker | Децентрализованная сеть |
| **Управление** | Ручная конфигурация | Центральная консоль |

## 🎯 Результат

**Получили полностью независимую систему:**
- ✅ Никаких внешних зависимостей (ngrok, STUN, TURN)
- ✅ Автоматическое обнаружение ферм в mesh-сети
- ✅ Прямые зашифрованные соединения
- ✅ Простое развертывание (один Tailscale агент)
- ✅ Enterprise безопасность с ACL
- ✅ Масштабирование до тысяч устройств

---

**🚀 Система готова к production использованию!**

Вопросы или проблемы с развертыванием? Обратитесь к разделу диагностики или создайте issue в репозитории.