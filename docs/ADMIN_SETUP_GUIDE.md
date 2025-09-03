# 🔧 РУКОВОДСТВО ПО АДМИНИСТРИРОВАНИЮ CUBE_RS

## 🎯 ОТВЕТ НА ГЛАВНЫЙ ВОПРОС

> **"Как управлять, добавлять пользователей, раздавать им ключи и подключать к их устройствам?"**

### ✅ **РЕШЕНИЕ ГОТОВО!** 

Создана **CLI утилита администрирования** для полного управления системой.

---

## 🚀 БЫСТРЫЙ СТАРТ

### 1. Проверка статуса системы
```bash
python tools/admin_cli.py status
```

### 2. Создание администратора
```bash
python tools/admin_cli.py create-user \
  --username admin \
  --email admin@company.com \
  --full-name "System Administrator" \
  --password secure123 \
  --role "System Administrator" \
  --admin
```

### 3. Создание обычного пользователя
```bash  
python tools/admin_cli.py create-user \
  --username farmer1 \
  --email farmer1@company.com \
  --full-name "Фермер Иванов" \
  --password farm123 \
  --role "Farm Operator"
```

### 4. Генерация ключа для устройства
```bash
python tools/admin_cli.py create-device-key \
  --expires 24 \
  --tags farm production \
  --created-by admin
```

### 5. Просмотр ожидающих регистраций
```bash
python tools/admin_cli.py list-pending
```

### 6. Одобрение регистрации устройства
```bash
python tools/admin_cli.py approve-registration \
  --request-id <REQUEST_ID> \
  --approved-by admin
```

---

## 📋 ПОЛНЫЙ ПРОЦЕСС ПОДКЛЮЧЕНИЯ УСТРОЙСТВА

### Шаг 1: Администратор создает ключ
```bash
python tools/admin_cli.py create-device-key --expires 24 --tags farm
# Результат: tskey-xxxxxxxxxxxxxxxxxxx
```

### Шаг 2: Устройство регистрируется (программно)
На устройстве КУБ-1063 выполняется:
```python
from web_app.device_registry import get_device_registry

registry = get_device_registry()
request_id = registry.create_registration_request(
    auth_key="tskey-xxxxxxxxxxxxxxxxxxx",
    device_hostname="kub-farm-001", 
    device_type="farm",
    device_info={
        "os": "Linux",
        "location": "Теплица №1",
        "capabilities": ["kub1063", "monitoring"]
    },
    tailscale_ip="100.64.1.10"
)
```

### Шаг 3: Администратор одобряет регистрацию
```bash
python tools/admin_cli.py list-pending
python tools/admin_cli.py approve-registration --request-id <ID>
```

### Шаг 4: Устройство получает доступ ✅
Устройство автоматически получает доступ ко всем сервисам системы.

---

## 🔧 ДОСТУПНЫЕ КОМАНДЫ CLI

### Управление пользователями
```bash
# Создание пользователя
python tools/admin_cli.py create-user \
  --username <username> \
  --email <email> \
  --full-name "<Full Name>" \
  --password <password> \
  --role "<Role Name>" \
  [--admin]

# Список пользователей
python tools/admin_cli.py list-users
```

### Управление устройствами
```bash
# Создание ключа авторизации
python tools/admin_cli.py create-device-key \
  [--expires <hours>] \
  [--max-usage <count>] \
  [--tags <tag1> <tag2>] \
  [--created-by <username>]

# Список ожидающих регистраций
python tools/admin_cli.py list-pending

# Одобрение регистрации
python tools/admin_cli.py approve-registration \
  --request-id <request_id> \
  [--approved-by <username>]

# Список устройств
python tools/admin_cli.py list-devices \
  [--type <device_type>] \
  [--status <status>]
```

### Мониторинг системы
```bash
# Статус системы
python tools/admin_cli.py status
```

---

## 👥 РОЛИ ПОЛЬЗОВАТЕЛЕЙ

В системе предустановлены следующие роли:

### **System Administrator**
- Полный доступ ко всем функциям
- Управление пользователями и ролями
- Регистрация устройств
- Системные настройки

### **Farm Administrator** 
- Полный доступ к управлению фермой
- Подключение к устройствам (VPN, VNC, SSH, HTTP)
- Конфигурирование устройств
- Регистрация новых устройств

### **Farm Operator**
- Мониторинг и базовое управление
- Подключение через VNC и HTTP
- API доступ для получения данных
- Просмотр устройств

### **Service Engineer**
- Доступ для обслуживания и диагностики
- SSH доступ к устройствам
- Конфигурирование для ремонта
- VPN и VNC доступ

### **Read Only**
- Только просмотр данных
- API доступ для чтения
- Просмотр статуса устройств

---

## 🔐 УПРАВЛЕНИЕ ДОСТУПОМ

### Создание групп устройств (программно)
```python
from web_app.rbac_system import get_rbac_system

rbac = get_rbac_system()
group_id = rbac.create_device_group(
    name="Production Farms",
    description="Производственные теплицы",
    device_types=["farm"],
    tags_filter=["production"]
)
```

### Назначение прав доступа
```python
policy_id = rbac.create_access_policy(
    name="Farm Operator Access",
    description="Доступ оператора к фермам",
    device_group_id=group_id,
    role_id=operator_role.role_id,
    permissions=[
        "device:view",
        "device:connect", 
        "service:vnc"
    ]
)
```

---

## 🌐 ИНТЕГРАЦИЯ С ВЕБ-ИНТЕРФЕЙСОМ

После создания пользователей они могут войти в систему через:
- **Web Dashboard**: http://localhost:5000
- **Tailscale Dashboard**: http://localhost:5000/tailscale
- **Mobile App**: По Tailscale mesh-сети

### Аутентификация (в разработке)
Текущая система использует упрощенную аутентификацию через session. 
Для продакшена требуется добавить полную систему login/logout.

---

## 📊 ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ

### Сценарий 1: Новая ферма
```bash
# 1. Создаем пользователя-оператора фермы
python tools/admin_cli.py create-user \
  --username farm_operator_1 \
  --email operator1@farm.com \
  --full-name "Иванов Иван Иванович" \
  --password farm2024 \
  --role "Farm Operator"

# 2. Генерируем ключ для устройства фермы
python tools/admin_cli.py create-device-key \
  --expires 48 \
  --tags farm production greenhouse1 \
  --created-by farm_operator_1

# Результат: tskey-abc123...
# Отправляем ключ на устройство фермы

# 3. Ждем регистрации устройства и одобряем
python tools/admin_cli.py list-pending
python tools/admin_cli.py approve-registration --request-id xyz789

# 4. Проверяем статус
python tools/admin_cli.py list-devices --type farm --status active
```

### Сценарий 2: Сервисное обслуживание
```bash
# 1. Создаем временного сервисного инженера
python tools/admin_cli.py create-user \
  --username service_tech \
  --email tech@service.com \
  --full-name "Техник Петров" \
  --password service123 \
  --role "Service Engineer"

# 2. Создаем временный ключ для диагностического устройства
python tools/admin_cli.py create-device-key \
  --expires 8 \
  --max-usage 1 \
  --tags diagnostic service \
  --created-by service_tech
```

---

## 🛡️ БЕЗОПАСНОСТЬ

### Рекомендации:
1. **Используйте сильные пароли** для всех пользователей
2. **Ограничивайте срок действия ключей** (24-48 часов)
3. **Регулярно проверяйте** ожидающие регистрации
4. **Отзывайте доступ** неактивным пользователям
5. **Мониторьте логи** системы безопасности

### Переменные окружения (продакшен):
```bash
export SECRET_KEY="your-production-secret-key"
export TAILSCALE_API_KEY="tskey-api-real-key"
export API_KEY="your-api-key"
export API_SECRET="your-api-secret"
```

---

## ✅ ИТОГО: СИСТЕМА ГОТОВА!

### Что работает:
- ✅ Создание пользователей и ролей
- ✅ Генерация ключей авторизации
- ✅ Регистрация устройств
- ✅ Одобрение регистраций
- ✅ Управление доступом
- ✅ CLI интерфейс администрирования

### Что можно улучшить:
- 🔄 Веб-интерфейс для администраторов
- 🔄 Полная система аутентификации
- 🔄 API эндпоинты для управления

**Система полностью функциональна для управления пользователями и устройствами! 🎉**