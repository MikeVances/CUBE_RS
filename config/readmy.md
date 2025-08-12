# 🔒 Безопасная настройка CUBE_RS Telegram Bot

## 🎯 Принципы безопасности

❌ **НЕ ДЕЛАЙТЕ:**
- Не храните токены в коде
- Не коммитьте файлы с секретами в Git
- Не используйте переменные окружения на продакшене
- Не передавайте токены в открытом виде

✅ **ДЕЛАЙТЕ:**
- Используйте защищённые файлы конфигурации
- Устанавливайте правильные права доступа
- Ведите аудит доступа к секретам
- Регулярно ротируйте токены

## 🛠️ Настройка токена

### Способ 1: Интерактивная настройка (Рекомендуется)

```bash
# Запустите бота - система автоматически запросит токен
python start_bot.py

# Система спросит:
# 🤖 Bot Token: [введите токен, он будет скрыт]
# 💾 Сохранить токен в защищённом файле? (y/N): y
```

**Преимущества:**
- ✅ Токен не отображается в терминале
- ✅ Автоматически устанавливаются безопасные права (600)
- ✅ Токен сохраняется в `config/bot_secrets.json`

### Способ 2: Создание файла вручную

```bash
# Создайте файл конфигурации
mkdir -p config
nano config/bot_secrets.json
```

```json
{
  "telegram": {
    "bot_token": "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ1234567890",
    "admin_users": [123456789, 987654321]
  },
  "security": {
    "session_timeout": 3600,
    "max_failed_attempts": 5
  }
}
```

```bash
# Установите безопасные права доступа
chmod 600 config/bot_secrets.json

# Проверьте права
ls -la config/bot_secrets.json
# Должно быть: -rw------- (только владелец может читать/писать)
```

### Способ 3: Переменная окружения (НЕ рекомендуется)

```bash
# Только для тестирования!
export TELEGRAM_BOT_TOKEN='your_token_here'
python start_bot.py
```

⚠️ **Предупреждение:** Этот способ небезопасен для продакшена!

## 🛡️ Проверка безопасности

### Автоматическая проверка:

```bash
# Запустите проверку безопасности
python telegram_bot/secure_config.py

# Или через основной скрипт
python start_bot.py --check
```

### Ручная проверка:

```bash
# 1. Проверьте права доступа к файлу
ls -la config/bot_secrets.json
# Должно быть: -rw------- (600)

# 2. Убедитесь что файл НЕ в Git
git status --ignored
# bot_secrets.json должен быть в игнорируемых

# 3. Проверьте .gitignore
grep "bot_secrets" .gitignore
# Должна быть строка: config/bot_secrets.json
```

## 👑 Настройка администраторов

### Способ 1: Через файл конфигурации

```json
{
  "telegram": {
    "bot_token": "your_token",
    "admin_users": [
      123456789,  // Ваш Telegram ID
      987654321   // ID другого админа
    ]
  }
}
```

### Способ 2: Программно

```python
from telegram_bot.secure_config import SecureConfig

config = SecureConfig()
config.add_admin_user(123456789)  # Ваш Telegram ID
```

### Как узнать свой Telegram ID:

1. Напишите боту @userinfobot
2. Или используйте @get_id_bot
3. ID - это число, например: `123456789`

## 🔄 Ротация токенов

### Когда менять токен:
- ✅ Каждые 3-6 месяцев (плановая ротация)
- ✅ При подозрении на компрометацию
- ✅ При смене команды разработчиков
- ✅ После инцидентов безопасности

### Как сменить токен:

1. **Создайте новый токен у @BotFather:**
   ```
   /newtoken
   /mybots → выберите бота → API Token → Regenerate
   ```

2. **Обновите конфигурацию:**
   ```bash
   # Способ 1: Интерактивно
   rm config/bot_secrets.json
   python start_bot.py
   
   # Способ 2: Вручную
   nano config/bot_secrets.json  # Замените токен
   ```

3. **Перезапустите бота:**
   ```bash
   # Остановите старый процесс (Ctrl+C)
   python start_bot.py
   ```

## 📊 Аудит безопасности

### Логи безопасности:

```bash
# Проверьте логи на подозрительную активность
tail -f telegram_bot.log | grep -E "(WARN|ERROR|failed|ban)"

# Команды пользователей
sqlite3 kub_commands.db "
SELECT timestamp, telegram_id, command_type, success 
FROM user_command_history 
ORDER BY timestamp DESC LIMIT 50;
"
```

### Мониторинг доступа:

```sql
-- Активные пользователи за последние 24 часа
SELECT telegram_id, username, access_level, last_active 
FROM telegram_users 
WHERE last_active > datetime('now', '-1 day');

-- Неудачные попытки команд
SELECT telegram_id, command_type, timestamp 
FROM user_command_history 
WHERE success = 0 
ORDER BY timestamp DESC;
```

## 🚨 Действия при компрометации

### Немедленные действия:

1. **Отзовите токен:**
   ```bash
   # У @BotFather
   /mybots → Bot → Settings → Delete Bot (крайний случай)
   # Или
   /mybots → Bot → API Token → Regenerate
   ```

2. **Остановите бота:**
   ```bash
   pkill -f "start_bot.py"
   ```

3. **Заблокируйте подозрительных пользователей:**
   ```sql
   UPDATE telegram_users 
   SET is_active = 0 
   WHERE telegram_id = suspicious_user_id;
   ```

4. **Проанализируйте логи:**
   ```bash
   grep -E "(ERROR|WARN)" telegram_bot.log | tail -100
   ```

### Восстановление:

1. Создайте новый токен
2. Обновите конфигурацию
3. Перезапустите бота
4. Уведомите администраторов
5. Проведите анализ инцидента

## 🔧 Дополнительные меры безопасности

### Брандмауэр:

```bash
# Ограничьте исходящие соединения только к Telegram API
# (настройки зависят от вашего брандмауэра)
```

### Мониторинг системы:

```bash
# Автоматическое оповещение при ошибках
tail -f telegram_bot.log | grep ERROR | mail -s "Bot Error" admin@example.com
```

### Резервное копирование:

```bash
# Регулярно создавайте бэкапы (БЕЗ секретов!)
sqlite3 kub_commands.db ".backup backup_$(date +%Y%m%d).db"
tar -czf backup_$(date +%Y%m%d).tar.gz *.py config/bot_config.json
```

## ✅ Чек-лист безопасности

- [ ] Токен хранится в защищённом файле (не в коде)
- [ ] Права доступа к файлу: 600 (rw-------)
- [ ] Файл с токеном в .gitignore
- [ ] Настроены ID администраторов
- [ ] Логирование всех операций включено
- [ ] Регулярная ротация токенов (каждые 3-6 месяцев)
- [ ] Мониторинг логов на подозрительную активность
- [ ] Резервное копирование базы данных
- [ ] План действий при инциденте

---

💡 **Помните:** Безопасность - это процесс, а не состояние. Регулярно проверяйте и обновляйте настройки безопасности.