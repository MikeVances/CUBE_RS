.PHONY: help build up down logs clean test lint format install dev-install

# Default target
help:
	@echo "Stienen RS485 Gateway - Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  help         - Show this help message"
	@echo "  install      - Install Python dependencies"
	@echo "  dev-install  - Install development dependencies"
	@echo "  test         - Run tests"
	@echo "  lint         - Run linting"
	@echo "  format       - Format code"
	@echo "  build        - Build Docker images"
	@echo "  up           - Start all services"
	@echo "  down         - Stop all services"
	@echo "  logs         - Show logs"
	@echo "  clean        - Clean up containers and volumes"
	@echo "  scan         - Scan for RS485 devices"
	@echo "  monitor      - Monitor RS485 traffic"

# Python development
install:
	pip install -r requirements.txt

dev-install:
	pip install -r requirements.txt
	pip install -e .
	pre-commit install

test:
	python -m pytest tests/ -v --cov=stienen --cov-report=html

lint:
	python -m pylint stienen/
	python -m mypy stienen/

format:
	python -m black stienen/ tests/
	python -m isort stienen/ tests/

# Docker operations
build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

clean:
	docker-compose down -v
	docker system prune -f

# RS485 utilities
scan:
	python monitoring_utilities.py scan /dev/ttyUSB0

monitor:
	python monitoring_utilities.py monitor /dev/ttyUSB0 --duration 60

health:
	python monitoring_utilities.py health --config config.json

# Production deployment
deploy-prod:
	@echo "Deploying to production..."
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Backup
backup:
	@echo "Creating backup..."
	mkdir -p backups/$(shell date +%Y%m%d_%H%M%S)
	docker-compose exec postgres pg_dump -U stienen stienen > backups/$(shell date +%Y%m%d_%H%M%S)/database.sql
	cp -r config backups/$(shell date +%Y%m%d_%H%M%S)/
	cp -r logs backups/$(shell date +%Y%m%d_%H%M%S)/
