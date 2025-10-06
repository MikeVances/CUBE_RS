#!/bin/bash
# Скрипт резервного копирования CUBE EDGE
# Создает полную резервную копию данных, конфигураций и логов

set -e

# Конфигурация
BACKUP_BASE_DIR="/var/backups/cube_edge"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="$BACKUP_BASE_DIR/$TIMESTAMP"
KEEP_DAYS=30

# Источники данных
DATA_DIR="/var/lib/cube_edge"
CONFIG_DIR="/etc/cube_edge"
EDGE_CONFIG_DIR="/opt/cube_edge/config"
LOGS_DIR="/var/log/cube_edge"

# Функция логирования
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [BACKUP] $1" | tee -a /var/log/cube_edge/backup.log
}

# Проверка существования директорий
check_source_dirs() {
    log "Проверка исходных директорий..."
    
    for dir in "$DATA_DIR" "$EDGE_CONFIG_DIR"; do
        if [ ! -d "$dir" ]; then
            log "ПРЕДУПРЕЖДЕНИЕ: Директория $dir не найдена"
        fi
    done
}

# Создание директории для backup
create_backup_dir() {
    log "Создание директории резервной копии: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    
    # Создаем структуру
    mkdir -p "$BACKUP_DIR/data"
    mkdir -p "$BACKUP_DIR/config"
    mkdir -p "$BACKUP_DIR/logs"
    mkdir -p "$BACKUP_DIR/metadata"
}

# Backup баз данных
backup_databases() {
    log "Резервное копирование баз данных..."
    
    if [ -f "$DATA_DIR/kub_data.db" ]; then
        # Создаем dump SQLite базы
        sqlite3 "$DATA_DIR/kub_data.db" ".dump" > "$BACKUP_DIR/data/kub_data.sql"
        
        # Копируем саму базу
        cp "$DATA_DIR/kub_data.db" "$BACKUP_DIR/data/"
        log "✅ kub_data.db скопирована"
    fi
    
    if [ -f "$DATA_DIR/kub_commands.db" ]; then
        sqlite3 "$DATA_DIR/kub_commands.db" ".dump" > "$BACKUP_DIR/data/kub_commands.sql"
        cp "$DATA_DIR/kub_commands.db" "$BACKUP_DIR/data/"
        log "✅ kub_commands.db скопирована"
    fi
    
    # Копируем метрики если есть
    if [ -f "$DATA_DIR/metrics.json" ]; then
        cp "$DATA_DIR/metrics.json" "$BACKUP_DIR/data/"
        log "✅ metrics.json скопированы"
    fi
}

# Backup конфигураций
backup_configs() {
    log "Резервное копирование конфигураций..."
    
    # Системная конфигурация
    if [ -d "$CONFIG_DIR" ]; then
        cp -r "$CONFIG_DIR"/* "$BACKUP_DIR/config/" 2>/dev/null || true
        log "✅ Системные конфигурации скопированы"
    fi
    
    # EDGE конфигурации (но без секретов в открытом виде)
    if [ -d "$EDGE_CONFIG_DIR" ]; then
        # Копируем все кроме dev_password.txt
        find "$EDGE_CONFIG_DIR" -type f ! -name "dev_password.txt" -exec cp {} "$BACKUP_DIR/config/" \;
        log "✅ EDGE конфигурации скопированы (без dev паролей)"
    fi
}

# Backup логов (только последние)
backup_logs() {
    log "Резервное копирование логов..."
    
    if [ -d "$LOGS_DIR" ]; then
        # Копируем логи за последние 7 дней
        find "$LOGS_DIR" -name "*.log" -mtime -7 -exec cp {} "$BACKUP_DIR/logs/" \;
        log "✅ Логи за последние 7 дней скопированы"
    fi
    
    # Журнал systemd за последний день
    journalctl -u cube-edge --since "1 day ago" > "$BACKUP_DIR/logs/systemd_cube-edge.log" 2>/dev/null || true
}

# Создание метаданных backup
create_metadata() {
    log "Создание метаданных резервной копии..."
    
    cat > "$BACKUP_DIR/metadata/backup_info.txt" << EOF
CUBE EDGE Backup Information
============================
Timestamp: $TIMESTAMP
Date: $(date)
Hostname: $(hostname)
User: $(whoami)
EDGE Version: $(cat /opt/cube_edge/VERSION 2>/dev/null || echo "unknown")

Directories backed up:
- Data: $DATA_DIR
- Config: $CONFIG_DIR, $EDGE_CONFIG_DIR  
- Logs: $LOGS_DIR

System Info:
- Disk usage: $(df -h /var/lib/cube_edge 2>/dev/null || echo "N/A")
- Memory: $(free -h | head -2 | tail -1)
- Uptime: $(uptime)

EOF

    # Хеши файлов для проверки целостности
    find "$BACKUP_DIR" -type f -exec sha256sum {} \; > "$BACKUP_DIR/metadata/checksums.sha256"
    
    log "✅ Метаданные созданы"
}

# Сжатие backup
compress_backup() {
    log "Сжатие резервной копии..."
    
    cd "$BACKUP_BASE_DIR"
    tar -czf "${TIMESTAMP}.tar.gz" "$TIMESTAMP"
    
    if [ $? -eq 0 ]; then
        # Удаляем несжатую версию
        rm -rf "$BACKUP_DIR"
        
        # Размер архива
        ARCHIVE_SIZE=$(du -h "${TIMESTAMP}.tar.gz" | cut -f1)
        log "✅ Резервная копия сжата: ${TIMESTAMP}.tar.gz ($ARCHIVE_SIZE)"
    else
        log "❌ Ошибка сжатия резервной копии"
        exit 1
    fi
}

# Очистка старых backup
cleanup_old_backups() {
    log "Очистка старых резервных копий (старше $KEEP_DAYS дней)..."
    
    find "$BACKUP_BASE_DIR" -name "*.tar.gz" -mtime +$KEEP_DAYS -delete
    
    REMAINING=$(find "$BACKUP_BASE_DIR" -name "*.tar.gz" | wc -l)
    log "✅ Очистка завершена. Осталось резервных копий: $REMAINING"
}

# Отправка уведомления об успешном backup
send_notification() {
    log "Отправка уведомления о резервном копировании..."
    
    # Если есть Telegram бот, отправляем уведомление
    if systemctl is-active --quiet cube-edge.service; then
        python3 << EOF
import sys
sys.path.append('/opt/cube_edge')
try:
    from core.security_manager import get_security_manager
    from monitoring.prometheus_config import add_alert
    
    add_alert("INFO", "Резервное копирование выполнено успешно: $TIMESTAMP", "backup")
    print("Уведомление отправлено через систему мониторинга")
except Exception as e:
    print(f"Не удалось отправить уведомление: {e}")
EOF
    fi
}

# Главная функция
main() {
    log "🔄 Начало резервного копирования CUBE EDGE..."
    
    # Проверяем права
    if [ "$EUID" -ne 0 ] && [ "$(whoami)" != "cube_edge" ]; then
        log "❌ Скрипт должен быть запущен от пользователя cube_edge или root"
        exit 1
    fi
    
    # Проверяем наличие места на диске
    AVAILABLE_SPACE=$(df /var/backups 2>/dev/null | tail -1 | awk '{print $4}' || echo "0")
    if [ "$AVAILABLE_SPACE" -lt 1000000 ]; then  # Меньше 1GB
        log "⚠️ ПРЕДУПРЕЖДЕНИЕ: Мало места на диске для резервных копий"
    fi
    
    # Выполняем backup
    check_source_dirs
    create_backup_dir
    backup_databases
    backup_configs
    backup_logs
    create_metadata
    compress_backup
    cleanup_old_backups
    send_notification
    
    log "✅ Резервное копирование завершено успешно: ${TIMESTAMP}.tar.gz"
    
    # Показываем статистику
    echo ""
    echo "📊 Статистика резервного копирования:"
    echo "   Файл: $BACKUP_BASE_DIR/${TIMESTAMP}.tar.gz"
    echo "   Размер: $(du -h "$BACKUP_BASE_DIR/${TIMESTAMP}.tar.gz" 2>/dev/null | cut -f1 || echo 'N/A')"
    echo "   Всего копий: $(find "$BACKUP_BASE_DIR" -name "*.tar.gz" | wc -l)"
    echo "   Свободно на диске: $(df -h /var/backups 2>/dev/null | tail -1 | awk '{print $4}' || echo 'N/A')"
}

# Обработка сигналов
trap 'log "❌ Резервное копирование прервано"; exit 1' INT TERM

# Запуск
main "$@"