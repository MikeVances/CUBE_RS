#!/bin/bash
# Установка systemd сервисов для CUBE EDGE

set -e

echo "🔧 Установка systemd сервисов для CUBE EDGE..."

# Проверка прав root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Этот скрипт должен быть запущен от root"
    exit 1
fi

# Создание пользователя и группы
if ! id "cube_edge" &>/dev/null; then
    echo "👤 Создание пользователя cube_edge..."
    useradd --system --home-dir /opt/cube_edge --shell /bin/false cube_edge
fi

# Создание необходимых директорий
echo "📁 Создание директорий..."
mkdir -p /opt/cube_edge
mkdir -p /var/lib/cube_edge
mkdir -p /var/log/cube_edge
mkdir -p /var/backups/cube_edge
mkdir -p /etc/cube_edge

# Установка правильных прав
echo "🔐 Настройка прав доступа..."
chown -R cube_edge:cube_edge /opt/cube_edge
chown -R cube_edge:cube_edge /var/lib/cube_edge
chown -R cube_edge:cube_edge /var/log/cube_edge
chown -R cube_edge:cube_edge /var/backups/cube_edge
chown -R root:cube_edge /etc/cube_edge

chmod 755 /opt/cube_edge
chmod 750 /var/lib/cube_edge
chmod 750 /var/log/cube_edge
chmod 750 /var/backups/cube_edge
chmod 750 /etc/cube_edge

# Копирование файлов сервисов
echo "📋 Копирование unit файлов..."
cp cube-edge.service /etc/systemd/system/
cp cube-edge-backup.service /etc/systemd/system/
cp cube-edge-backup.timer /etc/systemd/system/
cp cube-edge-monitor.service /etc/systemd/system/

# Установка прав на unit файлы
chmod 644 /etc/systemd/system/cube-edge*.service
chmod 644 /etc/systemd/system/cube-edge*.timer

# Перезагрузка systemd
echo "🔄 Перезагрузка systemd daemon..."
systemctl daemon-reload

# Включение сервисов
echo "✅ Включение сервисов..."
systemctl enable cube-edge.service
systemctl enable cube-edge-backup.timer
systemctl enable cube-edge-monitor.service

# Создание logrotate конфигурации
echo "📝 Настройка logrotate..."
if [ -f "../config/logrotate.conf" ]; then
    cp ../config/logrotate.conf /etc/logrotate.d/cube-edge
    chown root:root /etc/logrotate.d/cube-edge
    chmod 644 /etc/logrotate.d/cube-edge
fi

echo ""
echo "✅ Установка завершена!"
echo ""
echo "Следующие шаги:"
echo "1. Скопируйте код EDGE в /opt/cube_edge/"
echo "2. Установите Python зависимости в /opt/cube_edge/venv/"
echo "3. Настройте конфигурацию в /etc/cube_edge/"
echo "4. Запустите сервис: systemctl start cube-edge"
echo ""
echo "Команды для управления:"
echo "  systemctl start cube-edge      # Запуск"
echo "  systemctl stop cube-edge       # Остановка"
echo "  systemctl status cube-edge     # Статус"
echo "  systemctl restart cube-edge    # Перезапуск"
echo "  journalctl -u cube-edge -f     # Просмотр логов"
echo ""
echo "Backup будет выполняться автоматически каждые 6 часов"
echo "Проверить: systemctl list-timers | grep cube-edge"