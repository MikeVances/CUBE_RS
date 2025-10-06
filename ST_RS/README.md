# 🏭 Stienen RS485 Gateway

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-supported-blue.svg)](Dockerfile)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

Современная система мониторинга контроллеров Stienen через RS485. Полная миграция с C#/.NET на Python с расширенным функционалом.

## ✨ Возможности

- 🔌 **RS485 коммуникация** - Надежная связь с контроллерами Stienen
- 🌐 **Веб-интерфейс** - Современная замена WinForms
- 📊 **SCADA интеграция** - REST API, MQTT, XML, CSV экспорт
- 🖥️ **Кроссплатформенность** - Linux, Windows, macOS
- 🐳 **Docker поддержка** - Простое развертывание
- 📈 **Мониторинг** - Prometheus метрики, Grafana дашборды
- 🧪 **Тестирование** - Комплексные unit и интеграционные тесты

## 🚀 Быстрый старт

### Установка

```bash
# Клонирование репозитория
git clone https://github.com/company/stienen-gateway.git
cd stienen-gateway

# Установка зависимостей
pip install -r requirements.txt

# Или установка пакета
pip install -e .
```

### Первый запуск

```bash
# Создание конфигурации
cp config.example.json config.json

# Проверка доступных портов
python main.py --list-ports

# Тест протокола
python main.py --test-protocol

# Запуск с автоопределением устройств
python main.py --port /dev/ttyUSB0 --devices 1,2,3
```

### Docker

```bash
# Запуск всей системы
docker-compose up -d

# Логи
docker-compose logs -f stienen-gateway

# Веб-интерфейс: http://localhost:8080
# Grafana: http://localhost:3000 (admin/admin)
```

## 📖 Документация

- [Руководство по установке](docs/installation.md)
- [Конфигурация](docs/configuration.md)
- [API документация](docs/api.md)
- [Миграция с C#](docs/migration.md)
- [Развертывание](docs/deployment.md)

## 🔧 Разработка

```bash
# Установка dev зависимостей
make dev-install

# Запуск тестов
make test

# Линтинг и форматирование
make lint
make format

# Локальный запуск
make up
```

## 🏗️ Архитектура

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Контроллеры   │────│   RS485 Gateway  │────│  SCADA системы  │
│    Stienen      │    │      Python      │    │   REST/MQTT     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                       ┌──────────────┐
                       │ Веб-интерфейс │
                       │   FastAPI     │
                       └──────────────┘
```

## 📊 Статус миграции

| Компонент | C# Оригинал | Python | Статус |
|-----------|-------------|--------|---------|
| RS485 протокол | ✅ | ✅ | ✅ Готово |
| Коммуникация | ✅ | ✅ | ✅ Готово |
| Маппинг переменных | ✅ | ✅ | ✅ Готово |
| SCADA экспорт | ✅ | ✅ | ✅ Расширено |
| UI интерфейс | WinForms | Web | ✅ Модернизировано |
| База данных | PostgreSQL | PostgreSQL | ✅ Совместимо |

## 🤝 Вклад в проект

1. Fork репозитория
2. Создайте feature branch (`git checkout -b feature/amazing-feature`)
3. Commit изменения (`git commit -m 'Add amazing feature'`)
4. Push в branch (`git push origin feature/amazing-feature`)
5. Создайте Pull Request

## 📄 Лицензия

Этот проект лицензирован под MIT License - см. [LICENSE](LICENSE) файл.

## 🆘 Поддержка

- 📧 Email: support@company.com
- 📖 Документация: https://stienen-gateway.readthedocs.io/
- 🐛 Issues: https://github.com/company/stienen-gateway/issues

## 🎯 Roadmap

- [ ] OPC-UA интеграция
- [ ] Kubernetes Helm charts
- [ ] Mobile приложение
- [ ] Machine Learning аналитика
- [ ] Multi-tenancy поддержка

---

*Создано с ❤️ для промышленной автоматизации*
