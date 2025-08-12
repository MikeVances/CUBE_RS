# 🤖 Telegram Bot для КУБ-1063

Telegram Bot для управления системой климат-контроля КУБ-1063 через UnifiedKUBSystem.

## 🎯 Возможности

- **📊 Мониторинг** - чтение показаний датчиков в реальном времени
- **📈 Статистика** - информация о работе системы  
- **🔄 Управление** - сброс аварий и управление регистрами
- **🔐 Безопасность** - многоуровневая система прав доступа
- **📝 Аудит** - полное логирование всех операций

## 🏗️ Архитектура

```
telegram_bot/
├── bot_main.py          # Основной файл бота
├── bot_database.py      # Работа с базой пользователей  
├── bot_permissions.py   # Система прав доступа
├── bot_utils.py         # Форматирование и утилиты
└── README.md           # Эта инструкция

config/
└── telegram_bot.json   # Конфигурация бота

scripts/
├── create_base_db.py   # Создание основных баз
└── init_telegram_db.py # Создание таблиц для бота

start_bot.py            # Скрипт запуска
```

## 🚀 Быстрый старт

### 1. Создание Telegram Bot

1. Напишите @BotFather в Telegram
2. Создайте нового бота: `/newbot`
3. Выберите имя и username
4. Получите токен бота

### 2. Настройка окружения

```bash
# Установите токен
export TELEGRAM_BOT_TOKEN='your_bot_token_here'

# Или в Windows
set TELEGRAM_BOT_TOKEN=your_bot_token_here
```

### 3. Установка зависимостей

```bash
# Установка python-telegram-bot
pip install python-telegram-bot[all]

# Или через наш скрипт
python start_bot.py --install
```

### 4. Подготовка базы данных

```bash
# Создание основных баз (если не сделано)
python scripts/create_base_db.py

# Создание таблиц для бота
python scripts/init_telegram_db.py
```

### 5. Запуск бота

```bash
# Проверка готовности
python start_bot.py --check

# Запуск бота
python start_bot.py
```

## 🔐 Система прав доступа

### Уровни доступа:

| Уровень | Описание | Права |
|---------|----------|-------|
| **user** | 👀 Пользователь | Только чтение показаний |
| **operator** | 🔧 Оператор | Чтение + сброс аварий |
| **admin** | ⚙️ Администратор | Управление + настройки |
| **engineer** | 🛠️ Инженер | Полный доступ |

### Лимиты команд:
- **user**: 5 команд/час
- **operator**: 20 команд/час  
- **admin**: 50 команд/час
- **engineer**: 100 команд/час

## 📱 Команды бота

### Основные команды:
- `/start` - Регистрация и главное меню
- `/status` - Текущие показания датчиков
- `/stats` - Статистика работы системы
- `/help` - Справка по командам

### Команды управления:
- `/reset` - Сброс аварий (operator+)
- `/permissions` - Информация о правах доступа

### Inline кнопки:
- 🔄 Обновить данные
- 📊 Показать статистику  
- 🚨 Сброс аварий
- ⚙️ Настройки

## ⚙️ Конфигурация

Основные настройки в `config/telegram_bot.json`:

```json
{
  "permissions": {
    "admin_users": [123456789],     // ID админов
    "default_access_level": "user"
  },
  "rate_limiting": {
    "default_commands_per_hour": 10
  },
  "formatting": {
    "use_emojis": true,
    "decimal_places": 1
  }
}
```

## 📊 Управление пользователями

### Через базу данных:

```bash
# Просмотр пользователей
sqlite3 kub_commands.db "SELECT * FROM telegram_users;"

# Изменение уровня доступа
sqlite3 kub_commands.db "UPDATE telegram_users SET access_level='operator' WHERE telegram_id=123456789;"

# Деактивация пользователя  
sqlite3 kub_commands.db "UPDATE telegram_users SET is_active=0 WHERE telegram_id=123456789;"
```

### Программно:

```python
from telegram_bot.bot_database import TelegramBotDB

db = TelegramBotDB()

# Изменение уровня доступа
db.set_user_access_level(123456789, 'operator')

# Деактивация пользователя
db.deactivate_user(123456789)
```

## 🔧 Интеграция с UnifiedKUBSystem

Бот использует существующую `UnifiedKUBSystem` для:

- **Чтения данных**: `system.get_current_data()`
- **Выполнения команд**: `system.add_write_command()`
- **Получения статистики**: `system.get_system_statistics()`
- **Валидации**: `system.validate_write_command()`

Все операции логируются в `audit_log` с указанием пользователя Telegram.

## 📝 Логирование

### Файлы логов:
- `telegram_bot.log` - основной лог бота
- `kub_commands.db` - база команд и аудита

### Уровни логирования:
- **INFO** - обычные операции
- **WARNING** - подозрительная активность
- **ERROR** - ошибки выполнения
- **DEBUG** - отладочная информация

## 🛠️ Разработка и отладка

### Запуск в режиме отладки:

```python
# В bot_main.py измените уровень логирования
logging.basicConfig(level=logging.DEBUG)
```

### Тестирование модулей:

```bash
# Тест базы данных
python telegram_bot/bot_database.py

# Тест прав доступа  
python telegram_bot/bot_permissions.py

# Тест форматирования
python telegram_bot/bot_utils.py
```

### Структура базы данных:

```sql
-- Пользователи бота
telegram_users (telegram_id, username, access_level, created_at, ...)

-- История команд
user_command_history (telegram_id, command_type, timestamp, success, ...)

-- Настройки доступа
access_config (access_level, allowed_registers, can_read, can_write, ...)
```

## 🚨 Безопасность

### Рекомендации:
1. **Ограничьте доступ** - добавьте ID пользователей в `admin_users`
2. **Мониторьте логи** - проверяйте подозрительную активность
3. **Обновляйте токен** - периодически меняйте токен бота
4. **Резервные копии** - делайте бэкапы базы данных

### Блокировка пользователей:
```sql
UPDATE telegram_users SET is_active=0 WHERE telegram_id=suspicious_user_id;
```

## ❓ Устранение неполадок

### Бот не отвечает:
1. Проверьте токен: `echo $TELEGRAM_BOT_TOKEN`
2. Проверьте логи: `tail -f telegram_bot.log`
3. Проверьте базу: `ls -la *.db`

### Ошибки прав доступа:
1. Проверьте уровень пользователя в базе
2. Убедитесь что таблицы созданы
3. Проверьте лимиты команд

### Проблемы с UnifiedKUBSystem:
1. Убедитесь что система запущена
2. Проверьте подключение к КУБ-1063
3. Проверьте логи основной системы

## 📞 Поддержка

При проблемах:
1. Проверьте логи: `telegram_bot.log`
2. Запустите диагностику: `python start_bot.py --check`
3. Проверьте базу данных на целостность
4. Обратитесь к администратору системы

---

**Версия:** 1.0.0  
**Совместимость:** UnifiedKUBSystem v1.0+  
**Требования:** Python 3.8+, python-telegram-bot 20.0+