#!/usr/bin/env python3
"""
API Gateway для предоставления данных КУБ-1063 внешним приложениям
Работает локально и предоставляет защищенный API
"""

import asyncio
import hashlib
import hmac
import logging
import os
import sys
import time

import aiosqlite
from flask import Flask, abort, jsonify, request
from flask_cors import CORS

# Добавляем пути для импорта модулей системы
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from core.config_manager import get_config
    from core.security_manager import SecurityManager
    from dashboard.dashboard_reader import (
        get_historical_data,
        get_statistics,
        read_all,
        test_connection,
    )
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    sys.exit(1)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Инициализация Flask
app = Flask(__name__)

# CORS configuration - получаем из переменных окружения
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
CORS(app, origins=[origin.strip() for origin in cors_origins])

# Rate limiting - простой подход без slowapi для совместимости
# limiter = Limiter(
#     key_func=get_remote_address, default_limits=["200 per day", "50 per hour"]
# )
# Используем простую проверку rate limit
def check_rate_limit():
    # Простая проверка (можно расширить по мере необходимости)
    return True

# Загрузка конфигурации
try:
    config = get_config()
    security_manager = SecurityManager()
except Exception as e:
    logger.error(f"Ошибка загрузки конфигурации: {e}")
    config = None
    security_manager = None


class APIAuth:
    """Система аутентификации API"""

    def __init__(self):
        self.api_keys = {}
        self.load_api_keys()

    def load_api_keys(self):
        """Загружает API ключи из конфигурации"""
        try:
            if security_manager:
                # Пробуем загрузить API ключи из зашифрованного конфига
                api_config = security_manager.load_encrypted_config("api_keys")
                if api_config:
                    self.api_keys = api_config
                    logger.info(f"✅ Загружено {len(self.api_keys)} API ключей")
                else:
                    # Создаем дефолтный набор ключей для разработки
                    self.create_default_keys()
            else:
                self.create_default_keys()
        except Exception as e:
            logger.error(f"Ошибка загрузки API ключей: {e}")
            self.create_default_keys()

    def create_default_keys(self):
        """Создает ключи по умолчанию для разработки"""
        import secrets

        default_key = "dev-api-key"
        default_secret = secrets.token_hex(32)

        self.api_keys = {
            default_key: {
                "secret": default_secret,
                "name": "Development Key",
                "permissions": ["read"],
                "created": time.time(),
            }
        }

        # Сохраняем ключи
        if security_manager:
            try:
                security_manager.save_encrypted_config("api_keys", self.api_keys)
                logger.info("✅ API ключи сохранены в зашифрованном виде")
            except Exception as e:
                logger.error(f"Ошибка сохранения API ключей: {e}")

        logger.warning("⚠️ Используются ключи разработки!")
        logger.info(f"🔑 API Key: {default_key}")
        logger.info(f"🔐 API Secret: {default_secret}")

    def verify_request(
        self, api_key: str, timestamp: str, signature: str, payload: str
    ) -> bool:
        """Проверяет подпись API запроса"""
        if api_key not in self.api_keys:
            logger.warning(f"Неизвестный API ключ: {api_key}")
            return False

        # Проверяем timestamp (не старше 5 минут)
        try:
            request_time = int(timestamp)
            current_time = int(time.time())
            if abs(current_time - request_time) > 300:  # 5 минут
                logger.warning("Запрос слишком старый")
                return False
        except ValueError:
            logger.warning("Неверный формат timestamp")
            return False

        # Проверяем подпись
        secret = self.api_keys[api_key]["secret"]
        expected_signature = self.generate_signature(payload, timestamp, secret)

        if not hmac.compare_digest(signature, expected_signature):
            logger.warning("Неверная подпись запроса")
            return False

        return True

    def generate_signature(self, payload: str, timestamp: str, secret: str) -> str:
        """Генерирует HMAC подпись"""
        message = f"{timestamp}{payload}"
        return hmac.new(
            secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()


# Инициализация аутентификации
auth = APIAuth()


def require_auth(f):
    """Декоратор для проверки аутентификации"""

    def decorated_function(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        timestamp = request.headers.get("X-Timestamp")
        signature = request.headers.get("X-Signature")

        if not all([api_key, timestamp, signature]):
            logger.warning("Отсутствуют заголовки аутентификации")
            abort(401, description="Отсутствуют заголовки аутентификации")

        # Получаем payload
        if request.method in ["POST", "PUT", "PATCH"]:
            payload = request.get_data(as_text=True) or ""
        else:
            payload = ""

        if not auth.verify_request(api_key, timestamp, signature, payload):
            abort(403, description="Неверная аутентификация")

        return f(*args, **kwargs)

    decorated_function.__name__ = f.__name__
    return decorated_function


@app.route("/api/health")
@require_auth
def health_check():
    """Проверка состояния API"""
    db_status = test_connection()

    return jsonify(
        {
            "status": "healthy" if db_status else "degraded",
            "service": "kub-1063-api-gateway",
            "database": "connected" if db_status else "disconnected",
            "timestamp": time.time(),
        }
    )


@app.route("/api/data/current")
@require_auth
# @limiter.limit("10 per minute")  # Отключено для совместимости
def get_current_data():
    """Получение текущих данных КУБ-1063"""
    try:
        # Безопасное чтение из БД с параметризованными запросами
        data = asyncio.run(get_current_data_secure())

        if data:
            return jsonify(
                {"status": "success", "data": data, "retrieved_at": time.time()}
            )
        else:
            return jsonify({"status": "error", "message": "Нет доступных данных"}), 404

    except Exception as e:
        logger.error(f"Ошибка получения текущих данных: {e}")
        return jsonify({"status": "error", "message": "Внутренняя ошибка сервера"}), 500


async def get_current_data_secure():
    """Безопасное получение текущих данных из БД"""
    database_url = os.getenv("DATABASE_URL", "sqlite:///kub_data.db")
    db_path = database_url.replace("sqlite:///", "")

    async with aiosqlite.connect(db_path) as conn:
        # Параметризованный запрос - защита от SQL injection
        cursor = await conn.execute(
            """
            SELECT temp_inside, temp_target, humidity, co2, nh3, pressure,
                   ventilation_level, ventilation_target, active_alarms,
                   active_warnings, updated_at,
                   digital_outputs_1, digital_outputs_2, digital_outputs_3
            FROM latest_data
            WHERE id = ?
        """,
            (1,),
        )

        row = await cursor.fetchone()

        if row:
            return {
                "temp_inside": row[0],
                "temp_target": row[1],
                "humidity": row[2],
                "co2": row[3],
                "nh3": row[4],
                "pressure": row[5],
                "ventilation_level": row[6],
                "ventilation_target": row[7],
                "active_alarms": row[8],
                "active_warnings": row[9],
                "timestamp": row[10],
                "digital_outputs_1": row[11],
                "digital_outputs_2": row[12],
                "digital_outputs_3": row[13],
                "connection_status": "connected" if row[10] else "disconnected",
            }
        return None


@app.route("/api/data/history")
@require_auth
# @limiter.limit("5 per minute")  # Отключено для совместимости
def get_history():
    """Получение исторических данных"""
    try:
        hours = request.args.get("hours", 6, type=int)
        hours = min(max(hours, 1), 168)  # Ограничиваем 1-168 часов

        # Валидация параметра
        if not isinstance(hours, int) or hours < 1:
            return (
                jsonify({"status": "error", "message": "Некорректный параметр hours"}),
                400,
            )

        data = asyncio.run(get_historical_data_secure(hours))

        if data:
            return jsonify(
                {
                    "status": "success",
                    "data": data,
                    "hours": hours,
                    "count": len(data),
                    "retrieved_at": time.time(),
                }
            )
        else:
            return (
                jsonify({"status": "error", "message": "Нет исторических данных"}),
                404,
            )

    except Exception as e:
        logger.error(f"Ошибка получения исторических данных: {e}")
        return jsonify({"status": "error", "message": "Внутренняя ошибка сервера"}), 500


async def get_historical_data_secure(hours: int):
    """Безопасное получение исторических данных"""
    database_url = os.getenv("DATABASE_URL", "sqlite:///kub_data.db")
    db_path = database_url.replace("sqlite:///", "")

    async with aiosqlite.connect(db_path) as conn:
        # Параметризованный запрос - защита от SQL injection
        cursor = await conn.execute(
            """
            SELECT timestamp, temp_inside, temp_target, humidity, co2, nh3, pressure,
                   ventilation_level, ventilation_target, active_alarms, active_warnings
            FROM sensor_data
            WHERE timestamp > datetime('now', '-' || ? || ' hours')
            ORDER BY timestamp DESC
            LIMIT 1000
        """,
            (hours,),
        )

        rows = await cursor.fetchall()

        formatted_data = []
        for row in rows:
            formatted_data.append(
                {
                    "timestamp": row[0],
                    "temp_inside": row[1],
                    "temp_target": row[2],
                    "humidity": row[3],
                    "co2": row[4],
                    "nh3": row[5],
                    "pressure": row[6],
                    "ventilation_level": row[7],
                    "ventilation_target": row[8],
                    "active_alarms": row[9],
                    "active_warnings": row[10],
                }
            )

        return formatted_data


@app.route("/api/data/statistics")
@require_auth
def get_stats():
    """Получение статистики системы"""
    try:
        data = get_statistics()

        if data:
            return jsonify(
                {"status": "success", "data": data, "retrieved_at": time.time()}
            )
        else:
            return (
                jsonify({"status": "error", "message": "Нет статистических данных"}),
                404,
            )

    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        return jsonify({"status": "error", "message": "Внутренняя ошибка сервера"}), 500


@app.route("/api/keys/info")
@require_auth
def get_api_info():
    """Информация об API ключе (без секрета)"""
    api_key = request.headers.get("X-API-Key")
    if api_key in auth.api_keys:
        key_info = auth.api_keys[api_key].copy()
        key_info.pop("secret", None)  # Удаляем секрет из ответа

        return jsonify({"status": "success", "key_info": key_info})
    else:
        return jsonify({"status": "error", "message": "Ключ не найден"}), 404


@app.errorhandler(401)
def unauthorized(error):
    return (
        jsonify(
            {"error": "Неавторизованный доступ", "message": str(error.description)}
        ),
        401,
    )


@app.errorhandler(403)
def forbidden(error):
    return jsonify({"error": "Доступ запрещен", "message": str(error.description)}), 403


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Не найдено"}), 404


@app.errorhandler(429)
def ratelimit_handler(e):
    return (
        jsonify(
            {
                "error": "Превышен лимит запросов",
                "message": "Слишком много запросов. Попробуйте позже.",
                "retry_after": e.retry_after,
            }
        ),
        429,
    )


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Внутренняя ошибка сервера"}), 500


if __name__ == "__main__":
    logger.info("🚀 Запуск API Gateway для КУБ-1063")
    logger.info(f"🔑 Загружено API ключей: {len(auth.api_keys)}")

    # Запуск сервера
    port = int(os.environ.get("API_PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
