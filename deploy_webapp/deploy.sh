#!/bin/bash

# CUBE_RS Web Application Deployment Script
# Развертывание веб-приложения администратора

set -e

echo "🌐 CUBE_RS Web Application Deployment"
echo "====================================="

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не установлен"
    exit 1
fi

# Проверка прав
if [[ $EUID -ne 0 ]]; then
    echo "⚠️  Для полной установки требуются root права"
    echo "   Запустите: sudo ./deploy.sh"
    USE_ROOT=false
else
    USE_ROOT=true
fi

# Создание директорий
echo "📁 Создание директорий..."
if [ "$USE_ROOT" = true ]; then
    mkdir -p /etc/cube_webapp/{config,secrets}
    mkdir -p /var/lib/cube_webapp/{data,uploads}
    mkdir -p /var/log/cube_webapp
    mkdir -p /opt/cube_webapp
    
    # Права доступа
    chmod 755 /etc/cube_webapp
    chmod 700 /etc/cube_webapp/secrets
    chmod 755 /var/lib/cube_webapp
    chmod 755 /var/log/cube_webapp
else
    mkdir -p ~/.cube_webapp/{config,secrets,data,logs}
fi

# Установка зависимостей
echo "📦 Установка зависимостей..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

# Копирование файлов
echo "📋 Копирование файлов веб-приложения..."
if [ "$USE_ROOT" = true ]; then
    cp -r web_app/ tools/ security/ config/ /opt/cube_webapp/
    # Создаем конфиг
    cp config/app_config.yaml /etc/cube_webapp/config/
else
    mkdir -p ~/.local/opt/cube_webapp
    cp -r web_app/ tools/ security/ config/ ~/.local/opt/cube_webapp/
    cp config/app_config.yaml ~/.cube_webapp/config/
fi

# Настройка переменных окружения
echo "⚙️  Настройка переменных окружения..."
cat > webapp.env << 'EOF'
# CUBE_RS Web Application Environment
SECRET_KEY=your-super-secret-key-change-this-in-production
API_KEY=your-api-key
API_SECRET=your-api-secret
GATEWAY_URL=http://localhost:8000
DEBUG=false
PORT=5000

# Database
DATABASE_URL=sqlite:///cube_webapp.db

# Security
SSL_CERT_PATH=/etc/cube_webapp/certs/webapp.crt
SSL_KEY_PATH=/etc/cube_webapp/certs/webapp.key

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/cube_webapp/webapp.log
EOF

if [ "$USE_ROOT" = true ]; then
    mv webapp.env /etc/cube_webapp/config/
else
    mv webapp.env ~/.cube_webapp/config/
fi

# NGINX конфигурация (если установлен)
if command -v nginx &> /dev/null && [ "$USE_ROOT" = true ]; then
    echo "🔧 Создание конфигурации Nginx..."
    cat > /etc/nginx/sites-available/cube_webapp << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/cube_webapp/certs/webapp.crt;
    ssl_certificate_key /etc/cube_webapp/certs/webapp.key;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains";

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Static files
    location /static {
        alias /opt/cube_webapp/web_app/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Security
    location ~ /\. {
        deny all;
    }
}
EOF

    echo "📝 Nginx конфиг создан: /etc/nginx/sites-available/cube_webapp"
    echo "   Для активации: ln -s /etc/nginx/sites-available/cube_webapp /etc/nginx/sites-enabled/"
fi

# Создание systemd сервиса
if [ "$USE_ROOT" = true ]; then
    echo "🔧 Создание systemd сервиса..."
    cat > /etc/systemd/system/cube-webapp.service << 'EOF'
[Unit]
Description=CUBE_RS Web Application
After=network.target
Wants=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/cube_webapp
Environment=PYTHONPATH=/opt/cube_webapp
EnvironmentFile=/etc/cube_webapp/config/webapp.env
ExecStart=/usr/bin/python3 -m gunicorn --bind 127.0.0.1:5000 --workers 4 --timeout 300 web_app.app:app
Restart=always
RestartSec=10

# Security
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/cube_webapp /var/log/cube_webapp

# Logging
StandardOutput=append:/var/log/cube_webapp/webapp.log
StandardError=append:/var/log/cube_webapp/webapp.log

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable cube-webapp
    
    echo "🎯 Сервис создан: systemctl start cube-webapp"
fi

# Создание скриптов управления
echo "📝 Создание скриптов управления..."
cat > start_webapp.sh << 'EOF'
#!/bin/bash
echo "🌐 Запуск CUBE_RS Web Application..."

# Определяем пути
if [ -d "/opt/cube_webapp" ]; then
    CUBE_PATH="/opt/cube_webapp"
    ENV_FILE="/etc/cube_webapp/config/webapp.env"
else
    CUBE_PATH="$HOME/.local/opt/cube_webapp"
    ENV_FILE="$HOME/.cube_webapp/config/webapp.env"
fi

cd "$CUBE_PATH"
export PYTHONPATH="$CUBE_PATH:$PYTHONPATH"

# Загружаем переменные окружения
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "⚠️  Файл окружения не найден: $ENV_FILE"
    echo "SECRET_KEY и другие переменные должны быть настроены"
fi

# Проверяем конфигурацию
if [ -z "$SECRET_KEY" ]; then
    echo "❌ SECRET_KEY не установлен"
    echo "   Отредактируйте: $ENV_FILE"
    exit 1
fi

# Создаем админа при первом запуске
echo "👤 Проверка административного пользователя..."
python3 -c "
import sys
sys.path.append('$CUBE_PATH')
from web_app.rbac_system import get_rbac_system

rbac = get_rbac_system()
users = rbac.get_users()
if not any(user.is_admin for user in users):
    print('Создание административного пользователя...')
    rbac.create_user(
        username='admin',
        email='admin@company.com',
        full_name='System Administrator',
        password='admin123',
        roles=['System Administrator'],
        is_admin=True
    )
    print('✅ Пользователь admin создан (пароль: admin123)')
    print('⚠️  ОБЯЗАТЕЛЬНО смените пароль после первого входа!')
"

# Запуск
echo "🚀 Запуск веб-приложения на порту 5000..."
python3 -m gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 300 web_app.app:app
EOF

chmod +x start_webapp.sh

cat > stop_webapp.sh << 'EOF'
#!/bin/bash
echo "🛑 Остановка CUBE_RS Web Application..."
pkill -f "gunicorn.*web_app.app:app" || true
pkill -f "web_app.app" || true
echo "✅ Web Application остановлено"
EOF

chmod +x stop_webapp.sh

# Создание скрипта создания пользователя
cat > create_admin.sh << 'EOF'
#!/bin/bash
echo "👤 Создание административного пользователя"

read -p "Username: " username
read -p "Email: " email
read -p "Full Name: " fullname
read -s -p "Password: " password
echo

# Определяем путь
if [ -d "/opt/cube_webapp" ]; then
    CUBE_PATH="/opt/cube_webapp"
else
    CUBE_PATH="$HOME/.local/opt/cube_webapp"
fi

cd "$CUBE_PATH"
export PYTHONPATH="$CUBE_PATH:$PYTHONPATH"

python3 -c "
import sys
from web_app.rbac_system import get_rbac_system

rbac = get_rbac_system()
user_id = rbac.create_user(
    username='$username',
    email='$email',
    full_name='$fullname',
    password='$password',
    roles=['System Administrator'],
    is_admin=True
)
print(f'✅ Пользователь {username} создан с ID: {user_id}')
"
EOF

chmod +x create_admin.sh

# Проверка установки
echo "🔍 Проверка установки..."
python3 -c "
import sys
try:
    import flask
    import werkzeug
    import gunicorn
    print('✅ Все зависимости установлены')
except ImportError as e:
    print(f'❌ Ошибка импорта: {e}')
    sys.exit(1)
"

echo ""
echo "✅ Установка веб-приложения завершена!"
echo ""
echo "📋 Следующие шаги:"
echo "1. Отредактируйте переменные окружения:"
if [ "$USE_ROOT" = true ]; then
    echo "   nano /etc/cube_webapp/config/webapp.env"
else
    echo "   nano ~/.cube_webapp/config/webapp.env"
fi
echo "2. Установите SECRET_KEY, API_KEY, API_SECRET"
echo "3. Запустите веб-приложение:"
if [ "$USE_ROOT" = true ]; then
    echo "   systemctl start cube-webapp"
    echo "   systemctl status cube-webapp"
else
    echo "   ./start_webapp.sh"
fi
echo "4. Откройте в браузере: http://localhost:5000"
echo "5. Войдите как admin/admin123 и смените пароль"
echo ""
echo "🔧 Управление:"
echo "   ./start_webapp.sh    - запуск"
echo "   ./stop_webapp.sh     - остановка"
echo "   ./create_admin.sh    - создание админа"
if [ "$USE_ROOT" = true ]; then
    echo "   systemctl status cube-webapp  - статус"
    echo "   journalctl -u cube-webapp -f  - логи"
fi