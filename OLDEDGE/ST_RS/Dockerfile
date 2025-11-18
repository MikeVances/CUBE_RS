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
