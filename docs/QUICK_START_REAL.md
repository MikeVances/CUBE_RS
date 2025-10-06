# 🚀 БЫСТРЫЙ ЗАПУСК CUBE_RS (Gateway уже работает!)

## ✅ **СИТУАЦИЯ:** Gateway работает, КУБ-1063 подключен!

---

## 🎯 **ДА, МОЖНО ЗАПУСКАТЬ!**

Если у вас Gateway уже работает и устройство подключено, тогда просто запускайте остальные сервисы:

### **Вариант 1: Автоматический запуск всех сервисов**
```bash
# В новом терминале:
python tools/start_all_services.py
```
Это запустит все сервисы из `start_all_services.py`:
- Dashboard (Streamlit)  
- Web App (Flask)
- WebSocket Server
- Telegram Bot
- Tunnel Broker

### **Вариант 2: Запуск отдельных сервисов в разных терминалах**

#### Терминал 1 (Gateway) - УЖЕ РАБОТАЕТ ✅
```bash
# Ваш Gateway уже работает с КУБ-1063
```

#### Терминал 2: Web Dashboard
```bash
cd CUBE_RS
python web_app/app.py
# Откроется на http://localhost:5000
```

#### Терминал 3: Streamlit Dashboard  
```bash
cd CUBE_RS
python dashboard/app.py
# Откроется на http://localhost:8501
```

#### Терминал 4: Telegram Bot
```bash
cd CUBE_RS
python telegram_bot/async_bot_main.py
```

#### Терминал 5: WebSocket Server
```bash
cd CUBE_RS  
python publish/websocket_server.py
# Запустится на ws://localhost:8765
```

---

## 🔧 **НАСТРОЙКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ**

Перед запуском установите переменные:
```bash
export SECRET_KEY="production-secret-key-change-me"
export API_KEY="your-gateway-api-key"
export API_SECRET="your-gateway-api-secret" 
export GATEWAY_URL="http://localhost:8000"
```

---

## 📋 **ПРОВЕРКА РАБОТЫ СИСТЕМЫ**

### 1. Проверьте что Gateway работает:
```bash
curl http://localhost:8000/api/health
```

### 2. Запустите CLI диагностику:
```bash
python tools/admin_cli.py status
```

### 3. Создайте первого администратора:
```bash
python tools/admin_cli.py create-user \
  --username admin \
  --email admin@company.com \
  --full-name "Administrator" \
  --password secure123 \
  --role "System Administrator" \
  --admin
```

### 4. Откройте веб-интерфейсы:
- **Main Dashboard**: http://localhost:5000
- **Streamlit Dashboard**: http://localhost:8501  
- **WebSocket**: ws://localhost:8765

---

## 🎯 **ПОЛНЫЙ WORKFLOW УПРАВЛЕНИЯ УСТРОЙСТВАМИ:**

### Шаг 1: Создайте ключ для нового устройства
```bash
python tools/admin_cli.py create-device-key \
  --expires 24 \
  --tags farm production \
  --created-by admin
```

### Шаг 2: Новое устройство регистрируется
Устройство использует полученный ключ для регистрации в системе

### Шаг 3: Одобряете регистрацию
```bash
python tools/admin_cli.py list-pending
python tools/admin_cli.py approve-registration --request-id <ID>
```

### Шаг 4: Устройство получает доступ! ✅

---

## 🔍 **TROUBLESHOOTING**

### Если порт занят:
```bash
# Найти процесс на порту
sudo lsof -i :5000

# Убить процесс
sudo lsof -ti:5000 | xargs kill -9
```

### Если не хватает переменных окружения:
```bash
# Минимальный набор для работы
export SECRET_KEY="dev-secret-key"
export API_KEY="test-key"
export API_SECRET="test-secret"
```

### Если ошибки импорта:
```bash
# Установить зависимости
pip install -r requirements.txt

# Проверить пути
export PYTHONPATH=$PYTHONPATH:$(pwd)
```

---

## 🎉 **ЗАКЛЮЧЕНИЕ:**

### ✅ **ДА! СИСТЕМА ГОТОВА К ЗАПУСКУ!**

Если Gateway работает и КУБ-1063 подключен, то:

1. **Запускайте все сервисы** через `start_all_services.py`
2. **Создавайте пользователей** через CLI
3. **Управляйте устройствами** через веб-интерфейс
4. **Все административные функции работают!**

**Система полностью готова к эксплуатации! 🚀**
