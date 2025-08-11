#!/bin/bash
# Скрипт тотальной очистки проекта CUBE_RS

echo "🧹 ТОТАЛЬНАЯ УБОРКА ПРОЕКТА CUBE_RS"
echo "=" * 50

# Создаем папку для бэкапов важных файлов
mkdir -p backup_before_cleanup
echo "📦 Создана папка backup_before_cleanup"

# Бэкапим важные конфиги и документацию
cp requirements.txt backup_before_cleanup/ 2>/dev/null
cp *.md backup_before_cleanup/ 2>/dev/null
cp -r docs backup_before_cleanup/ 2>/dev/null

echo "✅ Важные файлы сохранены в backup"

echo ""
echo "🗑️ УДАЛЕНИЕ НЕИСПОЛЬЗУЕМЫХ ФАЙЛОВ:"

# 1. Удаляем все __pycache__
echo "  • Удаление __pycache__ директорий..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
echo "    ✅ __pycache__ удалены"

# 2. Удаляем .pyc файлы
echo "  • Удаление .pyc файлов..."
find . -name "*.pyc" -delete 2>/dev/null
echo "    ✅ .pyc файлы удалены"

# 3. Удаляем старые main.py файлы
echo "  • Удаление ненужных main.py..."
rm -f main.py 2>/dev/null
rm -f dashboard/__main__.py 2>/dev/null
rm -f modbus/__main__.py 2>/dev/null
rm -f publish/__main__.py 2>/dev/null
echo "    ✅ Ненужные main.py удалены"

# 4. Удаляем дубликаты и старые файлы
echo "  • Удаление дубликатов и старых версий..."
rm -f config.py 2>/dev/null
rm -f dashboard/app2.py 2>/dev/null
rm -f modbus/dashboard_reader.py 2>/dev/null  # дубликат dashboard/
rm -f modbus/gateway.py.backup 2>/dev/null
rm -f modbus/OLDgateway.py 2>/dev/null
rm -f modbus/tcp_duplicator.py 2>/dev/null
rm -f publish/scaner.py 2>/dev/null
rm -f CUBE_RS_project.zip 2>/dev/null
echo "    ✅ Дубликаты и старые файлы удалены"

# 5. Очищаем логи (оставляем файлы но очищаем содержимое)
echo "  • Очистка логов..."
> gateway1.log 2>/dev/null
> gateway2.log 2>/dev/null
> mqtt.log 2>/dev/null
> reader.log 2>/dev/null
> start_services.log 2>/dev/null
> tcp_duplicator.log 2>/dev/null
> telegram_bot.log 2>/dev/null
> time_window_manager.log 2>/dev/null
> watchdog.log 2>/dev/null
echo "    ✅ Логи очищены"

# 6. Удаляем временные файлы SQLite
echo "  • Удаление временных файлов БД..."
rm -f kub_data.db-shm 2>/dev/null
rm -f kub_data.db-wal 2>/dev/null
echo "    ✅ Временные файлы БД удалены"

# 7. Очистка tools/ от тестовых файлов
echo "  • Очистка директории tools..."
cd tools 2>/dev/null && {
    # Оставляем только нужные файлы
    mkdir -p temp_keep
    cp start_all_services.py temp_keep/ 2>/dev/null
    cp stop_all_services.py temp_keep/ 2>/dev/null
    cp testcloud.py temp_keep/ 2>/dev/null
    cp test_direct_modbus.py temp_keep/ 2>/dev/null
    
    # Удаляем всё остальное
    rm -f *.py 2>/dev/null
    
    # Возвращаем нужные файлы
    cp temp_keep/* . 2>/dev/null
    rm -rf temp_keep
    
    cd ..
    echo "    ✅ Директория tools очищена"
}

echo ""
echo "📁 СОЗДАНИЕ ПРАВИЛЬНОЙ СТРУКТУРЫ:"

# Создаем нужные __init__.py если отсутствуют
touch dashboard/__init__.py 2>/dev/null
touch modbus/__init__.py 2>/dev/null
touch publish/__init__.py 2>/dev/null
echo "  ✅ __init__.py файлы созданы"

# Создаем .gitignore если его нет
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.pyc

# Logs
*.log

# Database
*.db-shm
*.db-wal

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Backup
backup_*/
EOF
echo "  ✅ .gitignore создан"

echo ""
echo "📊 РЕЗУЛЬТАТ ОЧИСТКИ:"

# Подсчитываем оставшиеся файлы
total_files=$(find . -type f | wc -l | tr -d ' ')
python_files=$(find . -name "*.py" | wc -l | tr -d ' ')
md_files=$(find . -name "*.md" | wc -l | tr -d ' ')

echo "  📁 Общий размер проекта: $(du -sh . | cut -f1)"
echo "  📄 Всего файлов: $total_files"
echo "  🐍 Python файлов: $python_files"  
echo "  📖 Документация (.md): $md_files"

echo ""
echo "✅ УБОРКА ЗАВЕРШЕНА!"
echo ""
echo "🎯 ОСТАВЛЕНЫ ТОЛЬКО НУЖНЫЕ ФАЙЛЫ:"
echo "  • modbus/ - основные модули системы"
echo "  • dashboard/ - дашборд Streamlit"
echo "  • publish/ - телеграм, mqtt, websocket"
echo "  • tools/ - только нужные утилиты" 
echo "  • docs/ - документация"
echo "  • *.md - описания и инструкции"
echo "  • requirements.txt - зависимости"
echo "  • kub_data.db - база данных"
echo ""
echo "🔥 УДАЛЕНЫ:"
echo "  • Все __pycache__ и .pyc"
echo "  • Дубликаты и старые версии"
echo "  • Тестовые и временные файлы"
echo "  • Пустые/ненужные main.py"
echo "  • Временные файлы SQLite"
echo ""
echo "📦 Бэкап важных файлов: backup_before_cleanup/"