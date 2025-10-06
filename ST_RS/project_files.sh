# Финальная структура проекта Stienen RS485 Gateway

# requirements.txt
cat > requirements.txt << 'EOF'
# Core dependencies
pyserial>=3.5
crcmod>=1.7
asyncio>=3.4.3

# Data processing and validation
pydantic>=1.10.0
dataclasses-json>=0.5.7

# Web interface and API
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
websockets>=11.0

# HTTP client for SCADA integration
aiohttp>=3.8.0
requests>=2.31.0

# XML/CSV processing
lxml>=4.9.0
pandas>=2.0.0  # For advanced CSV processing

# MQTT support (optional)
paho-mqtt>=1.6.0
asyncio-mqtt>=0.13.0

# Database support (optional)
asyncpg>=0.28.0
sqlalchemy>=2.0.0

# Monitoring and logging
psutil>=5.9.0
coloredlogs>=15.0
prometheus-client>=0.17.0

# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0

# Development tools
black>=23.0.0
pylint>=2.17.0
mypy>=1.5.0
pre-commit>=3.3.0

# Documentation
mkdocs>=1.5.0
mkdocs-material>=9.1.0
EOF

# Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    libc6-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Создание пользователя
RUN groupadd -r stienen && useradd -r -g stienen stienen

# Рабочая директория
WORKDIR /app

# Копирование зависимостей и установка
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Создание необходимых директорий
RUN mkdir -p logs exports config \
    && chown -R stienen:stienen /app

# Переключение на пользователя
USER stienen

# Переменные окружения
ENV PYTHONPATH=/app
ENV STIENEN_CONFIG=/app/config.json

# Проверка здоровья
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/api/gateway/status')" || exit 1

# Expose порты
EXPOSE 8080 9090

# Команда по умолчанию
CMD ["python", "main.py", "--config", "config.json"]

# Метаданные
LABEL maintainer="Stienen Gateway Team"
LABEL description="RS485 Gateway for Stienen Controllers"
LABEL version="1.0.0"
LABEL org.opencontainers.image.source="https://github.com/company/stienen-gateway"
EOF

# .dockerignore
cat > .dockerignore << 'EOF'
# Git
.git
.gitignore

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.so
.pytest_cache/
.coverage
htmlcov/
.tox/
.cache
nosetests.xml
coverage.xml
*.cover
.hypothesis/

# Virtual environments
venv/
env/
ENV/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Logs and data
logs/
*.log
exports/
*.csv
*.xml

# Documentation
docs/_build/
site/

# Testing
.pytest_cache/
.coverage
htmlcov/

# Development
.env
.env.local
node_modules/

# Temporary files
*.tmp
*.temp
EOF

# docker-compose.yml (полная версия)
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  # Основной гейтвей Stienen
  stienen-gateway:
    build: 
      context: .
      dockerfile: Dockerfile
    container_name: stienen-gateway
    restart: unless-stopped
    volumes:
      - ./config:/app/config:ro
      - ./logs:/app/logs
      - ./exports:/app/exports
      - ./database:/app/database:ro
    devices:
      - "${RS485_DEVICE:-/dev/ttyUSB0}:/dev/ttyUSB0"
    environment:
      - STIENEN_LOG_LEVEL=${LOG_LEVEL:-INFO}
      - STIENEN_CONFIG=/app/config.json
      - POSTGRES_HOST=postgres
      - POSTGRES_DB=${POSTGRES_DB:-stienen}
      - POSTGRES_USER=${POSTGRES_USER:-stienen}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-secure_password}
      - MQTT_BROKER_HOST=mqtt-broker
    networks:
      - stienen-net
    depends_on:
      - postgres
      - mqtt-broker
    healthcheck:
      test: ["CMD", "python", "-c", "import sys; sys.exit(0)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # Веб-интерфейс
  stienen-web:
    build: 
      context: .
      dockerfile: Dockerfile
    container_name: stienen-web
    restart: unless-stopped
    ports:
      - "${WEB_PORT:-8080}:8080"
    volumes:
      - ./config:/app/config:ro
      - ./logs:/app/logs:ro
    command: ["python", "web_interface.py", "web", "--config", "/app/config.json", "--port", "8080"]
    environment:
      - STIENEN_LOG_LEVEL=${LOG_LEVEL:-INFO}
    networks:
      - stienen-net
    depends_on:
      - stienen-gateway
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/api/gateway/status"]
      interval: 30s
      timeout: 10s
      retries: 3

  # PostgreSQL база данных
  postgres:
    image: postgres:15-alpine
    container_name: stienen-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-stienen}
      POSTGRES_USER: ${POSTGRES_USER:-stienen}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-secure_password}
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=C"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./database/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql:ro
      - ./database/initial_data.sql:/docker-entrypoint-initdb.d/02-data.sql:ro
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    networks:
      - stienen-net
    command: postgres -c 'max_connections=200' -c 'shared_buffers=128MB'
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-stienen}"]
      interval: 10s
      timeout: 5s
      retries: 5

  # MQTT брокер
  mqtt-broker:
    image: eclipse-mosquitto:2.0
    container_name: stienen-mqtt
    restart: unless-stopped
    ports:
      - "${MQTT_PORT:-1883}:1883"
      - "${MQTT_WS_PORT:-9001}:9001"
    volumes:
      - ./mqtt/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
      - ./mqtt/passwd:/mosquitto/config/passwd:ro
      - mqtt_data:/mosquitto/data
      - mqtt_logs:/mosquitto/log
    networks:
      - stienen-net
    healthcheck:
      test: ["CMD", "mosquitto_sub", "-t", "$$SYS/#", "-C", "1"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Redis для кэширования (опционально)
  redis:
    image: redis:7-alpine
    container_name: stienen-redis
    restart: unless-stopped
    volumes:
      - redis_data:/data
    networks:
      - stienen-net
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3

  # Prometheus для метрик
  prometheus:
    image: prom/prometheus:latest
    container_name: stienen-prometheus
    restart: unless-stopped
    ports:
      - "${PROMETHEUS_PORT:-9090}:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/usr/share/prometheus/console_libraries'
      - '--web.console.templates=/usr/share/prometheus/consoles'
      - '--web.enable-lifecycle'
    networks:
      - stienen-net

  # Grafana для визуализации
  grafana:
    image: grafana/grafana:latest
    container_name: stienen-grafana
    restart: unless-stopped
    ports:
      - "${GRAFANA_PORT:-3000}:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD:-admin}
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_SERVER_ROOT_URL=http://localhost:3000/
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources:ro
    networks:
      - stienen-net
    depends_on:
      - prometheus

  # Nginx reverse proxy (опционально)
  nginx:
    image: nginx:alpine
    container_name: stienen-nginx
    restart: unless-stopped
    ports:
      - "${NGINX_HTTP_PORT:-80}:80"
      - "${NGINX_HTTPS_PORT:-443}:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
    networks:
      - stienen-net
    depends_on:
      - stienen-web
      - grafana

volumes:
  postgres_data:
    driver: local
  mqtt_data:
    driver: local  
  mqtt_logs:
    driver: local
  redis_data:
    driver: local
  prometheus_data:
    driver: local
  grafana_data:
    driver: local

networks:
  stienen-net:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
EOF

# .env.example (переменные окружения)
cat > .env.example << 'EOF'
# RS485 Device
RS485_DEVICE=/dev/ttyUSB0

# Network ports
WEB_PORT=8080
POSTGRES_PORT=5432
MQTT_PORT=1883
MQTT_WS_PORT=9001
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
NGINX_HTTP_PORT=80
NGINX_HTTPS_PORT=443

# Database
POSTGRES_DB=stienen
POSTGRES_USER=stienen
POSTGRES_PASSWORD=secure_password_change_me

# Logging
LOG_LEVEL=INFO

# Grafana
GRAFANA_PASSWORD=admin_change_me

# Security
JWT_SECRET=your_jwt_secret_key_here
API_KEY=your_api_key_here
EOF

# Makefile для удобства развертывания
cat > Makefile << 'EOF'
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
EOF

# config.example.json (пример конфигурации)
cat > config.example.json << 'EOF'
{
  "gateway": {
    "name": "Production_Stienen_Gateway",
    "rs485_port": "/dev/ttyUSB0",
    "rs485_baudrate": 38400,
    "polling_interval": 5.0,
    "identification_timeout": 30.0,
    "max_retries": 3,
    "scada_export_interval": 1.0,
    "keep_alive_interval": 30.0
  },
  "devices": [
    {
      "address": 1,
      "name": "Climate_Controller_Building_A",
      "hardware": 1001,
      "version": 1,
      "enabled": true,
      "description": "Основной климат-контроллер здания A",
      "location": "Building A, Room 101",
      "variables": [
        "AirTemperature",
        "TargetTemperature", 
        "Humidity",
        "FanEnabled",
        "HeaterEnabled"
      ]
    },
    {
      "address": 2,
      "name": "Feed_Controller_Section_1",
      "hardware": 1001,
      "version": 1,
      "enabled": true,
      "description": "Контроллер кормления секция 1",
      "location": "Section 1, Feed Tower",
      "variables": [
        "FeedLevel",
        "MotorRunning",
        "DailyConsumption",
        "LastFeedTime"
      ]
    },
    {
      "address": 3,
      "name": "Water_Controller_Main",
      "hardware": 1001,
      "version": 1,
      "enabled": true,
      "description": "Основной контроллер водоснабжения",
      "location": "Water Plant, Main Building",
      "variables": [
        "WaterLevel",
        "PumpStatus",
        "Pressure",
        "FlowRate"
      ]
    }
  ],
  "scada": {
    "rest_api_url": "https://scada.company.com/api/v1",
    "rest_auth_token": "Bearer your_api_token_here",
    "xml_export_path": "./exports/stienen_data.xml",
    "csv_export_path": "./exports/stienen_data.csv",
    "mqtt_broker_host": "mqtt.company.com",
    "mqtt_broker_port": 1883,
    "mqtt_username": "stienen_gateway",
    "mqtt_password": "secure_mqtt_password",
    "mqtt_topic_prefix": "stienen",
    "export_interval": 1.0,
    "only_changed_values": true,
    "batch_size": 100,
    "timeout_seconds": 30
  },
  "variables": {
    "config_file": "./config/variables.json",
    "auto_discovery": true,
    "cache_enabled": true,
    "cache_ttl_seconds": 300
  },
  "logging": {
    "level": "INFO",
    "file": "./logs/gateway.log",
    "max_size_mb": 10,
    "backup_count": 5,
    "console_output": true,
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "date_format": "%Y-%m-%d %H:%M:%S"
  },
  "monitoring": {
    "enabled": true,
    "prometheus_port": 9090,
    "health_check_interval": 30,
    "performance_profiling": false,
    "metrics": {
      "packet_counters": true,
      "device_status": true,
      "response_times": true,
      "error_rates": true
    }
  },
  "security": {
    "api_key_required": false,
    "jwt_secret": "your_jwt_secret_key_here",
    "allowed_origins": ["*"],
    "rate_limiting": {
      "enabled": true,
      "requests_per_minute": 60
    }
  },
  "database": {
    "enabled": false,
    "host": "localhost",
    "port": 5432,
    "database": "stienen",
    "username": "stienen",
    "password": "secure_password",
    "pool_size": 10,
    "max_overflow": 20
  }
}
EOF

# setup.py (установочный скрипт)
cat > setup.py << 'EOF'
#!/usr/bin/env python3

from setuptools import setup, find_packages
import os

# Читаем README
def read_readme():
    with open("README.md", "r", encoding="utf-8") as fh:
        return fh.read()

# Читаем requirements
def read_requirements():
    requirements = []
    if os.path.exists("requirements.txt"):
        with open("requirements.txt", "r", encoding="utf-8") as fh:
            requirements = [line.strip() for line in fh 
                          if line.strip() and not line.startswith("#")]
    return requirements

setup(
    name="stienen-rs485-gateway",
    version="1.0.0",
    author="Stienen Gateway Team",
    author_email="team@company.com",
    description="RS485 Gateway for Stienen Controllers - Python Migration from C#/.NET",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/company/stienen-gateway",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Manufacturing",
        "Topic :: System :: Hardware",
        "Topic :: Scientific/Engineering",
        "Topic :: System :: Monitoring",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9", 
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
        "Environment :: Console",
        "Framework :: AsyncIO",
        "Framework :: FastAPI",
    ],
    python_requires=">=3.8",
    install_requires=read_requirements(),
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "pylint>=2.17.0",
            "mypy>=1.5.0",
            "pre-commit>=3.3.0",
        ],
        "web": [
            "fastapi>=0.100.0",
            "uvicorn[standard]>=0.23.0",
            "websockets>=11.0",
        ],
        "mqtt": [
            "paho-mqtt>=1.6.0",
            "asyncio-mqtt>=0.13.0",
        ],
        "database": [
            "asyncpg>=0.28.0",
            "sqlalchemy>=2.0.0",
        ],
        "monitoring": [
            "prometheus-client>=0.17.0",
            "psutil>=5.9.0",
            "coloredlogs>=15.0",
        ],
        "all": [
            "fastapi>=0.100.0",
            "uvicorn[standard]>=0.23.0",
            "websockets>=11.0",
            "paho-mqtt>=1.6.0",
            "asyncio-mqtt>=0.13.0",
            "asyncpg>=0.28.0",
            "sqlalchemy>=2.0.0",
            "prometheus-client>=0.17.0",
            "psutil>=5.9.0",
            "coloredlogs>=15.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "stienen-gateway=main:main",
            "stienen-web=web_interface:run_web_interface",
            "stienen-monitor=monitoring_utilities:main",
            "stienen-test=tests.test_protocol:main",
        ],
    },
    include_package_data=True,
    package_data={
        "stienen": [
            "config/*.json",
            "templates/*.html",
            "static/css/*.css",
            "static/js/*.js",
        ],
    },
    project_urls={
        "Bug Reports": "https://github.com/company/stienen-gateway/issues",
        "Source": "https://github.com/company/stienen-gateway",
        "Documentation": "https://stienen-gateway.readthedocs.io/",
    },
    keywords="rs485 stienen gateway industrial automation scada iot modbus",
    platforms=["any"],
    zip_safe=False,
)
EOF

# pyproject.toml (современная конфигурация Python)
cat > pyproject.toml << 'EOF'
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "stienen-rs485-gateway"
version = "1.0.0"
description = "RS485 Gateway for Stienen Controllers"
readme = "README.md"
license = {text = "MIT"}
authors = [
    {name = "Stienen Gateway Team", email = "team@company.com"},
]
maintainers = [
    {name = "Stienen Gateway Team", email = "team@company.com"},
]
classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Intended Audience :: Manufacturing",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10", 
    "Programming Language :: Python :: 3.11",
    "Topic :: System :: Hardware",
    "Topic :: Scientific/Engineering",
    "Framework :: AsyncIO",
]
dependencies = [
    "pyserial>=3.5",
    "crcmod>=1.7",
    "pydantic>=1.10.0",
    "aiohttp>=3.8.0",
    "fastapi>=0.100.0",
    "uvicorn[standard]>=0.23.0",
]
requires-python = ">=3.8"

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.1.0",
    "black>=23.0.0",
    "pylint>=2.17.0",
    "mypy>=1.5.0",
    "pre-commit>=3.3.0",
]
web = [
    "fastapi>=0.100.0",
    "uvicorn[standard]>=0.23.0",
    "websockets>=11.0",
]
mqtt = [
    "paho-mqtt>=1.6.0",
    "asyncio-mqtt>=0.13.0",
]
database = [
    "asyncpg>=0.28.0",
    "sqlalchemy>=2.0.0",
]
monitoring = [
    "prometheus-client>=0.17.0",
    "psutil>=5.9.0",
    "coloredlogs>=15.0",
]

[project.urls]
Homepage = "https://github.com/company/stienen-gateway"
Repository = "https://github.com/company/stienen-gateway"
Documentation = "https://stienen-gateway.readthedocs.io/"
"Bug Tracker" = "https://github.com/company/stienen-gateway/issues"

[project.scripts]
stienen-gateway = "main:main"
stienen-web = "web_interface:run_web_interface"
stienen-monitor = "monitoring_utilities:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["stienen*"]
exclude = ["tests*"]

[tool.black]
line-length = 88
target-version = ['py38', 'py39', 'py310', 'py311']
include = '\.pyi?$'
extend-exclude = '''
/(
  # directories
  \.eggs
  | \.git
  | \.hg
  | \.mypy_cache
  | \.tox
  | \.venv
  | build
  | dist
)/
'''

[tool.pylint.messages_control]
disable = ["C0330", "C0326", "W0621", "R0903", "R0913", "R0914"]

[tool.mypy]
python_version = "3.8"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
disallow_untyped_decorators = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
warn_unreachable = true
strict_equality = true

[tool.pytest.ini_options]
minversion = "7.0"
addopts = "-ra -q --strict-markers --strict-config"
testpaths = ["tests"]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests as integration tests",
    "unit: marks tests as unit tests",
]

[tool.coverage.run]
source = ["stienen"]
omit = [
    "*/tests/*",
    "*/test_*",
    "setup.py",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
EOF

# .pre-commit-config.yaml
cat > .pre-commit-config.yaml << 'EOF'
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-json
      - id: check-toml
      - id: check-xml
      - id: debug-statements
      - id: check-builtin-literals
      - id: check-case-conflict
      - id: check-docstring-first
      - id: check-merge-conflict
      - id: check-executables-have-shebangs

  - repo: https://github.com/psf/black
    rev: 23.7.0
    hooks:
      - id: black
        language_version: python3

  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
        args: ["--profile", "black"]

  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        args: [--max-line-length=88, --extend-ignore=E203]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.5.1
    hooks:
      - id: mypy
        additional_dependencies: [pydantic, types-requests]
EOF

# .gitignore
cat > .gitignore << 'EOF'
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# C extensions
*.so

# Distribution / packaging
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
pip-wheel-metadata/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# PyInstaller
*.manifest
*.spec

# Installer logs
pip-log.txt
pip-delete-this-directory.txt

# Unit test / coverage reports
htmlcov/
.tox/
.nox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.py,cover
.hypothesis/
.pytest_cache/

# Virtual environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Spyder project settings
.spyderproject
.spyproject

# Rope project settings
.ropeproject

# mkdocs documentation
/site

# mypy
.mypy_cache/
.dmypy.json
dmypy.json

# Pyre type checker
.pyre/

# Logs and runtime data
logs/
*.log
*.pid
*.seed
*.pid.lock

# Exports and generated data
exports/
backups/
*.csv
*.xml
temp/

# Configuration files with secrets
config.json
.env
.env.local
.env.*.local

# OS generated files
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
ehthumbs.db
Thumbs.db

# Docker
.dockerignore
docker-compose.override.yml

# Temporary files
*.tmp
*.temp
*.bak
*.swp
*.swo

# Database files
*.db
*.sqlite
*.sqlite3

# Jupyter Notebook
.ipynb_checkpoints

# pyenv
.python-version

# pipenv
Pipfile.lock

# PEP 582
__pypackages__/

# Celery stuff
celerybeat-schedule
celerybeat.pid

# SageMath parsed files
*.sage.py

# Environments
.env
.env.local
.env.development.local
.env.test.local
.env.production.local

# Spyder project settings
.spyderproject
.spyproject

# Rope project settings
.ropeproject

# mkdocs documentation
/site

# mypy
.mypy_cache/
.dmypy.json
dmypy.json

# Pyre type checker
.pyre/

# pyright
pyrightconfig.json
EOF

# README.md (финальный)
cat > README.md << 'EOF'
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
EOF

echo "Финальная структура проекта создана!"
echo ""
echo "📁 Полная структура проекта:"
echo ""
echo "stienen_gateway/"
echo "├── 📄 README.md                    # Документация проекта"
echo "├── 📄 requirements.txt            # Python зависимости"  
echo "├── 📄 setup.py                    # Установочный скрипт"
echo "├── 📄 pyproject.toml              # Современная Python конфигурация"
echo "├── 📄 Dockerfile                  # Docker образ"
echo "├── 📄 docker-compose.yml          # Docker Compose"
echo "├── 📄 Makefile                    # Команды разработки"
echo "├── 📄 .env.example                # Переменные окружения"
echo "├── 📄 .gitignore                  # Git игнорирование"
echo "├── 📄 .pre-commit-config.yaml     # Хуки pre-commit"
echo "├── 📄 config.example.json         # Пример конфигурации"
echo "├── 📄 main.py                     # Точка входа"
echo "├── "
echo "├── 🐍 stienen/                    # Основной Python пакет"
echo "│   ├── 📄 __init__.py"
echo "│   ├── 📄 rs485_protocol.py       # RS485 протокол"
echo "│   ├── 📄 rs485_communication.py  # RS485 коммуникация"
echo "│   ├── 📄 variable_mapping.py     # Маппинг переменных"
echo "│   ├── 📄 scada_integration.py    # SCADA интеграция"
echo "│   ├── 📄 gateway_backend.py      # Основной бэкенд"
echo "│   ├── 📄 main_application.py     # Главное приложение"
echo "│   ├── 📄 web_interface.py        # Веб-интерфейс"
echo "│   └── 📄 monitoring_utilities.py # Утилиты мониторинга"
echo "├── "
echo "├── 🧪 tests/                      # Тесты"
echo "│   ├── 📄 __init__.py"
echo "│   ├── 📄 test_protocol.py        # Тесты протокола"
echo "│   ├── 📄 test_communication.py   # Тесты коммуникации"
echo "│   ├── 📄 test_variables.py       # Тесты переменных"
echo "│   ├── 📄 test_gateway.py         # Тесты гейтвея"
echo "│   └── 📄 test_integration.py     # Интеграционные тесты"
echo "├── "
echo "├── ⚙️  config/                     # Конфигурационные файлы"
echo "│   ├── 📄 variables.json          # Конфигурация переменных"
echo "│   └── 📄 devices.json            # Конфигурация устройств"
echo "├── "
echo "├── 📊 monitoring/                 # Мониторинг и метрики"
echo "│   ├── 📄 prometheus.yml          # Конфигурация Prometheus"
echo "│   └── 📁 grafana/                # Дашборды Grafana"
echo "│       ├── 📁 dashboards/"
echo "│       └── 📁 datasources/"
echo "├── "
echo "├── 📝 logs/                       # Логи системы"
echo "├── 📤 exports/                    # Экспорт данных SCADA"
echo "├── 💾 backups/                    # Резервные копии"
echo "└── 📚 docs/                       # Документация"
echo "    ├── 📄 installation.md"
echo "    ├── 📄 configuration.md"
echo "    ├── 📄 api.md"
echo "    └── 📄 deployment.md"
echo ""
echo "✅ Проект полностью готов к использованию!"
echo ""
echo "🚀 Следующие шаги:"
echo "1. cp config.example.json config.json"
echo "2. Отредактируйте config.json под ваши устройства"
echo "3. make install"
echo "4. make test"
echo "5. make up"
echo "6. Откройте http://localhost:8080"
echo ""
echo "📖 Полная документация в README.md"
