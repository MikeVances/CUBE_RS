# 📦 Структура развертывания CUBE_RS

Проект реструктурирован для реального продакшен развертывания на 3 независимых системах.

## 🏗️ Новая структура проекта

```
CUBE_RS/
├── deploy_gateway/          # 📱 Пакет для развертывания на Gateway устройствах
│   ├── deploy.sh           # Скрипт автоматической установки
│   ├── requirements.txt    # Python зависимости для gateway
│   ├── gateway/           # Код автоматической регистрации
│   ├── modbus/            # Modbus TCP/RTU драйверы
│   ├── security/          # MITM защита и certificate pinning
│   └── monitoring/        # Локальный мониторинг устройства
│
├── deploy_webapp/          # 🌐 Веб-приложение (админ панель)
│   ├── deploy.sh          # Скрипт установки веб-приложения
│   ├── requirements.txt   # Flask, Gunicorn зависимости
│   ├── web_app/          # Flask приложение с RBAC
│   ├── tools/            # CLI утилиты администратора
│   └── security/         # Системы безопасности
│
├── deploy_server/         # 🖥️  Серверное приложение (бэкенд API)
│   ├── deploy.sh         # Скрипт установки сервера
│   ├── requirements.txt  # FastAPI, SQLAlchemy зависимости
│   ├── server_app/       # FastAPI API сервер
│   ├── monitoring/       # Центральный мониторинг безопасности
│   └── security/         # Системы защиты от MITM
│
├── docs/                 # 📚 Вся техническая документация
│   ├── README.md        # Навигация по документации
│   ├── MITM_PROTECTION_COMPLETED.md
│   ├── PRODUCTION_SYSTEM_COMPLETED.md
│   └── [все остальные .md файлы]
│
├── README.md            # 🚀 Главный README с инструкциями
└── [исходные папки...]  # Оригинальная структура разработки
```

## 🚀 Быстрое развертывание

### 1. Серверное приложение (хостинг/VPS)
```bash
cd deploy_server
sudo ./deploy.sh
systemctl start cube-server
# API доступен: http://server:8000
```

### 2. Веб-приложение (отдельный хостинг)  
```bash
cd deploy_webapp  
sudo ./deploy.sh
systemctl start cube-webapp
# Админка доступна: http://webapp:5000
```

### 3. Gateway устройства (железо на фермах)
```bash  
cd deploy_gateway
sudo ./deploy.sh
# Автоматическая регистрация с сервером
```

## 🔧 Что включено в каждый пакет

### 📱 deploy_gateway/
**Назначение**: Установка на промышленные gateway устройства
- ✅ Автоматическая регистрация устройств
- ✅ Сбор данных с КУБ-1063 через Modbus
- ✅ Hardware binding и привязка к железу
- ✅ Certificate pinning для защиты от MITM
- ✅ Локальный мониторинг безопасности
- ✅ Systemd сервис для автозапуска

### 🌐 deploy_webapp/ 
**Назначение**: Веб-интерфейс администратора
- ✅ Flask веб-приложение с Bootstrap UI
- ✅ RBAC система управления пользователями
- ✅ Управление производственными партиями
- ✅ CLI утилиты (admin_cli.py, production_cli.py)
- ✅ Система certificate management
- ✅ Nginx конфигурация для HTTPS
- ✅ Gunicorn для production запуска

### 🖥️ deploy_server/
**Назначение**: Центральный API сервер
- ✅ FastAPI приложение с автодокументацией
- ✅ Endpoints для регистрации устройств
- ✅ Центральный мониторинг безопасности  
- ✅ Network security monitoring
- ✅ API для активации устройств в поле
- ✅ Система алертов и уведомлений
- ✅ Uvicorn с multiple workers

## 🔐 Безопасность во всех компонентах

### Gateway → Server:
- Certificate pinning
- Hardware binding  
- Mutual TLS аутентификация
- Зашифрованные auth keys

### WebApp → Server:
- HTTPS с SSL сертификатами
- RBAC авторизация
- CSRF защита
- Security headers

### Server защита:
- Rate limiting
- MITM detection  
- Network monitoring
- Security alerts

## 📋 Системные требования

### Минимальные:
- **Python 3.8+**
- **SQLite3** (встроен)
- **Linux/macOS/Windows**
- **512MB RAM** (gateway)
- **1GB RAM** (webapp/server)

### Рекомендуемые для продакшена:
- **PostgreSQL** (вместо SQLite)
- **Redis** (кэширование)  
- **Nginx** (reverse proxy)
- **SSL сертификаты**
- **Firewall** настройки

## 🎯 Преимущества новой структуры

✅ **Независимое развертывание** - каждый компонент на своем сервере
✅ **Минимальные зависимости** - только необходимые пакеты в каждом deploy
✅ **Простая установка** - один скрипт `./deploy.sh`
✅ **Production ready** - systemd сервисы, логирование, мониторинг
✅ **Масштабируемость** - можно запускать множество экземпляров
✅ **Безопасность** - изолированные компоненты с защитой
✅ **Документация** - все .md файлы организованы в docs/

## 🔗 Связь между компонентами

```
Gateway Device           Web Application         Server API
     │                         │                     │
     ├─ Modbus КУБ-1063       ├─ Admin UI            ├─ Device Registry
     ├─ Auto Registration     ├─ RBAC System         ├─ Security Monitor  
     ├─ Hardware Binding      ├─ Production CLI      ├─ Network Monitor
     └─ Certificate Pinning   └─ Certificate Mgmt    └─ Alert System
     │                         │                     │
     └─────────────── HTTPS с mTLS ──────────────────┘
```

## 🚀 Готово к продакшену!

Система теперь готова к развертыванию в реальной промышленной среде с:
- **Тысячами gateway устройств**
- **Множественными администраторами** 
- **Центральным мониторингом**
- **Enterprise безопасностью**