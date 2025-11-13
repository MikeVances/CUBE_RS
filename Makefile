# CUBE_RS Industrial IoT Gateway - Makefile
# Удобные команды для разработки и развертывания

.PHONY: help install dev run test clean docker build deploy

# По умолчанию показываем help
.DEFAULT_GOAL := help

help: ## Показать справку по командам
	@echo "🏭 CUBE_RS Industrial IoT Gateway v2.0.0"
	@echo "======================================"
	@echo ""
	@echo "Доступные команды:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Примеры:"
	@echo "  make install     # Установка зависимостей"
	@echo "  make run         # Запуск всех сервисов (по конфигу)"
	@echo "  make run-edge    # Запуск только Edge (ферма)"
	@echo "  make run-server  # Запуск только Server (поставщик)"
	@echo "  make run-app     # Запуск только APP (веб-интерфейс)"
	@echo "  make run-bot     # Запуск только Telegram бота"
	@echo "  make test        # Запуск тестов"
	@echo "  make docker      # Сборка Docker образа"

install: ## Установка зависимостей через Poetry
	@echo "📦 Установка зависимостей..."
	@command -v poetry >/dev/null 2>&1 || { echo "❌ Poetry не установлен. Установите: curl -sSL https://install.python-poetry.org | python3 -"; exit 1; }
	poetry install
	@echo "✅ Зависимости установлены"

install-pip: ## Установка зависимостей через pip (fallback)
	@echo "📦 Установка зависимостей через pip..."
	pip install -r requirements.txt
	@echo "✅ Зависимости установлены"

setup: ## Первоначальная настройка проекта
	@echo "🔧 Настройка проекта..."
	@if [ ! -f .env ]; then \
		echo "📝 Создание .env файла из примера..."; \
		cp .env.example .env; \
		echo "⚠️ Отредактируйте .env файл перед запуском!"; \
	fi
	@mkdir -p logs data config
	@echo "✅ Проект настроен"

check: ## Проверка окружения
	@command -v poetry >/dev/null 2>&1 && poetry run python start.py --check || python start.py --check

run: ## Запуск всех сервисов
	@echo "🚀 Запуск всех сервисов CUBE_RS..."
	@command -v poetry >/dev/null 2>&1 && poetry run python start.py all || python start.py all

run-gateway: ## Запуск только Modbus Gateway
	@echo "🚀 Запуск Modbus Gateway..."
	@command -v poetry >/dev/null 2>&1 && poetry run python start.py gateway || python start.py gateway

run-api: ## Запуск только API Gateway  
	@echo "🚀 Запуск API Gateway..."
	@command -v poetry >/dev/null 2>&1 && poetry run python start.py api || python start.py api

run-bot: ## Запуск только Telegram Bot
	@echo "🚀 Запуск Telegram Bot..."
	@command -v poetry >/dev/null 2>&1 && poetry run python start.py bot || python start.py bot

run-dashboard: ## Запуск только Web Dashboard
	@echo "🚀 Запуск Web Dashboard..."
	@command -v poetry >/dev/null 2>&1 && poetry run python start.py dashboard || python start.py dashboard

dev: ## Запуск в режиме разработки
	@echo "🔧 Запуск в режиме разработки..."
	@export ENVIRONMENT=development && $(MAKE) run

test: ## Запуск тестов
	@echo "🧪 Запуск тестов..."
	@command -v poetry >/dev/null 2>&1 && poetry run pytest || python -m pytest
	@echo "✅ Тесты завершены"

test-coverage: ## Запуск тестов с coverage
	@echo "🧪 Запуск тестов с покрытием..."
	@command -v poetry >/dev/null 2>&1 && poetry run pytest --cov=. --cov-report=html || python -m pytest --cov=. --cov-report=html
	@echo "📊 Отчет о покрытии: htmlcov/index.html"

lint: ## Проверка качества кода
	@echo "🔍 Проверка качества кода..."
	@command -v poetry >/dev/null 2>&1 && { \
		echo "🔧 Ruff linting..."; \
		poetry run ruff check . || true; \
		echo "🎨 Black formatting..."; \
		poetry run black --check . || true; \
		echo "📏 MyPy type checking..."; \
		poetry run mypy . || true; \
	} || echo "⚠️ Poetry не найден, пропускаем линтинг"

format: ## Автоформатирование кода
	@echo "🎨 Форматирование кода..."
	@command -v poetry >/dev/null 2>&1 && { \
		poetry run black .; \
		poetry run isort .; \
	} || echo "⚠️ Poetry не найден"

clean: ## Очистка временных файлов
	@echo "🧹 Очистка временных файлов..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf dist/
	rm -rf build/
	@echo "✅ Очистка завершена"

docker: ## Сборка Docker образа
	@echo "🐳 Сборка Docker образа..."
	docker build -t cube-rs:latest .
	@echo "✅ Docker образ собран: cube-rs:latest"

docker-run: ## Запуск в Docker контейнере
	@echo "🐳 Запуск в Docker..."
	@if [ ! -f .env ]; then \
		echo "❌ .env файл не найден. Создайте его из .env.example"; \
		exit 1; \
	fi
	docker run -d \
		--name cube-rs \
		--env-file .env \
		-p 5023:5023 \
		-p 8000:8000 \
		-v ./data:/app/data \
		-v ./logs:/app/logs \
		cube-rs:latest
	@echo "✅ Контейнер запущен. Логи: docker logs -f cube-rs"

docker-compose: ## Запуск через Docker Compose
	@echo "🐳 Запуск через Docker Compose..."
	docker-compose up -d
	@echo "✅ Все сервисы запущены через Docker Compose"

docker-stop: ## Остановка Docker сервисов
	@echo "🛑 Остановка Docker сервисов..."
	docker-compose down || docker stop cube-rs || true
	@echo "✅ Docker сервисы остановлены"

logs: ## Просмотр логов
	@echo "📋 Просмотр логов..."
	@if docker ps | grep -q cube-rs; then \
		echo "Docker логи:"; \
		docker logs -f cube-rs; \
	elif [ -f logs/gateway1.log ]; then \
		echo "Локальные логи:"; \
		tail -f logs/gateway1.log; \
	else \
		echo "❌ Логи не найдены"; \
	fi

health: ## Проверка состояния сервисов
	@echo "⚕️ Проверка состояния сервисов..."
	@curl -s http://localhost:5023/health/detailed | python -m json.tool || echo "❌ Modbus Gateway недоступен"
	@curl -s http://localhost:8000/api/health | python -m json.tool || echo "❌ API Gateway недоступен"

backup: ## Создание бэкапа данных
	@echo "💾 Создание бэкапа..."
	@mkdir -p backups/$(shell date +%Y%m%d_%H%M%S)
	@cp -r data/ backups/$(shell date +%Y%m%d_%H%M%S)/ 2>/dev/null || echo "Нет данных для бэкапа"
	@cp config/app_config.yaml backups/$(shell date +%Y%m%d_%H%M%S)/ 2>/dev/null || echo "Нет конфига для бэкапа"
	@echo "✅ Бэкап создан в backups/"

deploy: ## Развертывание в продакшен (требует настройки)
	@echo "🚀 Развертывание в продакшен..."
	@echo "⚠️ Убедитесь что:"
	@echo "  1. Все секреты настроены в .env"
	@echo "  2. База данных создана"
	@echo "  3. Фаервол настроен"
	@echo "  4. SSL сертификаты установлены"
	@read -p "Продолжить? [y/N]: " confirm && [ "$$confirm" = "y" ] || exit 1
	@export ENVIRONMENT=production && $(MAKE) docker-compose
	@echo "✅ Развертывание завершено"

migrate-secrets: ## Миграция секретов в переменные окружения
	@echo "🔐 Миграция секретов..."
	python scripts/migrate_secrets.py
	@echo "✅ Секреты мигрированы"

# Служебные цели
.PHONY: _check-poetry
_check-poetry:
	@command -v poetry >/dev/null 2>&1 || { echo "❌ Poetry не установлен"; exit 1; }
run-edge: ## Запуск только Edge (ферма)
	@echo "🚀 Запуск Edge (RS485 + gateway + optional bot/dashboard)..."
	@command -v poetry >/dev/null 2>&1 && poetry run python EDGE/start_edge.py || python EDGE/start_edge.py

scan-slaves: ## Сканирование Modbus slave ID на RS485
	@echo "🔍 Сканирование RS485 устройств..."
	@command -v poetry >/dev/null 2>&1 && poetry run python EDGE/tools/scan_slave_ids.py $(ARGS) || python EDGE/tools/scan_slave_ids.py $(ARGS)

run-server: ## Запуск только Server (поставщик)
	@echo "🚀 Запуск Server (API + WS + optional bot)..."
	@command -v poetry >/dev/null 2>&1 && poetry run python start_server.py || python start_server.py

run-app: ## Запуск только APP (веб-интерфейс)
	@echo "🚀 Запуск APP (web_interface via uvicorn)..."
	@command -v poetry >/dev/null 2>&1 && poetry run python start_app.py || python start_app.py
