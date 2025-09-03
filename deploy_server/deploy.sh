#!/bin/bash

# CUBE_RS Server Deployment Script  
# Развертывание серверного приложения (бэкенд API)

set -e

echo "🖥️  CUBE_RS Server Application Deployment"
echo "========================================"

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

# Создание пользователя сервиса
if [ "$USE_ROOT" = true ]; then
    if ! id "cube" &>/dev/null; then
        echo "👤 Создание пользователя cube..."
        useradd -r -s /bin/false -d /opt/cube_server cube
    fi
fi

# Создание директорий
echo "📁 Создание системных директорий..."
if [ "$USE_ROOT" = true ]; then
    mkdir -p /etc/cube_server/{config,secrets,certs}
    mkdir -p /var/lib/cube_server/{data,uploads,backups}
    mkdir -p /var/log/cube_server
    mkdir -p /opt/cube_server
    
    # Права доступа
    chown -R cube:cube /etc/cube_server /var/lib/cube_server /var/log/cube_server /opt/cube_server
    chmod 755 /etc/cube_server
    chmod 700 /etc/cube_server/secrets
    chmod 700 /etc/cube_server/certs
    chmod 755 /var/lib/cube_server
    chmod 755 /var/log/cube_server
else
    mkdir -p ~/.cube_server/{config,secrets,data,logs,certs}
fi

# Установка зависимостей
echo "📦 Установка зависимостей..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

# Копирование файлов
echo "📋 Копирование файлов сервера..."
if [ "$USE_ROOT" = true ]; then
    cp -r server_app/ monitoring/ security/ tools/ config/ /opt/cube_server/
    chown -R cube:cube /opt/cube_server
else
    mkdir -p ~/.local/opt/cube_server
    cp -r server_app/ monitoring/ security/ tools/ config/ ~/.local/opt/cube_server/
fi

# Создание API приложения
echo "🔧 Создание FastAPI приложения..."
mkdir -p server_app/{api,models,services,core}

cat > server_app/main.py << 'EOF'
#!/usr/bin/env python3
"""
CUBE_RS Server Application
FastAPI backend для системы CUBE_RS
"""

import os
import sys
import logging
from pathlib import Path

# Добавляем пути к модулям
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

# Импорты модулей CUBE_RS
from security.security_monitor import get_security_monitor
from monitoring.network_security_monitor import get_network_monitor

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/cube_server/server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Менеджер жизненного цикла приложения
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Запуск CUBE_RS Server Application")
    
    # Инициализация мониторинга безопасности
    try:
        security_monitor = get_security_monitor()
        network_monitor = get_network_monitor()
        logger.info("Мониторинг безопасности инициализирован")
    except Exception as e:
        logger.error(f"Ошибка инициализации мониторинга: {e}")
    
    yield
    
    # Shutdown  
    logger.info("Остановка CUBE_RS Server Application")

# Создание FastAPI приложения
app = FastAPI(
    title="CUBE_RS Server API",
    description="Backend API для системы мониторинга КУБ-1063",
    version="1.0.0",
    lifespan=lifespan
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене ограничить
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["*"]  # В продакшене ограничить
)

# Обработчик ошибок
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Необработанная ошибка: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# Базовые маршруты
@app.get("/")
async def root():
    return {
        "message": "CUBE_RS Server API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": "2024-01-01T00:00:00Z"
    }

# API маршруты устройств
@app.post("/api/v1/device-registry/register")
async def register_device(request: Request):
    """Регистрация нового устройства"""
    try:
        data = await request.json()
        
        # Здесь будет логика регистрации
        return {
            "status": "success",
            "request_id": "req_123456",
            "message": "Device registration request created"
        }
    except Exception as e:
        logger.error(f"Ошибка регистрации устройства: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/device-registry/activate")  
async def activate_device(request: Request):
    """Активация устройства в поле"""
    try:
        data = await request.json()
        
        # Здесь будет логика активации
        return {
            "status": "success", 
            "device_serial": "device-001",
            "registration_request_id": "req_123456",
            "next_step": "pending_approval"
        }
    except Exception as e:
        logger.error(f"Ошибка активации устройства: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/v1/device-registry/status/{request_id}")
async def get_registration_status(request_id: str):
    """Получение статуса регистрации"""
    return {
        "request_id": request_id,
        "status": "pending",
        "device_id": None
    }

# API мониторинга
@app.get("/api/v1/monitoring/stats")
async def get_monitoring_stats():
    """Статистика мониторинга"""
    try:
        security_monitor = get_security_monitor()
        stats = security_monitor.get_security_stats()
        return stats
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        raise HTTPException(status_code=500, detail="Failed to get stats")

@app.get("/api/v1/monitoring/alerts")
async def get_active_alerts():
    """Активные алерты безопасности"""
    return {
        "alerts": [],
        "count": 0
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
EOF

# Настройка переменных окружения
echo "⚙️  Настройка переменных окружения..."
cat > server.env << 'EOF'
# CUBE_RS Server Environment
SECRET_KEY=your-server-secret-key-change-in-production
DEBUG=false
PORT=8000
HOST=0.0.0.0

# Database
DATABASE_URL=sqlite:///cube_server.db
# Для PostgreSQL: DATABASE_URL=postgresql://user:pass@localhost/cube_server

# Redis (для кэширования)
REDIS_URL=redis://localhost:6379/0

# Security
CERTIFICATE_PINNING_ENABLED=true
MUTUAL_TLS_ENABLED=true
RATE_LIMITING_ENABLED=true

# Monitoring
SECURITY_MONITORING_ENABLED=true
NETWORK_MONITORING_ENABLED=true
PACKET_CAPTURE_ENABLED=false

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/cube_server/server.log

# API Keys
API_KEY_EXPIRY_HOURS=24
MAX_DEVICES_PER_BATCH=1000

# Email notifications
SMTP_SERVER=localhost
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
NOTIFICATION_EMAIL=admin@company.com
EOF

if [ "$USE_ROOT" = true ]; then
    mv server.env /etc/cube_server/config/
    chown cube:cube /etc/cube_server/config/server.env
    chmod 600 /etc/cube_server/config/server.env
else
    mv server.env ~/.cube_server/config/
fi

# Создание systemd сервиса
if [ "$USE_ROOT" = true ]; then
    echo "🔧 Создание systemd сервиса..."
    cat > /etc/systemd/system/cube-server.service << 'EOF'
[Unit]
Description=CUBE_RS Server Application
After=network.target
Wants=network.target

[Service]
Type=simple
User=cube
Group=cube
WorkingDirectory=/opt/cube_server
Environment=PYTHONPATH=/opt/cube_server
EnvironmentFile=/etc/cube_server/config/server.env
ExecStart=/usr/bin/python3 -m uvicorn server_app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

# Security
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/cube_server /var/log/cube_server

# Logging
StandardOutput=append:/var/log/cube_server/server.log
StandardError=append:/var/log/cube_server/server.log

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable cube-server
    
    echo "🎯 Сервис создан: systemctl start cube-server"
fi

# Создание скриптов управления
echo "📝 Создание скриптов управления..."
cat > start_server.sh << 'EOF'
#!/bin/bash
echo "🖥️  Запуск CUBE_RS Server..."

# Определяем пути
if [ -d "/opt/cube_server" ]; then
    CUBE_PATH="/opt/cube_server"
    ENV_FILE="/etc/cube_server/config/server.env"
else
    CUBE_PATH="$HOME/.local/opt/cube_server"  
    ENV_FILE="$HOME/.cube_server/config/server.env"
fi

cd "$CUBE_PATH"
export PYTHONPATH="$CUBE_PATH:$PYTHONPATH"

# Загружаем переменные окружения
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

echo "🚀 Запуск FastAPI сервера на порту 8000..."
python3 -m uvicorn server_app.main:app --host 0.0.0.0 --port 8000 --workers 2
EOF

chmod +x start_server.sh

cat > stop_server.sh << 'EOF'  
#!/bin/bash
echo "🛑 Остановка CUBE_RS Server..."
pkill -f "uvicorn.*server_app.main:app" || true
pkill -f "cube_server" || true
echo "✅ Server остановлен"
EOF

chmod +x stop_server.sh

# Создание скрипта мониторинга
cat > start_monitoring.sh << 'EOF'
#!/bin/bash
echo "🔒 Запуск мониторинга безопасности..."

# Определяем путь
if [ -d "/opt/cube_server" ]; then
    CUBE_PATH="/opt/cube_server"
else
    CUBE_PATH="$HOME/.local/opt/cube_server"
fi

cd "$CUBE_PATH"
export PYTHONPATH="$CUBE_PATH:$PYTHONPATH"

# Запуск мониторинга безопасности
python3 monitoring/security_monitor.py --daemon &
SECURITY_PID=$!

# Запуск сетевого мониторинга  
python3 monitoring/network_security_monitor.py --daemon &
NETWORK_PID=$!

echo "✅ Мониторинг запущен:"
echo "   Security Monitor PID: $SECURITY_PID"  
echo "   Network Monitor PID: $NETWORK_PID"

# Сохраняем PID для остановки
echo "$SECURITY_PID" > /tmp/cube_security_monitor.pid
echo "$NETWORK_PID" > /tmp/cube_network_monitor.pid
EOF

chmod +x start_monitoring.sh

# Проверка установки
echo "🔍 Проверка установки..."
python3 -c "
import sys
try:
    import fastapi
    import uvicorn
    import pydantic
    print('✅ FastAPI и зависимости установлены')
except ImportError as e:
    print(f'❌ Ошибка импорта: {e}')
    sys.exit(1)
"

# Создание SSL сертификатов (самоподписанные для разработки)
if [ "$USE_ROOT" = true ]; then
    echo "🔐 Создание SSL сертификатов..."
    openssl req -x509 -newkey rsa:4096 -keyout /etc/cube_server/certs/server.key \
        -out /etc/cube_server/certs/server.crt -days 365 -nodes \
        -subj "/C=RU/ST=Moscow/L=Moscow/O=CUBE_RS/OU=Server/CN=localhost" 2>/dev/null || {
        echo "⚠️  OpenSSL не найден, пропуск создания сертификатов"
    }
fi

echo ""
echo "✅ Установка сервера завершена!"
echo ""
echo "📋 Следующие шаги:"
echo "1. Отредактируйте переменные окружения:"
if [ "$USE_ROOT" = true ]; then
    echo "   nano /etc/cube_server/config/server.env"
else
    echo "   nano ~/.cube_server/config/server.env"
fi
echo "2. Установите SECRET_KEY и другие параметры"
echo "3. Запустите сервер:"
if [ "$USE_ROOT" = true ]; then
    echo "   systemctl start cube-server"
    echo "   systemctl status cube-server"
else
    echo "   ./start_server.sh"
fi
echo "4. API будет доступен на: http://localhost:8000"
echo "5. Документация API: http://localhost:8000/docs"
echo ""
echo "🔧 Управление:"
echo "   ./start_server.sh      - запуск сервера"
echo "   ./stop_server.sh       - остановка"
echo "   ./start_monitoring.sh  - мониторинг безопасности"
if [ "$USE_ROOT" = true ]; then
    echo "   systemctl status cube-server  - статус"
    echo "   journalctl -u cube-server -f  - логи"
fi