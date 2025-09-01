# 🚀 Tunnel System - Deployment Package

## 📦 Готовый deployment пакет

Этот пакет содержит все необходимое для развертывания Tunnel System на production сервере с автоматической установкой, настройкой сервисов и watchdog.

## 🛠️ Что включено

### ✅ Основные компоненты:
- **Tunnel Broker Server** с watchdog
- **Systemd сервис** с автозапуском
- **Nginx reverse proxy** 
- **Автоматический установщик**
- **Скрипты управления**

### ✅ Функции безопасности:
- **Изолированный пользователь** tunnel-system
- **Ограничение прав доступа**
- **Firewall настройка**
- **Health check мониторинг**

### ✅ Мониторинг и надежность:
- **Watchdog** с автоперезапуском при сбоях
- **Ограничение частоты** перезапусков (10/час)
- **Детальное логирование**
- **HTTP health checks**

## 🚀 Установка на сервер

### Шаг 1: Подготовка
```bash
# Скачайте всю папку tunnel_system/ на ваш сервер
scp -r tunnel_system/ root@your-server:/tmp/

# Подключитесь к серверу
ssh root@your-server
cd /tmp/tunnel_system/
```

### Шаг 2: Автоматическая установка
```bash
# Сделайте скрипт исполняемым
chmod +x deploy.sh

# Запустите автоустановку (с правами root)
sudo ./deploy.sh
```

### Шаг 3: Готово! 🎉
Установщик автоматически:
- ✅ Установит все зависимости
- ✅ Создаст пользователя и директории
- ✅ Настроит systemd сервис
- ✅ Сконфигурирует nginx
- ✅ Настроит firewall
- ✅ Запустит все сервисы

## 🎛️ Управление сервисом

После установки доступны команды:

```bash
# Управление сервисом
tunnel-system start      # Запуск
tunnel-system stop       # Остановка  
tunnel-system restart    # Перезапуск
tunnel-system status     # Статус сервисов
tunnel-system logs       # Просмотр логов в реальном времени
tunnel-system health     # Проверка API
```

## 📊 Мониторинг

### Логи сервиса:
```bash
# Логи в реальном времени
tunnel-system logs

# Системные логи
sudo journalctl -u tunnel-broker -f

# Файлы логов
tail -f /var/log/tunnel-system/tunnel-broker.log
```

### Статус сервисов:
```bash
# Статус всех компонентов
tunnel-system status

# Только tunnel broker
sudo systemctl status tunnel-broker

# Nginx
sudo systemctl status nginx
```

### Health check:
```bash
# Проверка API
tunnel-system health

# Ручная проверка
curl http://localhost:8080/health
```

## 🌍 Доступ к сервису

После установки сервис доступен по адресам:

- **Основной API:** `http://your-server-ip`
- **Прямой API:** `http://your-server-ip:8080`  
- **WebSocket:** `ws://your-server-ip:8081`

## ⚙️ Конфигурация

Основной конфиг: `/opt/tunnel-system/config.ini`

```ini
[broker]
host = 0.0.0.0
port = 8080
websocket_port = 8081

[database]  
path = /opt/tunnel-system/data/tunnel_broker.db

[logging]
level = INFO
log_dir = /var/log/tunnel-system

[watchdog]
enabled = true
check_interval = 30
restart_delay = 5
max_restarts_per_hour = 10
```

После изменения конфига:
```bash
tunnel-system restart
```

## 🛡️ Безопасность

### Пользователь сервиса:
- Создается изолированный пользователь `tunnel-system`
- Нет shell доступа (`/bin/false`)
- Ограниченные права на файлы

### Файрвол:
Автоматически открываются порты:
- `22` (SSH)
- `80` (HTTP)  
- `443` (HTTPS)
- `8080` (API)

### SSL/HTTPS:
Для production рекомендуется настроить SSL:

```bash
# Установка certbot
sudo apt install certbot python3-certbot-nginx

# Получение сертификата
sudo certbot --nginx -d your-domain.com

# Автообновление
sudo crontab -e
# Добавить: 0 12 * * * /usr/bin/certbot renew --quiet
```

## 🔧 Watchdog функции

### Автоматический мониторинг:
- ✅ Проверка процесса каждые 30 секунд
- ✅ HTTP health check на `/health`
- ✅ Автоперезапуск при сбое
- ✅ Ограничение на 10 перезапусков/час

### Поведение при сбоях:
1. **Обнаружение сбоя** → логирование
2. **Graceful stop** (SIGTERM + 10сек)
3. **Force kill** если не остановился
4. **Задержка 5 секунд** 
5. **Новый запуск** → учет в статистике

## 🗂️ Структура файлов

```
/opt/tunnel-system/           # Основная директория
├── tunnel_broker.py          # Основной сервер
├── tunnel_broker_service.py  # Service wrapper с watchdog  
├── farm_client.py            # Клиент фермы
├── mobile_app.py             # Мобильное приложение
├── config.ini                # Конфигурация
├── requirements.txt          # Python зависимости
├── venv/                     # Виртуальное окружение
├── data/                     # База данных
│   └── tunnel_broker.db      # SQLite БД
├── logs/                     # Локальные логи
└── manage.sh                 # Скрипт управления

/var/log/tunnel-system/       # Системные логи
└── tunnel-broker.log         # Основной лог файл

/etc/systemd/system/          # Systemd
└── tunnel-broker.service     # Сервис

/etc/nginx/sites-available/   # Nginx
└── tunnel-system             # Конфигурация прокси
```

## 🐛 Решение проблем

### Сервис не запускается:
```bash
# Проверить статус
sudo systemctl status tunnel-broker

# Проверить логи  
sudo journalctl -u tunnel-broker -n 50

# Проверить конфиг
python3 -c "import configparser; c=configparser.ConfigParser(); c.read('/opt/tunnel-system/config.ini'); print('OK')"
```

### Проблемы с портами:
```bash
# Проверить занятые порты
sudo ss -tlnp | grep -E ":80|:8080"

# Проверить firewall
sudo ufw status  # Ubuntu
sudo firewall-cmd --list-all  # CentOS
```

### Проблемы с базой данных:
```bash
# Проверить права на БД
ls -la /opt/tunnel-system/data/

# Пересоздать БД
sudo rm /opt/tunnel-system/data/tunnel_broker.db
tunnel-system restart
```

### Перезапуски watchdog:
```bash
# Статистика перезапусков в логах
grep "перезапуск" /var/log/tunnel-system/tunnel-broker.log

# Отключить watchdog временно
sudo nano /opt/tunnel-system/config.ini
# [watchdog] enabled = false
tunnel-system restart
```

## 🎯 Production рекомендации

### 1. Мониторинг:
- Настройте внешний мониторинг (Zabbix, Nagios)
- Добавьте алерты на недоступность API
- Мониторьте использование диска и памяти

### 2. Backup:
```bash
# Бэкап БД
cp /opt/tunnel-system/data/tunnel_broker.db /backup/
# Автоматический бэкап через cron
```

### 3. Логротация:
```bash
# /etc/logrotate.d/tunnel-system
/var/log/tunnel-system/*.log {
    daily
    missingok
    rotate 30
    compress
    notifempty
    copytruncate
}
```

## ✅ Готово к использованию!

Пакет протестирован и готов для production развертывания. 
Весь процесс установки автоматизирован и занимает 2-3 минуты.

🚀 **Просто запустите `sudo ./deploy.sh` и система готова!**