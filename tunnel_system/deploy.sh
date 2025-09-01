#!/bin/bash
# 🚀 Автоматический установщик Tunnel System
# Использование: chmod +x deploy.sh && sudo ./deploy.sh

set -e  # Остановка при ошибках

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Логирование
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка прав root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "Этот скрипт должен быть запущен с правами root (sudo)"
        exit 1
    fi
}

# Определение дистрибутива
detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$NAME
        VERSION=$VERSION_ID
    else
        log_error "Не удается определить операционную систему"
        exit 1
    fi
    
    log_info "Обнаружена ОС: $OS $VERSION"
}

# Установка зависимостей
install_dependencies() {
    log_info "Установка зависимостей системы..."
    
    if [[ "$OS" == *"Ubuntu"* ]] || [[ "$OS" == *"Debian"* ]]; then
        apt-get update -y
        apt-get install -y python3 python3-pip python3-venv nginx supervisor ufw curl wget git
    elif [[ "$OS" == *"CentOS"* ]] || [[ "$OS" == *"Red Hat"* ]]; then
        yum update -y
        yum install -y python3 python3-pip nginx supervisor firewalld curl wget git
    elif [[ "$OS" == *"Fedora"* ]]; then
        dnf update -y
        dnf install -y python3 python3-pip nginx supervisor firewalld curl wget git
    else
        log_warning "Неизвестный дистрибутив, попытка установки через apt-get..."
        apt-get update -y
        apt-get install -y python3 python3-pip python3-venv nginx supervisor ufw curl wget git
    fi
    
    log_success "Системные зависимости установлены"
}

# Создание пользователя для сервиса
create_service_user() {
    log_info "Создание пользователя tunnel-system..."
    
    if ! id "tunnel-system" &>/dev/null; then
        useradd --system --shell /bin/false --home /opt/tunnel-system tunnel-system
        log_success "Пользователь tunnel-system создан"
    else
        log_info "Пользователь tunnel-system уже существует"
    fi
}

# Настройка директорий
setup_directories() {
    log_info "Настройка директорий..."
    
    # Создаем основную директорию
    mkdir -p /opt/tunnel-system
    mkdir -p /opt/tunnel-system/logs
    mkdir -p /opt/tunnel-system/data
    mkdir -p /var/log/tunnel-system
    
    # Копируем файлы
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    log_info "Копирование файлов из $SCRIPT_DIR в /opt/tunnel-system/"
    
    cp "$SCRIPT_DIR"/*.py /opt/tunnel-system/
    cp "$SCRIPT_DIR"/requirements.txt /opt/tunnel-system/
    cp "$SCRIPT_DIR"/README.md /opt/tunnel-system/
    
    # Копируем шаблоны если есть
    if [[ -d "$SCRIPT_DIR/templates" ]]; then
        cp -r "$SCRIPT_DIR"/templates /opt/tunnel-system/
    fi
    
    # Устанавливаем права
    chown -R tunnel-system:tunnel-system /opt/tunnel-system
    chown -R tunnel-system:tunnel-system /var/log/tunnel-system
    chmod +x /opt/tunnel-system/*.py
    
    log_success "Директории настроены"
}

# Создание виртуального окружения и установка Python зависимостей
setup_python_env() {
    log_info "Создание виртуального окружения Python..."
    
    cd /opt/tunnel-system
    
    # Создаем venv
    python3 -m venv venv
    source venv/bin/activate
    
    # Обновляем pip
    pip install --upgrade pip
    
    # Устанавливаем зависимости
    pip install -r requirements.txt
    pip install watchdog psutil  # Добавляем watchdog
    
    # Устанавливаем права на venv
    chown -R tunnel-system:tunnel-system venv
    
    log_success "Python окружение настроено"
}

# Создание конфигурационного файла
create_config() {
    log_info "Создание конфигурационного файла..."
    
    cat > /opt/tunnel-system/config.ini << EOF
[broker]
host = 0.0.0.0
port = 8080
websocket_port = 8081

[database]
path = /opt/tunnel-system/data/tunnel_broker.db

[logging]
level = INFO
log_dir = /var/log/tunnel-system

[security]
session_timeout = 3600
max_failed_attempts = 5
ban_duration = 300

[watchdog]
enabled = true
check_interval = 30
restart_delay = 5
max_restarts_per_hour = 10
EOF

    chown tunnel-system:tunnel-system /opt/tunnel-system/config.ini
    log_success "Конфигурационный файл создан"
}

# Создание systemd сервиса
create_systemd_service() {
    log_info "Создание systemd сервиса..."
    
    cat > /etc/systemd/system/tunnel-broker.service << EOF
[Unit]
Description=Tunnel System Broker
After=network.target
Wants=network.target

[Service]
Type=simple
User=tunnel-system
Group=tunnel-system
WorkingDirectory=/opt/tunnel-system
Environment=PATH=/opt/tunnel-system/venv/bin
ExecStart=/opt/tunnel-system/venv/bin/python tunnel_broker_service.py
ExecReload=/bin/kill -HUP \$MAINPID
KillMode=mixed
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tunnel-broker

# Безопасность
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/tunnel-system/data /var/log/tunnel-system

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    log_success "Systemd сервис создан"
}

# Создание wrapper сервиса с watchdog
create_service_wrapper() {
    log_info "Создание wrapper сервиса с watchdog..."
    
    cat > /opt/tunnel-system/tunnel_broker_service.py << 'EOF'
#!/usr/bin/env python3
"""
Tunnel Broker Service Wrapper с watchdog
"""

import os
import sys
import time
import signal
import subprocess
import threading
import configparser
import logging
from datetime import datetime, timedelta
from pathlib import Path
import psutil

class TunnelBrokerService:
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config.read('/opt/tunnel-system/config.ini')
        
        # Настройка логирования
        log_dir = self.config.get('logging', 'log_dir', fallback='/var/log/tunnel-system')
        log_level = self.config.get('logging', 'level', fallback='INFO')
        
        os.makedirs(log_dir, exist_ok=True)
        
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s [%(name)s] %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f'{log_dir}/tunnel-broker.log'),
                logging.StreamHandler()
            ]
        )
        
        self.logger = logging.getLogger('TunnelBrokerService')
        
        # Параметры watchdog
        self.watchdog_enabled = self.config.getboolean('watchdog', 'enabled', fallback=True)
        self.check_interval = self.config.getint('watchdog', 'check_interval', fallback=30)
        self.restart_delay = self.config.getint('watchdog', 'restart_delay', fallback=5)
        self.max_restarts_per_hour = self.config.getint('watchdog', 'max_restarts_per_hour', fallback=10)
        
        # Статистика перезапусков
        self.restart_history = []
        self.broker_process = None
        self.is_running = False
        
    def start_broker(self):
        """Запуск основного процесса брокера"""
        try:
            cmd = [
                '/opt/tunnel-system/venv/bin/python',
                '/opt/tunnel-system/tunnel_broker.py',
                '--host', self.config.get('broker', 'host', fallback='0.0.0.0'),
                '--port', self.config.get('broker', 'port', fallback='8080')
            ]
            
            self.logger.info(f"Запуск broker: {' '.join(cmd)}")
            
            self.broker_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                cwd='/opt/tunnel-system'
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка запуска broker: {e}")
            return False
    
    def stop_broker(self):
        """Остановка процесса брокера"""
        if self.broker_process:
            try:
                self.logger.info("Остановка broker...")
                self.broker_process.terminate()
                
                # Ждем graceful shutdown
                try:
                    self.broker_process.wait(timeout=10)
                    self.logger.info("Broker остановлен gracefully")
                except subprocess.TimeoutExpired:
                    self.logger.warning("Принудительное завершение broker...")
                    self.broker_process.kill()
                    self.broker_process.wait()
                    
            except Exception as e:
                self.logger.error(f"Ошибка остановки broker: {e}")
            finally:
                self.broker_process = None
    
    def is_broker_healthy(self):
        """Проверка здоровья брокера"""
        if not self.broker_process:
            return False
            
        # Проверяем, что процесс еще жив
        if self.broker_process.poll() is not None:
            self.logger.warning(f"Broker процесс завершился с кодом {self.broker_process.returncode}")
            return False
        
        # Проверяем HTTP endpoint (простая проверка)
        try:
            import requests
            host = self.config.get('broker', 'host', fallback='localhost')
            port = self.config.get('broker', 'port', fallback='8080')
            
            if host == '0.0.0.0':
                host = 'localhost'
            
            response = requests.get(f'http://{host}:{port}/health', timeout=5)
            if response.status_code == 200:
                return True
            else:
                self.logger.warning(f"Broker health check failed: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.warning(f"Broker health check failed: {e}")
            return False
    
    def can_restart(self):
        """Проверка, можно ли перезапускать (ограничение по частоте)"""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        
        # Удаляем старые записи
        self.restart_history = [ts for ts in self.restart_history if ts > hour_ago]
        
        return len(self.restart_history) < self.max_restarts_per_hour
    
    def restart_broker(self):
        """Перезапуск брокера"""
        if not self.can_restart():
            self.logger.error(f"Превышен лимит перезапусков ({self.max_restarts_per_hour}/час)")
            return False
        
        self.logger.info("Перезапуск broker...")
        
        # Останавливаем
        self.stop_broker()
        
        # Ждем
        time.sleep(self.restart_delay)
        
        # Запускаем
        if self.start_broker():
            self.restart_history.append(datetime.now())
            self.logger.info("Broker успешно перезапущен")
            return True
        else:
            self.logger.error("Не удалось перезапустить broker")
            return False
    
    def watchdog_loop(self):
        """Основной цикл watchdog"""
        self.logger.info("Запуск watchdog...")
        
        while self.is_running:
            try:
                if not self.is_broker_healthy():
                    self.logger.warning("Broker не отвечает, попытка перезапуска...")
                    
                    if not self.restart_broker():
                        self.logger.error("Критическая ошибка: не удалось перезапустить broker")
                        break
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"Ошибка в watchdog loop: {e}")
                time.sleep(self.check_interval)
    
    def signal_handler(self, signum, frame):
        """Обработчик сигналов"""
        self.logger.info(f"Получен сигнал {signum}, остановка сервиса...")
        self.stop()
    
    def start(self):
        """Запуск сервиса"""
        self.logger.info("🚀 Запуск Tunnel Broker Service...")
        
        # Регистрируем обработчики сигналов
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        
        self.is_running = True
        
        # Запускаем broker
        if not self.start_broker():
            self.logger.error("Не удалось запустить broker")
            return 1
        
        # Запускаем watchdog если включен
        if self.watchdog_enabled:
            watchdog_thread = threading.Thread(target=self.watchdog_loop, daemon=True)
            watchdog_thread.start()
            self.logger.info("Watchdog запущен")
        else:
            self.logger.info("Watchdog отключен")
        
        self.logger.info("Tunnel Broker Service запущен успешно")
        
        # Основной цикл
        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Получен Ctrl+C")
        
        self.stop()
        return 0
    
    def stop(self):
        """Остановка сервиса"""
        self.logger.info("Остановка Tunnel Broker Service...")
        self.is_running = False
        self.stop_broker()
        self.logger.info("Tunnel Broker Service остановлен")

if __name__ == '__main__':
    service = TunnelBrokerService()
    sys.exit(service.start())
EOF

    chmod +x /opt/tunnel-system/tunnel_broker_service.py
    chown tunnel-system:tunnel-system /opt/tunnel-system/tunnel_broker_service.py
    
    log_success "Service wrapper создан"
}

# Настройка Nginx
setup_nginx() {
    log_info "Настройка Nginx..."
    
    # Backup existing config
    if [[ -f /etc/nginx/sites-available/default ]]; then
        cp /etc/nginx/sites-available/default /etc/nginx/sites-available/default.backup
    fi
    
    cat > /etc/nginx/sites-available/tunnel-system << EOF
server {
    listen 80;
    server_name _;
    
    # Redirect HTTP to HTTPS (раскомментируйте после настройки SSL)
    # return 301 https://\$server_name\$request_uri;
    
    # Временно разрешаем HTTP
    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # WebSocket поддержка
    location /ws {
        proxy_pass http://localhost:8081;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Статические файлы (если есть)
    location /static {
        alias /opt/tunnel-system/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
}
EOF

    # Активируем конфигурацию
    ln -sf /etc/nginx/sites-available/tunnel-system /etc/nginx/sites-enabled/
    
    # Удаляем default если есть
    rm -f /etc/nginx/sites-enabled/default
    
    # Тестируем конфигурацию
    nginx -t
    
    log_success "Nginx настроен"
}

# Настройка файрвола
setup_firewall() {
    log_info "Настройка файрвола..."
    
    if command -v ufw >/dev/null 2>&1; then
        # Ubuntu/Debian - ufw
        ufw --force enable
        ufw allow ssh
        ufw allow 80/tcp
        ufw allow 443/tcp
        ufw allow 8080/tcp  # Для прямого доступа к API
        log_success "UFW настроен"
    elif command -v firewall-cmd >/dev/null 2>&1; then
        # CentOS/RHEL - firewalld
        systemctl enable firewalld
        systemctl start firewalld
        firewall-cmd --permanent --add-service=ssh
        firewall-cmd --permanent --add-service=http
        firewall-cmd --permanent --add-service=https
        firewall-cmd --permanent --add-port=8080/tcp
        firewall-cmd --reload
        log_success "Firewalld настроен"
    else
        log_warning "Файрвол не найден, настройте вручную"
    fi
}

# Запуск сервисов
start_services() {
    log_info "Запуск сервисов..."
    
    # Запускаем и включаем автозапуск tunnel-broker
    systemctl enable tunnel-broker
    systemctl start tunnel-broker
    
    # Перезапускаем nginx
    systemctl enable nginx
    systemctl restart nginx
    
    log_success "Сервисы запущены"
}

# Проверка статуса
check_status() {
    log_info "Проверка статуса сервисов..."
    
    echo "=== Tunnel Broker ==="
    systemctl status tunnel-broker --no-pager -l
    
    echo -e "\n=== Nginx ==="
    systemctl status nginx --no-pager -l
    
    echo -e "\n=== Проверка портов ==="
    ss -tlnp | grep -E ":80|:8080|:8081"
    
    echo -e "\n=== Health Check ==="
    sleep 3  # Даем время на запуск
    
    if curl -s http://localhost:8080/health >/dev/null; then
        log_success "✅ Tunnel Broker отвечает на http://localhost:8080"
    else
        log_error "❌ Tunnel Broker не отвечает"
    fi
    
    # Получаем внешний IP
    EXTERNAL_IP=$(curl -s ifconfig.me || curl -s icanhazip.com || echo "unknown")
    
    echo -e "\n=== Адреса доступа ==="
    log_success "🌍 Внешний доступ: http://$EXTERNAL_IP"
    log_success "🏠 Локальный доступ: http://localhost"
    log_success "🔧 API: http://$EXTERNAL_IP:8080"
}

# Создание скрипта управления
create_management_script() {
    log_info "Создание скрипта управления..."
    
    cat > /opt/tunnel-system/manage.sh << 'EOF'
#!/bin/bash
# Скрипт управления Tunnel System

case "$1" in
    start)
        echo "Запуск Tunnel System..."
        sudo systemctl start tunnel-broker
        sudo systemctl start nginx
        echo "Сервисы запущены"
        ;;
    stop)
        echo "Остановка Tunnel System..."
        sudo systemctl stop tunnel-broker
        echo "Tunnel Broker остановлен"
        ;;
    restart)
        echo "Перезапуск Tunnel System..."
        sudo systemctl restart tunnel-broker
        sudo systemctl restart nginx
        echo "Сервисы перезапущены"
        ;;
    status)
        echo "=== Tunnel Broker ==="
        sudo systemctl status tunnel-broker --no-pager -l
        echo -e "\n=== Nginx ==="
        sudo systemctl status nginx --no-pager -l
        ;;
    logs)
        echo "Логи Tunnel Broker (Ctrl+C для выхода):"
        sudo journalctl -u tunnel-broker -f
        ;;
    health)
        echo "Проверка здоровья сервиса..."
        curl -s http://localhost:8080/health | python3 -m json.tool || echo "Сервис недоступен"
        ;;
    *)
        echo "Использование: $0 {start|stop|restart|status|logs|health}"
        echo ""
        echo "Команды:"
        echo "  start   - Запуск сервисов"
        echo "  stop    - Остановка сервисов"
        echo "  restart - Перезапуск сервисов"
        echo "  status  - Статус сервисов"
        echo "  logs    - Просмотр логов в реальном времени"
        echo "  health  - Проверка API"
        exit 1
        ;;
esac
EOF

    chmod +x /opt/tunnel-system/manage.sh
    
    # Создаем symlink в /usr/local/bin
    ln -sf /opt/tunnel-system/manage.sh /usr/local/bin/tunnel-system
    
    log_success "Скрипт управления создан: tunnel-system {start|stop|restart|status|logs|health}"
}

# Главная функция
main() {
    echo "🚀 Tunnel System - Автоматический установщик"
    echo "=============================================="
    
    check_root
    detect_os
    install_dependencies
    create_service_user
    setup_directories
    setup_python_env
    create_config
    create_service_wrapper
    create_systemd_service
    setup_nginx
    setup_firewall
    start_services
    create_management_script
    check_status
    
    echo ""
    echo "=============================================="
    log_success "🎉 Установка завершена успешно!"
    echo "=============================================="
    echo ""
    echo "📋 Управление сервисом:"
    echo "   tunnel-system start    - Запуск"
    echo "   tunnel-system stop     - Остановка"  
    echo "   tunnel-system restart  - Перезапуск"
    echo "   tunnel-system status   - Статус"
    echo "   tunnel-system logs     - Логи"
    echo "   tunnel-system health   - Проверка API"
    echo ""
    echo "🌍 Доступ к сервису:"
    echo "   Внешний: http://$EXTERNAL_IP"
    echo "   API:     http://$EXTERNAL_IP:8080"
    echo ""
    echo "📁 Файлы:"
    echo "   Код:    /opt/tunnel-system/"
    echo "   Логи:   /var/log/tunnel-system/"
    echo "   Конфиг: /opt/tunnel-system/config.ini"
    echo ""
    log_success "✅ Tunnel System готов к использованию!"
}

# Запуск
main "$@"