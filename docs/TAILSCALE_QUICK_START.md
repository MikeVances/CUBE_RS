# 🚀 CUBE_RS с Tailscale - Быстрый старт

Пошаговая инструкция для развертывания системы мониторинга КУБ-1063 с Tailscale mesh-сетью.

## 📋 Предварительные требования

- Python 3.8+
- Аккаунт Tailscale (бесплатный)
- КУБ-1063 подключенный по Modbus TCP/RTU
- Linux/macOS/Windows с доступом в интернет

## 🎯 Шаг 1: Настройка Tailscale

### 1.1 Регистрация в Tailscale
1. Перейдите на https://tailscale.com
2. Зарегистрируйтесь или войдите в аккаунт
3. Создайте новый tailnet (например, `your-company.ts.net`)

### 1.2 Получение API ключа
1. Откройте https://login.tailscale.com/admin/settings/keys
2. Нажмите "Generate API key"
3. Сохраните ключ (начинается с `tskey-api-`)

### 1.3 Установка Tailscale на устройства
```bash
# Ubuntu/Debian
curl -fsSL https://tailscale.com/install.sh | sh

# macOS
brew install tailscale

# Windows  
# Скачайте с https://tailscale.com/download/windows
```

## 🏭 Шаг 2: Настройка фермы (КУБ-1063)

### 2.1 Подключение к Tailscale
```bash
# Подключение к вашему tailnet
sudo tailscale up --hostname=farm-001

# Проверка подключения
tailscale status
```

### 2.2 Клонирование и настройка CUBE_RS
```bash
# Клонирование репозитория
git clone https://github.com/your-repo/CUBE_RS.git
cd CUBE_RS

# Установка зависимостей
pip install -r requirements.txt

# Настройка переменных окружения для фермы
export TAILSCALE_ENABLED=true  
export TAILSCALE_TAILNET=your-company.ts.net
export TAILSCALE_API_KEY=tskey-api-xxxxxxxxxx
```

### 2.3 Запуск системы на ферме
```bash
# Запуск всех сервисов фермы
python tools/start_all_services.py

# Проверка статуса
python tools/check_services_status.py
```

Система автоматически:
- Запустит Modbus Gateway для чтения КУБ-1063
- Зарегистрирует ферму в Tailscale с тегом "farm"
- Начнет отправку heartbeat сигналов

## 💻 Шаг 3: Настройка центрального сервера (опционально)

### 3.1 Подключение сервера к Tailscale
```bash
# На центральном сервере/рабочем месте
sudo tailscale up --hostname=control-center

# Установка CUBE_RS  
git clone https://github.com/your-repo/CUBE_RS.git
cd CUBE_RS
pip install -r web_app/requirements.txt
```

### 3.2 Настройка веб-интерфейса
```bash
# Переменные окружения для управляющего сервера
export TAILSCALE_ENABLED=true
export TAILSCALE_TAILNET=your-company.ts.net  
export TAILSCALE_API_KEY=tskey-api-xxxxxxxxxx

# Настройка подключения к ферме (замените IP на Tailscale IP фермы)
export GATEWAY_URL=http://100.64.1.10:8000
export API_KEY=dev-api-key
export API_SECRET=your-api-secret

# Запуск веб-приложения
cd web_app
python app.py
```

### 3.3 Доступ к веб-интерфейсу
Откройте браузер и перейдите на:
- **Основной дашборд**: http://localhost:5000/
- **Управление Tailscale**: http://localhost:5000/tailscale

## 🎛️ Шаг 4: Управление системой

### 4.1 Веб-интерфейс
**Дашборд КУБ-1063** показывает:
- 📊 Графики температуры, влажности, CO₂, вентиляции
- 📈 История данных за последние часы
- ⚡ Real-time обновления каждые 30 секунд
- 📊 Статистику работы системы

**Управление Tailscale** позволяет:
- 🌐 Видеть все устройства в mesh-сети
- 🏭 Управлять фермами КУБ-1063
- 🔑 Создавать ключи для регистрации новых устройств
- 🔍 Проверять доступность устройств

### 4.2 Создание ключа для новой фермы
1. Откройте http://localhost:5000/tailscale
2. Нажмите кнопку "Создать ключ"
3. Настройте параметры:
   - ✅ Переиспользуемый ключ
   - ⏰ Срок действия (24 часа)
   - 🏷️ Теги: farm
4. Скопируйте созданный ключ

### 4.3 Подключение новой фермы
На новой ферме выполните:
```bash
# Подключение к Tailscale с полученным ключом  
sudo tailscale up --authkey=tskey-xxxxxxxxxx --hostname=farm-002

# Настройка и запуск CUBE_RS
# (повторите шаги 2.2-2.3)
```

## 🔐 Шаг 5: Настройка безопасности (рекомендуется)

### 5.1 Настройка ACL в Tailscale
В админ-панели Tailscale (https://login.tailscale.com/admin/acls) настройте правила доступа:

```json
{
  "tagOwners": {
    "tag:farm": ["your-email@company.com"],
    "tag:control": ["your-email@company.com"]
  },
  "acls": [
    {
      "action": "accept",
      "src": ["tag:control"],
      "dst": ["tag:farm:8000", "tag:farm:5000"]
    },
    {
      "action": "accept", 
      "src": ["tag:farm"],
      "dst": ["tag:control:5000"]
    }
  ]
}
```

### 5.2 Настройка RBAC (в веб-приложении)
Система автоматически создает роли:
- **System Administrator** - полный доступ
- **Farm Administrator** - управление фермой
- **Farm Operator** - мониторинг и базовое управление
- **Service Engineer** - диагностика и обслуживание
- **Read Only** - только просмотр

## 📱 Шаг 6: Мобильный доступ

### 6.1 Установка Tailscale на мобильное устройство
- **Android**: Google Play Store → Tailscale
- **iOS**: App Store → Tailscale

### 6.2 Подключение к сети
1. Войдите в приложение Tailscale с теми же учетными данными
2. Устройство автоматически подключится к mesh-сети
3. Откройте браузер и перейдите на Tailscale IP веб-сервера

### 6.3 PWA установка (опционально)
Веб-интерфейс поддерживает установку как PWA:
1. В браузере откройте веб-интерфейс
2. Нажмите "Добавить на главный экран"
3. Получите полноценное мобильное приложение

## 🔧 Шаг 7: Устранение проблем

### 7.1 Проверка подключения Tailscale
```bash
# Статус подключения
tailscale status

# Проверка IP адреса
tailscale ip -4

# Тест подключения к другому устройству
ping 100.64.1.10
```

### 7.2 Проверка работы CUBE_RS
```bash
# Статус сервисов
python tools/check_services_status.py

# Проверка API Gateway
curl http://localhost:8000/api/health

# Проверка веб-приложения
curl http://localhost:5000/api/status
```

### 7.3 Просмотр логов
```bash
# Логи системы
ls -la config/logs/

# Логи Tailscale
ls -la tunnel_system/config/logs/

# Логи веб-приложения (при запуске в debug режиме)
DEBUG=true python web_app/app.py
```

## 🎉 Готово!

Теперь у вас есть полнофункциональная система мониторинга КУБ-1063 с:
- ✅ Безопасным удаленным доступом через Tailscale
- ✅ Веб-интерфейсом с графиками и аналитикой  
- ✅ Автоматической регистрацией устройств
- ✅ Ролевой системой управления доступом
- ✅ Мобильным доступом к данным
- ✅ Централизованным управлением mesh-сетью

### Следующие шаги:
- 📚 Изучите [полную документацию](README.md)
- 🔧 Настройте [RBAC систему](web_app/README.md#rbac-system)
- 📊 Добавьте [дополнительные фермы](#43-подключение-новой-фермы)
- 🔐 Усильте [безопасность](#шаг-5-настройка-безопасности-рекомендуется)

**Нужна помощь?** Создайте issue в репозитории или обратитесь к [документации по устранению неполадок](web_app/README.md#отладка).