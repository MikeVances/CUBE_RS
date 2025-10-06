#!/bin/bash
# Скрипт развертывания CUBE EDGE для продакшн-среды
# Автоматизирует установку и настройку всей системы

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Конфигурация
EDGE_USER="cube_edge"
EDGE_HOME="/opt/cube_edge"
VENV_PATH="$EDGE_HOME/venv"
PYTHON_VERSION="3.11"

# Функции вывода
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
    if [ "$EUID" -ne 0 ]; then
        log_error "Этот скрипт должен быть запущен от root"
        exit 1
    fi
}

# Проверка операционной системы
check_os() {
    log_info "Проверка операционной системы..."
    
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$NAME
        VERSION=$VERSION_ID
        log_info "Обнаружена ОС: $OS $VERSION"
    else
        log_error "Не удалось определить операционную систему"
        exit 1
    fi
    
    # Проверяем поддерживаемые ОС
    case $OS in
        "Ubuntu"*|"Debian"*)
            PACKAGE_MANAGER="apt"
            ;;
        "CentOS"*|"Red Hat"*|"Rocky"*)
            PACKAGE_MANAGER="yum"
            ;;
        *)
            log_warning "ОС $OS может быть не полностью поддержана"
            PACKAGE_MANAGER="apt"  # По умолчанию
            ;;
    esac
}

# Установка системных зависимостей
install_system_deps() {
    log_info "Установка системных зависимостей..."
    
    case $PACKAGE_MANAGER in
        "apt")
            apt update
            apt install -y python3 python3-pip python3-venv python3-dev \
                          build-essential pkg-config libssl-dev libffi-dev \
                          sqlite3 systemd logrotate curl wget git \
                          ufw fail2ban
            ;;
        "yum")
            yum update -y
            yum install -y python3 python3-pip python3-devel \
                          gcc gcc-c++ make pkgconfig openssl-devel libffi-devel \
                          sqlite systemd logrotate curl wget git \
                          firewalld fail2ban
            ;;
    esac
    
    log_success "Системные зависимости установлены"
}

# Создание пользователя
create_user() {
    log_info "Создание пользователя $EDGE_USER..."
    
    if id "$EDGE_USER" &>/dev/null; then
        log_warning "Пользователь $EDGE_USER уже существует"
    else
        useradd --system --home-dir "$EDGE_HOME" --shell /bin/bash "$EDGE_USER"
        log_success "Пользователь $EDGE_USER создан"
    fi
}

# Создание директорий
create_directories() {
    log_info "Создание структуры директорий..."
    
    # Основные директории
    mkdir -p "$EDGE_HOME"
    mkdir -p /var/lib/cube_edge
    mkdir -p /var/log/cube_edge
    mkdir -p /var/backups/cube_edge
    mkdir -p /etc/cube_edge
    
    # Установка прав
    chown -R $EDGE_USER:$EDGE_USER "$EDGE_HOME"
    chown -R $EDGE_USER:$EDGE_USER /var/lib/cube_edge
    chown -R $EDGE_USER:$EDGE_USER /var/log/cube_edge
    chown -R $EDGE_USER:$EDGE_USER /var/backups/cube_edge
    chown -R root:$EDGE_USER /etc/cube_edge
    
    # Права доступа
    chmod 755 "$EDGE_HOME"
    chmod 750 /var/lib/cube_edge
    chmod 750 /var/log/cube_edge
    chmod 750 /var/backups/cube_edge
    chmod 750 /etc/cube_edge
    
    log_success "Структура директорий создана"
}

# Установка Python зависимостей
install_python_deps() {
    log_info "Установка Python зависимостей..."
    
    # Создаем виртуальное окружение
    sudo -u $EDGE_USER python3 -m venv "$VENV_PATH"
    
    # Обновляем pip
    sudo -u $EDGE_USER "$VENV_PATH/bin/pip" install --upgrade pip
    
    # Устанавливаем зависимости
    if [ -f "./requirements.txt" ]; then
        sudo -u $EDGE_USER "$VENV_PATH/bin/pip" install -r ./requirements.txt
        log_success "Python зависимости установлены из requirements.txt"
    else
        log_error "Файл requirements.txt не найден"
        exit 1
    fi
}

# Копирование файлов приложения
deploy_application() {
    log_info "Развертывание приложения..."
    
    # Копируем все файлы кроме .git, __pycache__, etc.
    rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
          --exclude='venv' --exclude='.pytest_cache' --exclude='*.log' \
          ./ "$EDGE_HOME/"
    
    # Устанавливаем права
    chown -R $EDGE_USER:$EDGE_USER "$EDGE_HOME"
    chmod +x "$EDGE_HOME/production_start.py"
    chmod +x "$EDGE_HOME/scripts/"*.sh
    
    # Создаем файл версии
    echo "$(date '+%Y.%m.%d-%H%M%S')" > "$EDGE_HOME/VERSION"
    
    log_success "Приложение развернуто"
}

# Настройка конфигурации
setup_configuration() {
    log_info "Настройка конфигурации..."
    
    # Копируем production конфигурацию
    if [ -f "./config/production.yaml" ]; then
        cp ./config/production.yaml /etc/cube_edge/app_config.yaml
        chown root:$EDGE_USER /etc/cube_edge/app_config.yaml
        chmod 640 /etc/cube_edge/app_config.yaml
    fi
    
    # Настройка переменных окружения
    cat > /etc/cube_edge/environment << EOF
# CUBE EDGE Environment Variables
ENVIRONMENT=production
CUBE_MASTER_PASSWORD_FILE=/etc/cube_edge/master_password
PYTHONPATH=$EDGE_HOME
EOF
    
    chmod 640 /etc/cube_edge/environment
    chown root:$EDGE_USER /etc/cube_edge/environment
    
    log_success "Конфигурация настроена"
}

# Установка systemd сервисов
install_systemd_services() {
    log_info "Установка systemd сервисов..."
    
    if [ -d "./systemd" ]; then
        cd systemd
        ./install_services.sh
        cd ..
        log_success "Systemd сервисы установлены"
    else
        log_error "Директория systemd не найдена"
        exit 1
    fi
}

# Настройка firewall
setup_firewall() {
    log_info "Настройка firewall..."
    
    case $PACKAGE_MANAGER in
        "apt")
            # Ubuntu/Debian - ufw
            ufw --force enable
            ufw default deny incoming
            ufw default allow outgoing
            
            # SSH
            ufw allow ssh
            
            # EDGE порты (только если нужны извне)
            # ufw allow 8090/tcp comment 'EDGE Health API'
            # ufw allow 8000/tcp comment 'EDGE WebSocket'
            
            log_success "UFW firewall настроен"
            ;;
        "yum")
            # CentOS/RHEL - firewalld
            systemctl enable firewalld
            systemctl start firewalld
            
            # SSH
            firewall-cmd --permanent --add-service=ssh
            firewall-cmd --reload
            
            log_success "Firewalld настроен"
            ;;
    esac
}

# Настройка fail2ban
setup_fail2ban() {
    log_info "Настройка fail2ban..."
    
    # Создаем jail для EDGE
    cat > /etc/fail2ban/jail.local << EOF
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true

[cube-edge]
enabled = true
port = 8090
filter = cube-edge
logpath = /var/log/cube_edge/security.log
maxretry = 3
bantime = 7200
EOF

    # Создаем фильтр для EDGE
    cat > /etc/fail2ban/filter.d/cube-edge.conf << EOF
[Definition]
failregex = .*SECURITY.*authentication failed.*<HOST>
            .*SECURITY.*unauthorized access.*<HOST>
            .*SECURITY.*too many requests.*<HOST>

ignoreregex =
EOF

    systemctl enable fail2ban
    systemctl restart fail2ban
    
    log_success "Fail2ban настроен"
}

# Инициализация секретов
init_secrets() {
    log_info "Инициализация системы секретов..."
    
    # Генерируем мастер-пароль
    MASTER_PASSWORD=$(openssl rand -base64 32)
    echo "$MASTER_PASSWORD" > /etc/cube_edge/master_password
    chmod 600 /etc/cube_edge/master_password
    chown root:root /etc/cube_edge/master_password
    
    # Инициализируем Security Manager
    export CUBE_MASTER_PASSWORD="$MASTER_PASSWORD"
    sudo -u $EDGE_USER -E "$VENV_PATH/bin/python" -c "
import sys
sys.path.append('$EDGE_HOME')
from core.security_manager import get_security_manager
sm = get_security_manager()
print('✅ Security Manager инициализирован')
"
    
    log_success "Система секретов инициализирована"
    log_warning "Сохраните мастер-пароль в безопасном месте!"
}

# Проверка развертывания
verify_deployment() {
    log_info "Проверка развертывания..."
    
    # Проверяем конфигурацию
    sudo -u $EDGE_USER "$VENV_PATH/bin/python" "$EDGE_HOME/production_start.py" --config-check
    
    if [ $? -eq 0 ]; then
        log_success "Конфигурация валидна"
    else
        log_error "Ошибка в конфигурации"
        exit 1
    fi
    
    # Проверяем готовность к запуску
    sudo -u $EDGE_USER "$VENV_PATH/bin/python" "$EDGE_HOME/production_start.py" --dry-run
    
    if [ $? -eq 0 ]; then
        log_success "Система готова к запуску"
    else
        log_error "Система не готова к запуску"
        exit 1
    fi
}

# Финальная настройка
final_setup() {
    log_info "Финальная настройка..."
    
    # Включаем сервисы
    systemctl enable cube-edge.service
    systemctl enable cube-edge-backup.timer
    systemctl enable cube-edge-monitor.service
    
    # Перезагружаем systemd
    systemctl daemon-reload
    
    log_success "Сервисы настроены для автозапуска"
}

# Главная функция
main() {
    echo "🚀 Развертывание CUBE EDGE Production"
    echo "===================================="
    
    check_root
    check_os
    
    # Выполняем развертывание
    install_system_deps
    create_user
    create_directories
    install_python_deps
    deploy_application
    setup_configuration
    install_systemd_services
    setup_firewall
    setup_fail2ban
    init_secrets
    verify_deployment
    final_setup
    
    echo ""
    log_success "🎉 Развертывание CUBE EDGE завершено успешно!"
    echo ""
    echo "📋 Следующие шаги:"
    echo "1. Настройте Telegram токен:"
    echo "   sudo -u $EDGE_USER $VENV_PATH/bin/python $EDGE_HOME/tools/telegram_secrets_cli.py set-token YOUR_TOKEN"
    echo ""
    echo "2. Настройте устройства в /etc/cube_edge/app_config.yaml"
    echo ""
    echo "3. Запустите сервис:"
    echo "   systemctl start cube-edge"
    echo ""
    echo "4. Проверьте статус:"
    echo "   systemctl status cube-edge"
    echo "   journalctl -u cube-edge -f"
    echo ""
    echo "🔐 Мастер-пароль сохранен в /etc/cube_edge/master_password"
    echo "⚡ Backup будет выполняться автоматически каждые 6 часов"
    echo "🔥 Firewall и fail2ban настроены"
    echo ""
    echo "✅ EDGE готов к работе!"
}

# Обработка сигналов
trap 'log_error "Развертывание прервано"; exit 1' INT TERM

# Запуск
main "$@"