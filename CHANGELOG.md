# 📋 CHANGELOG - История изменений CUBE_RS

## 🚀 v2.0.0 - Tailscale Integration (Текущая версия)

### ✨ Новые функции
- **🌐 Tailscale Mesh Network** - полная интеграция с Tailscale для создания защищенной mesh-сети
- **📱 Device Registry** - система регистрации устройств по аналогии с IXON Cloud
- **👥 RBAC System** - ролевая система управления доступом с 5 предустановленными ролями
- **🎨 Modern Web UI** - обновленный веб-интерфейс на Bootstrap 5 с двумя основными страницами
- **🔐 Enhanced Security** - многоуровневая система безопасности с HMAC подписями и зашифрованными секретами

### 🔧 Улучшения архитектуры
- **Микросервисная архитектура** с разделением на модули web_app, tunnel_system, core
- **Три SQLite базы данных** для разных типов данных (КУБ-1063, устройства, пользователи)
- **Async/await поддержка** для работы с Tailscale API
- **RESTful API** с полным набором endpoints для управления системой
- **Real-time обновления** через WebSocket и автоматические refresh

### 🗄️ Структура баз данных

#### device_registry.db
```sql
-- Зарегистрированные устройства
registered_devices: device_id, hostname, tailscale_ip, status, metadata, tags
-- Ключи авторизации с ограничениями
auth_keys: key_id, key_hash, expires_time, usage_count, max_usage
-- Процесс регистрации
device_registration_requests: request_id, device_hostname, status
```

#### rbac_system.db  
```sql
-- Пользователи и аутентификация
users: user_id, username, email, password_hash, roles, device_groups
-- Роли и разрешения
roles: role_id, name, permissions, is_system_role
-- Группы устройств для управления доступом
device_groups: group_id, name, device_ids, device_types, tags_filter
-- Политики доступа с временными ограничениями  
access_policies: policy_id, device_group_id, role_id, permissions, time_restrictions
```

### 🌐 Новые API Endpoints

#### Tailscale Management
- `GET /api/tailscale/status` - статус mesh-сети
- `GET /api/tailscale/devices` - список устройств
- `GET /api/tailscale/farms` - фермы КУБ-1063
- `POST /api/tailscale/auth-key` - создание ключей

#### Device Registry  
- `POST /api/registry/register` - регистрация устройства
- `GET /api/registry/devices` - управление устройствами
- `POST /api/registry/auth-key` - ключи регистрации
- `GET /api/registry/stats` - статистика

### 📱 Веб-интерфейс
- **Главная страница** (`/`) - Dashboard КУБ-1063 с графиками Chart.js
- **Tailscale страница** (`/tailscale`) - управление mesh-сетью
- **Responsive design** с адаптацией под мобильные устройства
- **Модальные окна** для создания ключей и управления устройствами
- **Real-time индикаторы** статуса подключения и API доступности

---

## 📊 v1.5.0 - P2P Tunnel System

### ✨ Добавлено
- P2P туннели через WebRTC для прямого подключения к фермам
- Tunnel Broker сервер для координации соединений
- Мобильное веб-приложение с красивым интерфейсом
- SQLite база данных для управления пользователями и фермами

### 🔧 Компоненты
- `tunnel_broker.py` - центральный сервер-коммутатор
- `farm_client.py` - клиент фермы с heartbeat
- `mobile_app.py` - мобильное приложение
- WebRTC P2P соединения с шифрованием

### 🏗️ Архитектура
```
📱 Mobile App ←--WebRTC P2P--→ 🏭 Farm Gateway
        ↓                           ↓
    📞 Request connection       📞 Register every 5min  
        ↓                           ↓
        🌐 Tunnel Broker Server (белый IP)
```

---

## 🌟 v1.0.0 - Core System

### ✨ Базовый функционал
- **Modbus TCP/RTU чтение** данных с КУБ-1063
- **SQLite хранение** временных рядов
- **Streamlit Dashboard** для визуализации
- **Telegram Bot** для уведомлений
- **WebSocket сервер** для real-time данных

### 📊 Мониторинг
- Температура внутренняя и целевая
- Влажность относительная  
- CO₂ концентрация
- Уровень вентиляции
- Статистика работы системы

### 🔧 Сервисы
- **Modbus Gateway** (порт 8000)
- **TCP Duplicator** (порт 5022) 
- **WebSocket Server** (порт 8765)
- **MQTT Publisher** для IoT интеграции
- **Dashboard** на Streamlit

---

## 🗂️ Миграция между версиями

### Переход с v1.5 (P2P) на v2.0 (Tailscale)

#### Что сохранилось:
- ✅ Все компоненты core системы (Modbus, Dashboard, Telegram)
- ✅ SQLite базы данных с данными КУБ-1063
- ✅ API Gateway для доступа к данным
- ✅ Мобильное приложение (адаптировано под Tailscale)

#### Что изменилось:
- 🔄 WebRTC P2P → Tailscale mesh VPN
- 🔄 Tunnel Broker → Device Registry + Tailscale Manager
- 🔄 Простая аутентификация → RBAC система
- 🔄 Одна база данных → три специализированные

#### Процесс миграции:
1. **Бэкап данных**: сохраните `kub_data.db` с историческими данными
2. **Настройка Tailscale**: создайте tailnet и получите API ключ  
3. **Обновление кода**: `git pull` последней версии
4. **Запуск новых сервисов**: `python tools/start_all_services.py`
5. **Регистрация устройств**: используйте новый веб-интерфейс

### Обратная совместимость
Legacy компоненты P2P системы сохранены для совместимости:
- `tunnel_broker.py` - оригинальный P2P брокер
- `farm_client.py` - WebRTC клиент
- `mobile_app.py` - P2P мобильное приложение

---

## 🔮 Планы развития (v2.1+)

### 🛣️ Roadmap
- **PWA поддержка** - установка веб-интерфейса как мобильное приложение
- **Advanced Analytics** - предиктивные модели и ML аналитика
- **Multi-tenant** - поддержка нескольких организаций
- **External Integrations** - API для ERP/CRM систем
- **Marketplace** - система плагинов и пользовательских виджетов
- **Mobile Native Apps** - нативные приложения iOS/Android

### 🔧 Технические улучшения
- **Docker containerization** - упрощение развертывания
- **Kubernetes support** - оркестрация в production
- **PostgreSQL/TimescaleDB** - альтернатива SQLite для больших нагрузок
- **Redis caching** - повышение производительности
- **Monitoring stack** - Prometheus/Grafana интеграция

### 🛡️ Безопасность
- **OAuth 2.0/OIDC** - современная аутентификация
- **Hardware security keys** - поддержка FIDO2/WebAuthn  
- **Advanced audit** - детальное журналирование
- **Compliance** - сертификация по промышленным стандартам

---

## 📞 Поддержка и обратная связь

- **Issues**: [GitHub Issues](https://github.com/your-repo/CUBE_RS/issues)
- **Документация**: [README.md](README.md)
- **Быстрый старт**: [TAILSCALE_QUICK_START.md](TAILSCALE_QUICK_START.md)

**Версия**: v2.0.0  
**Дата релиза**: 2024-12-XX  
**Статус**: Stable - готово к production использованию