# 🚀 Deployment Pipeline - Масштабный тест CUBE_RS

Полная инструкция для развертывания системы CUBE_RS в production окружении.

## 🎯 Архитектура развертывания

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Render.com    │    │   VPS Server     │    │   Local Farm    │
│   (Web App)     │◄──►│  (Tunnel System) │◄──►│   (Gateway +    │
│   - Dashboard   │    │  - Tailscale     │    │    КУБ-1063)    │
│   - RBAC        │    │  - Device Mgmt   │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
       ↑                         ↑                        ↑
   Internet             White IP Address            Local Network
```

## 📋 Этап 1: Подготовка к развертыванию

### 1.1 Требования

**Для Render.com (Web App):**
- Аккаунт на Render.com (бесплатный tier)
- GitHub репозиторий с web_app

**Для VPS (Tunnel System):**
- VPS с Ubuntu 20.04+ или CentOS 7+ 
- 1 GB RAM, 1 vCPU, 10 GB SSD (минимум)
- Белый IP адрес
- Root доступ по SSH

**Для фермы (Local):**
- Linux/macOS/Windows компьютер
- КУБ-1063 подключенный по Modbus TCP/RTU
- Python 3.8+ и права на установку пакетов

### 1.2 Подготовка репозитория

```bash
# 1. Создайте отдельный репозиторий для web_app
mkdir cube_rs_webapp
cd cube_rs_webapp

# 2. Скопируйте только web_app файлы
cp -r /path/to/CUBE_RS/web_app/* .

# 3. Инициализируйте Git
git init
git add .
git commit -m "Initial web app deployment"

# 4. Загрузите на GitHub
gh repo create cube-rs-webapp --public
git remote add origin https://github.com/yourusername/cube-rs-webapp.git
git push -u origin main
```

## 🌐 Этап 2: Развертывание Web App на Render.com

### 2.1 Создание сервиса на Render

1. **Войдите в Render.com** и нажмите "New Web Service"
2. **Подключите GitHub репозиторий** cube-rs-webapp
3. **Настройте параметры:**
   ```
   Name: cube-rs-monitor
   Environment: Python 3
   Build Command: pip install -r requirements.txt
   Start Command: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
   ```

### 2.2 Настройка переменных окружения

В Render Dashboard добавьте Environment Variables:

```bash
# Подключение к Gateway API (будет настроено позже)
GATEWAY_URL=https://your-vps-ip:8000
API_KEY=dev-api-key
API_SECRET=your-gateway-secret

# Tailscale интеграция (опционально)
TAILSCALE_ENABLED=false  # Пока отключаем
TAILSCALE_TAILNET=your-company.ts.net
TAILSCALE_API_KEY=tskey-api-xxxxxxxxxx

# Flask настройки  
SECRET_KEY=your-super-secret-flask-key-here
DEBUG=false
PORT=5000
```

### 2.3 Deploy и проверка

1. **Нажмите "Create Web Service"** - Render автоматически соберет и развернет приложение
2. **Дождитесь завершения** (обычно 2-3 минуты)
3. **Проверьте работу** по URL: https://cube-rs-monitor.onrender.com

**Ожидаемый результат:**
- ✅ Веб-интерфейс загружается
- ⚠️ Ошибки подключения к Gateway (это нормально, Gateway еще не настроен)

## 🖥️ Этап 3: Развертывание Tunnel System на VPS

### 3.1 Подключение к VPS

```bash
# Подключитесь к VPS по SSH
ssh root@YOUR_VPS_IP

# Обновите систему
apt update && apt upgrade -y  # Ubuntu/Debian
# или
yum update -y  # CentOS/RHEL
```

### 3.2 Загрузка и установка

```bash
# 1. Скачайте tunnel_system на VPS
git clone https://github.com/yourusername/CUBE_RS.git
cd CUBE_RS/tunnel_system

# 2. Сделайте скрипт исполняемым и запустите установку
chmod +x deploy.sh
sudo ./deploy.sh
```

**Скрипт установки автоматически:**
- Установит Python 3, Nginx, зависимости
- Создаст пользователя tunnel-system
- Настроит автозапуск через systemd
- Настроит Nginx reverse proxy  
- Откроет порты в файрволе
- Запустит сервисы

### 3.3 Проверка установки

```bash
# Проверка статуса сервисов
tunnel-system status

# Проверка логов
tunnel-system logs

# Проверка API
tunnel-system health
```

**Ожидаемый вывод:**
```bash
✅ Tunnel Broker отвечает на http://YOUR_VPS_IP:8080
🌍 Внешний доступ: http://YOUR_VPS_IP
🔧 API: http://YOUR_VPS_IP:8080
```

### 3.4 Настройка SSL (рекомендуется)

```bash
# Установка Certbot
sudo apt install certbot python3-certbot-nginx -y

# Получение SSL сертификата (замените example.com на ваш домен)
sudo certbot --nginx -d your-domain.com

# Проверка автообновления
sudo certbot renew --dry-run
```

## 🏭 Этап 4: Настройка фермы (Local Gateway)

### 4.1 Подготовка фермы

```bash
# На компьютере фермы
git clone https://github.com/yourusername/CUBE_RS.git
cd CUBE_RS

# Установка зависимостей
pip install -r requirements.txt
```

### 4.2 Настройка подключения к КУБ-1063

Отредактируйте `config/app_config.yaml`:

```yaml
modbus:
  port: "/dev/tty.usbserial-2110"  # Или COM порт в Windows
  baudrate: 9600
  timeout: 5
  tcp_host: "192.168.1.100"  # IP КУБ-1063 для Modbus TCP
  tcp_port: 502

gateway:
  host: "0.0.0.0"
  port: 8000
  api_key: "dev-api-key"
  api_secret: "your-generated-secret"
```

### 4.3 Запуск Gateway

```bash
# Запуск всех сервисов
python tools/start_all_services.py

# Проверка статуса
python tools/check_services_status.py
```

**Ожидаемый результат:**
```bash
✅ Modbus Gateway: http://localhost:8000
✅ WebSocket Server: ws://localhost:8765
✅ Telegram Bot: активен
```

### 4.4 Тест подключения к КУБ-1063

```bash
# Прямой тест API
curl http://localhost:8000/api/health
curl http://localhost:8000/api/data/current

# Ожидаемый ответ с данными температуры, влажности, CO₂
```

## 🔗 Этап 5: Соединение компонентов

### 5.1 Настройка туннеля к ферме

**Вариант A: ngrok (простой)**
```bash
# На ферме установите ngrok
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install ngrok

# Запустите туннель (замените токен на свой)
ngrok config add-authtoken YOUR_NGROK_TOKEN
ngrok http 8000

# Скопируйте https URL (например: https://abc123.ngrok.io)
```

**Вариант B: CloudFlare Tunnel (рекомендуется)**
```bash
# Установка cloudflared
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb

# Запуск туннеля
cloudflared tunnel --url http://localhost:8000
```

### 5.2 Обновление переменных в Render

В Render Dashboard обновите переменные:
```bash
GATEWAY_URL=https://your-tunnel-url.ngrok.io  # Из ngrok/cloudflare
API_KEY=dev-api-key  # Из конфига фермы
API_SECRET=your-gateway-secret  # Из логов Gateway при запуске
```

Нажмите "Manual Deploy" для применения изменений.

## 🧪 Этап 6: Финальное тестирование

### 6.1 Проверка Web Dashboard

Откройте https://cube-rs-monitor.onrender.com и проверьте:

- ✅ **Главная страница** загружается без ошибок
- ✅ **Метрики КУБ-1063** отображают реальные данные
- ✅ **Графики** строятся с актуальными показаниями
- ✅ **Статус подключения** показывает "Подключено"
- ✅ **Автообновление** работает каждые 30 секунд

### 6.2 Проверка API endpoints

```bash
# Тест основных API
curl https://cube-rs-monitor.onrender.com/api/status
curl https://cube-rs-monitor.onrender.com/api/data/current
curl https://cube-rs-monitor.onrender.com/api/data/history?hours=1

# Тест Tailscale endpoints (если настроен)
curl https://cube-rs-monitor.onrender.com/api/tailscale/status
```

### 6.3 Проверка VPS Tunnel System

```bash
# На VPS проверьте
curl http://YOUR_VPS_IP:8080/health
curl http://YOUR_VPS_IP:8080/api/farms

# Проверьте логи
tunnel-system logs
```

### 6.4 Нагрузочное тестирование

```bash
# Простой нагрузочный тест
for i in {1..100}; do
  curl -s https://cube-rs-monitor.onrender.com/api/status > /dev/null
  echo "Request $i completed"
done
```

## 📊 Этап 7: Мониторинг и логирование

### 7.1 Настройка мониторинга Render

В Render Dashboard настройте:
- **Metrics** - отслеживание CPU, RAM, Response time
- **Health Checks** - автоматические проверки `/health`
- **Alerts** - уведомления при проблемах

### 7.2 Мониторинг VPS

```bash
# Установка мониторинга
sudo apt install htop iotop nethogs -y

# Проверка ресурсов
htop                    # CPU и RAM
sudo iotop              # Disk I/O
sudo nethogs           # Network usage

# Системные логи
sudo journalctl -u tunnel-broker -f
```

### 7.3 Настройка Telegram уведомлений

На ферме настройте Telegram bot для уведомлений:

```bash
# В config/bot_secrets.json
{
  "bot_token": "YOUR_BOT_TOKEN",
  "admin_chat_id": "YOUR_CHAT_ID"
}

# Telegram bot будет отправлять уведомления о:
# - Проблемах с КУБ-1063
# - Критических показаниях
# - Статусе системы
```

## 🎉 Готово! Система развернута

### 📋 Итоговая архитектура:

1. **🌐 Web Interface**: https://cube-rs-monitor.onrender.com
   - Dashboard КУБ-1063 с графиками
   - Tailscale управление (если настроено)
   - RBAC система доступа

2. **🖥️ VPS Tunnel System**: http://YOUR_VPS_IP
   - Tunnel Broker для P2P соединений  
   - Device Registry
   - SSL сертификат

3. **🏭 Local Farm**: Gateway + КУБ-1063
   - Modbus Gateway на :8000
   - Туннель через ngrok/cloudflare
   - Telegram уведомления

### 🔧 Команды управления:

```bash
# На VPS
tunnel-system start|stop|restart|status|logs|health

# На ферме  
python tools/start_all_services.py
python tools/stop_all_services.py
python tools/check_services_status.py

# Render
# Управление через Web Dashboard
```

### 🚨 Устранение неполадок:

**Web App не подключается к Gateway:**
- Проверьте GATEWAY_URL в Render
- Убедитесь что туннель (ngrok/cloudflare) работает
- Проверьте API_KEY и API_SECRET

**VPS Tunnel System не запускается:**  
- Проверьте: `sudo systemctl status tunnel-broker`
- Логи: `sudo journalctl -u tunnel-broker -n 50`
- Перезапуск: `tunnel-system restart`

**КУБ-1063 не отвечает:**
- Проверьте физическое подключение
- Убедитесь в правильности настроек Modbus в config/app_config.yaml
- Тест: `curl http://localhost:8000/api/health`

## ✅ Масштабный тест готов!

Система полностью развернута и готова к production использованию с полным мониторингом КУБ-1063 через веб-интерфейс в интернете.

<function_calls>
<invoke name="TodoWrite">
<parameter name="todos">[{"content": "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u0433\u043e\u0442\u043e\u0432\u043d\u043e\u0441\u0442\u044c web_app \u0434\u043b\u044f \u0434\u0435\u043f\u043b\u043e\u044f \u043d\u0430 Render", "status": "completed", "activeForm": "\u041f\u0440\u043e\u0432\u0435\u0440\u044f\u044f \u0433\u043e\u0442\u043e\u0432\u043d\u043e\u0441\u0442\u044c web_app \u0434\u043b\u044f \u0434\u0435\u043f\u043b\u043e\u044f \u043d\u0430 Render"}, {"content": "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u0433\u043e\u0442\u043e\u0432\u043d\u043e\u0441\u0442\u044c tunnel_system \u0434\u043b\u044f \u0434\u0435\u043f\u043b\u043e\u044f \u043d\u0430 VPS", "status": "completed", "activeForm": "\u041f\u0440\u043e\u0432\u0435\u0440\u044f\u044f \u0433\u043e\u0442\u043e\u0432\u043d\u043e\u0441\u0442\u044c tunnel_system \u0434\u043b\u044f \u0434\u0435\u043f\u043b\u043e\u044f \u043d\u0430 VPS"}, {"content": "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c gateway \u0438 \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435 \u041a\u0423\u0411-1063", "status": "completed", "activeForm": "\u041f\u0440\u043e\u0432\u0435\u0440\u044f\u044f gateway \u0438 \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435 \u041a\u0423\u0411-1063"}, {"content": "\u0421\u043e\u0437\u0434\u0430\u0442\u044c deployment \u0438\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u0438", "status": "completed", "activeForm": "\u0421\u043e\u0437\u0434\u0430\u044e deployment \u0438\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u0438"}]