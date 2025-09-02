# CUBE_RS — Промышленная система мониторинга КУБ-1063

Полнофункциональная система для удаленного мониторинга и управления контроллерами КУБ-1063 через защищенную Tailscale mesh-сеть с ролевым управлением доступом.

## 🌟 Ключевые особенности

- **🌐 Web Dashboard** — современный веб-интерфейс с графиками и аналитикой
- **🔒 Tailscale Integration** — безопасная mesh-сеть для удаленного доступа  
- **👥 RBAC System** — детальное управление правами доступа
- **📱 Device Registry** — регистрация и управление устройствами
- **🤖 Telegram Bot** — уведомления и удаленное управление
- **📊 Real-time Data** — мониторинг в реальном времени

## 🚀 Быстрый старт

### Простой запуск (без Tailscale)
```bash
# 1. Установка зависимостей
pip install -r requirements.txt

# 2. Запуск системы
python tools/start_all_services.py

# 3. Веб-интерфейс
открыть http://localhost:5000
```

### Полнофункциональная система с Tailscale
Для развертывания mesh-сети с удаленным доступом следуйте подробной инструкции:

📖 **[TAILSCALE_QUICK_START.md](TAILSCALE_QUICK_START.md)** - полная пошаговая инструкция

## 🏗️ Архитектура системы

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web App       │    │  Tunnel System   │    │   Core System   │
│  - Dashboard    │◄──►│   (Tailscale)    │◄──►│   (Modbus)      │
│  - RBAC         │    │  - Mesh Network  │    │  - КУБ-1063     │
│  - Registry     │    │  - Device Mgmt   │    │  - Telegram     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 📊 Компоненты системы

### Core Services
- **🧲 Modbus Gateway** — чтение данных КУБ-1063 (порт 8000)
- **💾 Data Storage** — SQLite базы данных с временными рядами
- **🛰️ WebSocket Server** — real-time данные (порт 8765)
- **🤖 Telegram Bot** — уведомления и команды

### Web Application  
- **🌐 Flask Web App** — веб-интерфейс (порт 5000)
- **📊 Dashboard** — графики температуры, влажности, CO₂, вентиляции
- **🔐 Authentication** — система пользователей и ролей
- **📱 Device Management** — регистрация и управление устройствами

### Tailscale Network
- **🌐 Mesh Network** — защищенная VPN-сеть между устройствами
- **🔑 Device Registry** — автоматическая регистрация ферм
- **👥 Access Control** — детальное управление доступом
- **📈 Network Monitoring** — мониторинг состояния сети

## 🛠️ Управление системой

### Запуск всех сервисов
```bash
python tools/start_all_services.py
```

### Остановка всех сервисов
```bash
python tools/stop_all_services.py
```

### Проверка статуса
```bash
python tools/check_services_status.py
```

### Экстренная остановка
```bash
python tools/kill_all.py
```

## 📁 Структура проекта

```
CUBE_RS/
├── web_app/                          # Flask веб-приложение
│   ├── app.py                        # Основное веб-приложение
│   ├── tailscale_integration.py      # Интеграция с Tailscale
│   ├── device_registry.py            # Система регистрации устройств
│   ├── rbac_system.py               # Система управления доступом
│   └── templates/                    # HTML шаблоны
├── tunnel_system/                    # Tailscale mesh система
│   ├── tailscale_manager.py          # Управление Tailscale
│   ├── tailscale_farm_client.py      # Клиент фермы
│   └── tailscale_discovery_service.py # Обнаружение устройств  
├── modbus/                          # Modbus TCP система
│   ├── gateway.py                   # Modbus Gateway
│   ├── unified_system.py            # Единая система чтения
│   └── modbus_storage.py            # Хранение данных
├── telegram_bot/                   # Telegram бот
│   ├── bot_main.py                 # Основная логика бота
│   ├── bot_permissions.py          # Система разрешений
│   └── secure_config.py            # Защищенная конфигурация
├── core/                           # Базовые модули
│   ├── security_manager.py         # Менеджер безопасности
│   └── config_manager.py           # Менеджер конфигурации
├── tools/                          # Утилиты управления
│   ├── start_all_services.py       # Запуск всех сервисов
│   ├── stop_all_services.py        # Остановка сервисов
│   └── production_audit.py         # Аудит системы
└── config/                         # Конфигурация и секреты
    ├── app_config.yaml             # Основная конфигурация
    └── secrets/                    # Зашифрованные секреты
```

## 🌐 Веб-интерфейс

### Основные страницы
- **`/`** — Dashboard мониторинга КУБ-1063
  - Графики температуры, влажности, CO₂, вентиляции
  - Статистика системы и история данных
  - Real-time обновление каждые 30 секунд

- **`/tailscale`** — Управление Tailscale mesh-сетью  
  - Список всех устройств в сети
  - Управление фермами КУБ-1063
  - Создание ключей авторизации
  - Проверка подключения устройств

### API Endpoints

#### КУБ-1063 Data API
- `GET /api/status` — статус подключения к Gateway
- `GET /api/data/current` — текущие показания  
- `GET /api/data/history` — исторические данные
- `GET /api/data/statistics` — статистика работы

#### Tailscale Management API  
- `GET /api/tailscale/status` — статус mesh-сети
- `GET /api/tailscale/devices` — список устройств
- `GET /api/tailscale/farms` — список ферм  
- `POST /api/tailscale/auth-key` — создание ключей

#### Device Registry API
- `POST /api/registry/register` — регистрация устройства
- `GET /api/registry/devices` — зарегистрированные устройства
- `POST /api/registry/auth-key` — создание ключа регистрации
- `GET /api/registry/stats` — статистика реестра

## 📄 Документация

### Основная документация
- [CHANGELOG.md](CHANGELOG.md) — история изменений и новые функции
- [README_SERVICES.md](README_SERVICES.md) — управление сервисами
- [README_LAUNCH.md](README_LAUNCH.md) — инструкция по запуску  
- [README_CONFIG.md](README_CONFIG.md) — конфигурация системы
- [ModScan_Instructions.md](ModScan_Instructions.md) — инструкция по ModScan

### Технические документы
- [КУБ-1063_modbus registers.md](Cube-1063_modbus%20registers.md) — регистры Modbus
- [КУБ-1063_error_codes.md](КУБ-1063_error_codes.md) — коды ошибок
- [web_app/README.md](web_app/README.md) — веб-приложение
- [tunnel_system/README.md](tunnel_system/README.md) — Tailscale система

### Архитектурные документы  
- [TAILSCALE_QUICK_START.md](TAILSCALE_QUICK_START.md) — пошаговая настройка Tailscale
- [tunnel_system/TAILSCALE_ARCHITECTURE.md](tunnel_system/TAILSCALE_ARCHITECTURE.md) — архитектура Tailscale
- [tunnel_system/TAILSCALE_DEPLOYMENT.md](tunnel_system/TAILSCALE_DEPLOYMENT.md) — развертывание
- [TUNNEL_DEPLOYMENT_READY.md](TUNNEL_DEPLOYMENT_READY.md) — готовность к развертыванию

## 🏁 Текущее состояние

✅ **Работает:**
- Web Dashboard на Flask с Bootstrap UI
- Tailscale mesh-сеть для удаленного доступа
- RBAC система с ролевым управлением  
- Device Registry для автоматической регистрации
- Modbus Gateway для чтения КУБ-1063
- Telegram Bot с уведомлениями
- WebSocket для real-time данных
- Система безопасности и аудита

🔧 **В разработке:**
- Mobile PWA приложение  
- Advanced аналитика и предиктивные модели
- Интеграция с внешними системами (ERP/CRM)
- Marketplace для пользовательских виджетов

## 🛡️ Безопасность

### Уровни защиты
- **Шифрование** — все секреты зашифрованы AES-256
- **HMAC подписи** — защита API от подделки запросов
- **Tailscale VPN** — зашифрованная mesh-сеть
- **RBAC система** — детальные права доступа  
- **Audit logging** — журналирование всех действий
- **Auth keys** — временные ключи с ограничениями

### Переменные окружения
```bash
# Основное приложение
GATEWAY_URL=http://localhost:8000
API_KEY=your-api-key  
API_SECRET=your-api-secret

# Tailscale интеграция
TAILSCALE_ENABLED=true
TAILSCALE_TAILNET=your-tailnet.ts.net
TAILSCALE_API_KEY=tskey-api-xxxxxxxxxx

# Web приложение
SECRET_KEY=your-flask-secret-key
DEBUG=false
PORT=5000
```

## ⚠️ Важные замечания

1. **Перед запуском** убедитесь в наличии подключения к КУБ-1063
2. **Tailscale** требует настройки API ключа для полной функциональности  
3. **Для production** используйте HTTPS и настройте firewall
4. **Логи** сохраняются в `config/logs/` и `tunnel_system/config/logs/`
5. **Базы данных** автоматически создаются при первом запуске