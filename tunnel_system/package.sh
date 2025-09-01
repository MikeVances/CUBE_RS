#!/bin/bash
# 📦 Упаковщик Tunnel System для передачи на хостинг

set -e

# Цвета
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}📦 Упаковка Tunnel System для deployment${NC}"
echo "=================================================="

# Определяем директории
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PACKAGE_NAME="tunnel-system-$(date +%Y%m%d-%H%M%S)"
PACKAGE_DIR="/tmp/$PACKAGE_NAME"

echo -e "${BLUE}📁 Создание пакета: $PACKAGE_NAME${NC}"

# Создаем временную директорию
rm -rf "$PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR"

# Копируем основные файлы
echo -e "${BLUE}📄 Копирование файлов...${NC}"

cp "$SCRIPT_DIR/tunnel_broker.py" "$PACKAGE_DIR/"
cp "$SCRIPT_DIR/farm_client.py" "$PACKAGE_DIR/"  
cp "$SCRIPT_DIR/mobile_app.py" "$PACKAGE_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$PACKAGE_DIR/"
cp "$SCRIPT_DIR/README.md" "$PACKAGE_DIR/"
cp "$SCRIPT_DIR/DEPLOYMENT.md" "$PACKAGE_DIR/"
cp "$SCRIPT_DIR/deploy.sh" "$PACKAGE_DIR/"

# Копируем шаблоны если есть
if [[ -d "$SCRIPT_DIR/templates" ]]; then
    cp -r "$SCRIPT_DIR/templates" "$PACKAGE_DIR/"
    echo -e "${GREEN}✅ Шаблоны скопированы${NC}"
fi

# Делаем скрипты исполняемыми
chmod +x "$PACKAGE_DIR"/*.py
chmod +x "$PACKAGE_DIR/deploy.sh"

# Создаем файл версии
echo "$(date)" > "$PACKAGE_DIR/VERSION"
echo "Tunnel System Deployment Package" >> "$PACKAGE_DIR/VERSION"
echo "Generated from: $(hostname)" >> "$PACKAGE_DIR/VERSION"

# Создаем быстрый README для установки
cat > "$PACKAGE_DIR/INSTALL.md" << 'EOF'
# 🚀 Быстрая установка Tunnel System

## 📋 Перед установкой
- Сервер с Ubuntu 20.04+ / CentOS 7+ / Debian 10+
- Права root (sudo)
- Открытые порты: 80, 443, 8080
- Минимум 512MB RAM, 1GB диск

## 🛠️ Установка (одна команда)
```bash
sudo ./deploy.sh
```

## ✅ После установки
```bash
# Управление сервисом
tunnel-system status   # Проверить статус
tunnel-system logs     # Смотреть логи
tunnel-system health   # Проверить API

# Доступ
http://YOUR_SERVER_IP      # Web интерфейс  
http://YOUR_SERVER_IP:8080 # API напрямую
```

## 📞 Поддержка
- Логи: `/var/log/tunnel-system/`
- Конфиг: `/opt/tunnel-system/config.ini`
- Сервис: `systemctl status tunnel-broker`

Подробная документация в файле `DEPLOYMENT.md`
EOF

# Создаем контрольную сумму
echo -e "${BLUE}🔐 Создание контрольной суммы...${NC}"
cd "$PACKAGE_DIR"
find . -type f -name "*.py" -o -name "*.md" -o -name "*.txt" -o -name "*.sh" | sort | xargs sha256sum > CHECKSUMS.txt

# Создаем архив
echo -e "${BLUE}📁 Создание архива...${NC}"
cd /tmp
tar czf "$PACKAGE_NAME.tar.gz" "$PACKAGE_NAME"

# Вычисляем размер
PACKAGE_SIZE=$(du -h "$PACKAGE_NAME.tar.gz" | cut -f1)

echo ""
echo "=================================================="
echo -e "${GREEN}🎉 Пакет создан успешно!${NC}"
echo "=================================================="
echo -e "${YELLOW}📦 Файл:${NC} /tmp/$PACKAGE_NAME.tar.gz"
echo -e "${YELLOW}📏 Размер:${NC} $PACKAGE_SIZE"
echo ""
echo -e "${BLUE}📋 Содержимое пакета:${NC}"
tar -tzf "/tmp/$PACKAGE_NAME.tar.gz" | head -15
if [[ $(tar -tzf "/tmp/$PACKAGE_NAME.tar.gz" | wc -l) -gt 15 ]]; then
    echo "... и еще $(( $(tar -tzf "/tmp/$PACKAGE_NAME.tar.gz" | wc -l) - 15 )) файлов"
fi

echo ""
echo -e "${BLUE}🚀 Для установки на сервере:${NC}"
echo "1. Скачайте архив на сервер:"
echo "   scp /tmp/$PACKAGE_NAME.tar.gz root@your-server:/tmp/"
echo ""
echo "2. Распакуйте и установите:"
echo "   ssh root@your-server"
echo "   cd /tmp"
echo "   tar -xzf $PACKAGE_NAME.tar.gz"
echo "   cd $PACKAGE_NAME"
echo "   sudo ./deploy.sh"
echo ""
echo -e "${GREEN}✅ Автоматическая установка займет 2-3 минуты${NC}"
echo ""

# Очищаем временную директорию
rm -rf "$PACKAGE_DIR"

echo -e "${BLUE}📦 Упаковка завершена!${NC}"