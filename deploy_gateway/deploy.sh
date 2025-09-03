#!/bin/bash

# CUBE_RS Gateway Deployment Script
# Развертывание на устройствах gateway

set -e

echo "🚀 CUBE_RS Gateway Deployment"
echo "================================"

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не установлен"
    exit 1
fi

# Проверка прав root (для системных директорий)
if [[ $EUID -ne 0 ]]; then
    echo "⚠️  Для полной установки требуются root права"
    echo "   Запустите: sudo ./deploy.sh"
    USE_ROOT=false
else
    USE_ROOT=true
fi

# Создание директорий
echo "📁 Создание системных директорий..."
if [ "$USE_ROOT" = true ]; then
    mkdir -p /etc/cube_gateway/{certs,config}
    mkdir -p /var/lib/cube_gateway
    mkdir -p /var/log/cube_gateway
    mkdir -p /opt/cube_gateway
    
    # Права доступа
    chmod 755 /etc/cube_gateway
    chmod 700 /etc/cube_gateway/certs
    chmod 600 /etc/cube_gateway/config
    chmod 755 /var/lib/cube_gateway
    chmod 755 /var/log/cube_gateway
else
    mkdir -p ~/.cube_gateway/{certs,config,lib,logs}
fi

# Установка зависимостей
echo "📦 Установка Python зависимостей..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

# Копирование файлов
echo "📋 Копирование файлов gateway..."
cp -r gateway/ modbus/ security/ monitoring/ config/ tools/ /opt/cube_gateway/ 2>/dev/null || {
    echo "⚠️  Копирование в /opt/ не удалось, используем локальную директорию"
    mkdir -p ~/.local/opt/cube_gateway
    cp -r gateway/ modbus/ security/ monitoring/ config/ tools/ ~/.local/opt/cube_gateway/
}

# Конфигурация
echo "⚙️  Настройка конфигурации..."
if [ -f "config/gateway_config.yaml" ]; then
    if [ "$USE_ROOT" = true ]; then
        cp config/gateway_config.yaml /etc/cube_gateway/config/
    else
        cp config/gateway_config.yaml ~/.cube_gateway/config/
    fi
fi

# Создание systemd сервиса (только с root)
if [ "$USE_ROOT" = true ]; then
    echo "🔧 Создание systemd сервиса..."
    cat > /etc/systemd/system/cube-gateway.service << 'EOF'
[Unit]
Description=CUBE_RS Gateway Service
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/cube_gateway
ExecStart=/usr/bin/python3 /opt/cube_gateway/gateway/auto_registration_client.py --daemon
Restart=always
RestartSec=10
Environment=PYTHONPATH=/opt/cube_gateway

# Logging
StandardOutput=append:/var/log/cube_gateway/gateway.log
StandardError=append:/var/log/cube_gateway/gateway.log

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable cube-gateway
    
    echo "🎯 Сервис создан: systemctl start cube-gateway"
fi

# Создание скриптов управления
echo "📝 Создание скриптов управления..."
cat > start_gateway.sh << 'EOF'
#!/bin/bash
echo "🚀 Запуск CUBE_RS Gateway..."

# Определяем пути
if [ -d "/opt/cube_gateway" ]; then
    CUBE_PATH="/opt/cube_gateway"
else
    CUBE_PATH="$HOME/.local/opt/cube_gateway"
fi

cd "$CUBE_PATH"
export PYTHONPATH="$CUBE_PATH:$PYTHONPATH"

# Проверяем конфигурацию
if [ ! -f "/etc/cube_gateway/registration.conf" ] && [ ! -f "$HOME/.cube_gateway/registration.conf" ]; then
    echo "⚠️  Конфигурация не найдена, создаем базовую..."
    
    if [ -d "/etc/cube_gateway" ]; then
        CONFIG_DIR="/etc/cube_gateway"
    else
        CONFIG_DIR="$HOME/.cube_gateway"
        mkdir -p "$CONFIG_DIR"
    fi
    
    cat > "$CONFIG_DIR/registration.conf" << 'CONFIG_EOF'
{
  "server_url": "https://api.company.com",
  "auth_key": "PASTE_YOUR_AUTH_KEY_HERE",
  "activation_token": "PASTE_ACTIVATION_TOKEN_HERE",
  "device_type": "gateway",
  "log_level": "INFO",
  "auto_retry": true,
  "verify_ssl": true
}
CONFIG_EOF
    
    echo "📝 Конфигурация создана: $CONFIG_DIR/registration.conf"
    echo "📝 Отредактируйте файл конфигурации и перезапустите"
    exit 1
fi

# Запуск
python3 gateway/auto_registration_client.py --daemon
EOF

chmod +x start_gateway.sh

cat > stop_gateway.sh << 'EOF'
#!/bin/bash
echo "🛑 Остановка CUBE_RS Gateway..."
pkill -f "auto_registration_client.py"
echo "✅ Gateway остановлен"
EOF

chmod +x stop_gateway.sh

# Проверка установки
echo "🔍 Проверка установки..."

# Тест импортов
python3 -c "
import sys
try:
    import pymodbus
    import requests
    import cryptography
    print('✅ Все зависимости установлены')
except ImportError as e:
    print(f'❌ Ошибка импорта: {e}')
    sys.exit(1)
"

echo ""
echo "✅ Установка gateway завершена!"
echo ""
echo "📋 Следующие шаги:"
echo "1. Отредактируйте конфигурацию:"
if [ "$USE_ROOT" = true ]; then
    echo "   nano /etc/cube_gateway/registration.conf"
else
    echo "   nano ~/.cube_gateway/registration.conf"
fi
echo "2. Вставьте auth_key и activation_token"
echo "3. Запустите gateway:"
if [ "$USE_ROOT" = true ]; then
    echo "   systemctl start cube-gateway"
    echo "   systemctl status cube-gateway"
else
    echo "   ./start_gateway.sh"
fi
echo ""
echo "🔧 Управление:"
echo "   ./start_gateway.sh  - запуск"
echo "   ./stop_gateway.sh   - остановка"
if [ "$USE_ROOT" = true ]; then
    echo "   systemctl status cube-gateway  - статус сервиса"
    echo "   journalctl -u cube-gateway -f  - логи"
fi