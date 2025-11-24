# 🌐 SERVER - Tunnel Broker для EDGE системы

Серверная часть распределенной EDGE системы. Обеспечивает P2P туннелирование между пользователями и EDGE устройствами через WebRTC.

## 🏗️ Архитектура

```
📱 APP (пользователь) ←--HTTP/WebSocket--→ 🌐 SERVER (брокер) ←--P2P--→ 🏭 EDGE (устройство)
                                                  ↓
                                            WebRTC координация
                                          (трафик идет напрямую)
```

## 📦 Компоненты

### 🎛️ **Tunnel Broker** (`tunnel_broker.py`)
- Центральный координатор P2P соединений
- Регистрация и аутентификация пользователей
- Управление EDGE устройствами
- WebRTC offer/answer обмен
- SQLite база данных

### 🚀 **Resilient Tunnel Broker** (`resilient_tunnel_broker.py`)
- Улучшенная версия с автоочисткой
- Мониторинг состояния соединений
- Автоматическое восстановление
- Расширенная диагностика

### 📱 **Mobile Web App** (`mobile_app.py`)
- Веб-интерфейс для пользователей
- Регистрация/авторизация
- Выбор и подключение к EDGE устройствам
- P2P WebRTC клиент
- Отображение данных КУБ устройств

### 🎨 **Templates** (`tunnel_system/templates/`)
- HTML шаблоны веб-интерфейса
- Responsive дизайн
- JavaScript для WebRTC

## 🚀 Быстрый запуск

### Предварительные требования
```bash
sudo apt update
sudo apt install python3 python3-pip sqlite3 nginx
```

### Установка зависимостей
```bash
cd SERVER
pip3 install -r requirements.txt
```

### Запуск в development режиме
```bash
# Tunnel Broker (порт 8080)
python3 tunnel_broker.py --host 0.0.0.0 --port 8080

# Mobile Web App (порт 5000) 
python3 mobile_app.py --broker http://localhost:8080 --host 0.0.0.0 --port 5000
```

### Проверка работы
```bash
curl http://localhost:8080/health
curl http://localhost:5000
```

## 🐳 Production развертывание

### Docker (рекомендуемый)
```bash
# Сборка образов
docker build -t edge-tunnel-broker -f Dockerfile.broker .
docker build -t edge-mobile-app -f Dockerfile.webapp .

# Запуск через docker-compose
docker-compose up -d
```

### Systemd сервисы
```bash
# Копируем unit файлы
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload

# Запускаем сервисы
sudo systemctl enable --now tunnel-broker
sudo systemctl enable --now mobile-app
```

### Nginx прокси
```bash
# Копируем конфиг
sudo cp nginx/tunnel-broker.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/tunnel-broker.conf /etc/nginx/sites-enabled/
sudo systemctl reload nginx
```

## 🔧 Конфигурация

### Переменные окружения

#### Tunnel Broker
```bash
export BROKER_HOST="0.0.0.0"          # Хост сервера
export BROKER_PORT="8080"             # Порт Tunnel Broker
export DATABASE_PATH="tunnel_broker.db" # Путь к базе данных
export LOG_LEVEL="INFO"               # Уровень логирования
export WEBSOCKET_PORT="8081"          # WebSocket порт
```

#### Mobile Web App
```bash
export WEBAPP_HOST="0.0.0.0"          # Хост веб-приложения
export WEBAPP_PORT="5000"             # Порт веб-приложения
export BROKER_URL="http://localhost:8080" # URL Tunnel Broker
export SECRET_KEY="your-secret-key"    # Секретный ключ Flask
```

### Конфигурационные файлы
- `config/server.yaml` - основная конфигурация
- `config/nginx.conf` - настройки Nginx
- `config/ssl.conf` - SSL сертификаты

## 📊 API Reference

### Tunnel Broker API (port 8080)

#### Пользователи
```http
POST /api/register        # Регистрация пользователя
POST /api/login          # Авторизация пользователя
GET  /api/farms/{user_id} # Список ферм пользователя
```

#### EDGE устройства
```http
POST /api/farm/register   # Регистрация EDGE устройства
POST /api/farm/heartbeat # Heartbeat от EDGE
GET  /api/farm/{farm_id}/status # Статус EDGE устройства
```

#### P2P соединения
```http
POST /api/connect/request # Запрос на P2P соединение
POST /api/connect/answer # Ответ EDGE на соединение
GET  /api/connect/status/{request_id} # Статус запроса
```

### Mobile Web App (port 5000)
```http
GET  /                   # Главная страница
GET  /login             # Страница входа
GET  /register          # Страница регистрации
GET  /dashboard         # Дашборд пользователя
```

## 🔒 Безопасность

### Аутентификация
- SHA256 хеширование паролей
- Сессионные токены
- CSRF protection

### Network Security
- HTTPS обязателен в production
- WebRTC DTLS шифрование
- Rate limiting для API
- CORS настройки

### Database Security
- Prepared statements (защита от SQL injection)
- Регулярные бэкапы
- Encryption at rest

## 📈 Мониторинг

### Логирование
```bash
# Логи Tunnel Broker
tail -f logs/tunnel-broker.log

# Логи Web App
tail -f logs/mobile-app.log

# Системные логи
sudo journalctl -u tunnel-broker -f
```

### Метрики
- Количество активных P2P соединений
- Регистрированные EDGE устройства
- Пользователи онлайн
- Скорость обработки запросов

### Health Checks
```bash
# Проверка Tunnel Broker
curl http://localhost:8080/health

# Проверка веб-приложения
curl http://localhost:5000/health
```

## 🔧 Администрирование

### Управление пользователями
```bash
# Создать администратора
python3 admin_cli.py create-admin --username admin --email admin@example.com

# Список пользователей
python3 admin_cli.py list-users

# Заблокировать пользователя
python3 admin_cli.py block-user --user-id 123
```

### Управление EDGE устройствами
```bash
# Список EDGE устройств
python3 admin_cli.py list-farms

# Статистика соединений
python3 admin_cli.py connection-stats
```

### Бэкап и восстановление
```bash
# Создать бэкап
python3 backup_cli.py create --output backup_$(date +%Y%m%d).sql

# Восстановить из бэкапа
python3 backup_cli.py restore --input backup_20231207.sql
```

## 🚦 Troubleshooting

### Частые проблемы

#### P2P соединения не устанавливаются
```bash
# Проверить WebSocket соединение
wscat -c ws://localhost:8081

# Проверить логи координации
grep "WebRTC" logs/tunnel-broker.log
```

#### EDGE устройства не подключаются
```bash
# Проверить heartbeat
grep "heartbeat" logs/tunnel-broker.log

# Проверить регистрацию
curl http://localhost:8080/api/farm/list
```

#### Высокая нагрузка
```bash
# Мониторинг ресурсов
htop
iotop
netstat -tulnp
```

## 📞 Поддержка

### Контакты
- 📧 Email: support@edge-system.com
- 🐛 Issues: GitHub Issues
- 📚 Wiki: GitHub Wiki

### Полезные ссылки
- [EDGE Documentation](../docs/edge/README.md)
- [APP Documentation](../APP/docs/)
- [Architecture Overview](../docs/ARCHITECTURE.md)
- [Deployment Guide](docs/DEPLOYMENT.md)

---

**SERVER готов к продакшн развертыванию для обеспечения P2P туннелирования в распределенной EDGE системе! 🚀**
