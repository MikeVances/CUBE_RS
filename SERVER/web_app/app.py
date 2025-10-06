#!/usr/bin/env python3
"""
Flask Web Application для мониторинга КУБ-1063
Получает данные от Gateway через защищенный API
Поддерживает интеграцию с Tailscale для управления mesh-сетью
Ported from archive to SERVER for centralized web management
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional

import requests
from flask import Flask, jsonify, render_template, request, redirect, url_for, flash
from flask_cors import CORS

# Import SERVER core components
try:
    from ..monitoring.security_monitor import SecurityMonitor
    from ..security.mitm_protection import create_secure_client
except ImportError:
    SecurityMonitor = None
    create_secure_client = None

# Импорт системы регистрации устройств
from .device_registry import DeviceRegistry
from .rbac_system import RBACSystem, User, Role, Permission
from .api_gateway import APIGateway
from .tailscale_integration import TailscaleWebIntegration

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Инициализация Flask
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
CORS(app)

# Инициализация компонентов системы
device_registry = DeviceRegistry()
rbac_system = RBACSystem()
api_gateway = APIGateway()
tailscale_integration = TailscaleWebIntegration()

# Инициализация безопасности
security_monitor = SecurityMonitor() if SecurityMonitor else None


class WebAppConfig:
    """Конфигурация веб-приложения"""

    def __init__(self):
        # Основные настройки
        self.host = os.environ.get("WEB_HOST", "0.0.0.0")
        self.port = int(os.environ.get("WEB_PORT", "8080"))
        self.debug = os.environ.get("WEB_DEBUG", "false").lower() == "true"
        
        # API Gateway настройки
        self.edge_gateway_url = os.environ.get("EDGE_GATEWAY_URL", "http://localhost:5020")
        self.api_key = os.environ.get("API_KEY", "")
        self.api_secret = os.environ.get("API_SECRET", "")
        
        # Tailscale настройки
        self.tailscale_enabled = os.environ.get("TAILSCALE_ENABLED", "true").lower() == "true"
        self.tailnet = os.environ.get("TAILNET", "your-tailnet.ts.net")
        self.tailscale_api_key = os.environ.get("TAILSCALE_API_KEY", "")
        
        # База данных
        self.db_path = os.environ.get("DB_PATH", "server_data.db")
        
        # Безопасность
        self.enable_security_monitoring = os.environ.get("SECURITY_MONITORING", "true").lower() == "true"
        self.certificate_pinning = os.environ.get("CERTIFICATE_PINNING", "true").lower() == "true"
        
    def is_configured(self) -> bool:
        """Проверяет базовую конфигурацию"""
        return bool(self.api_key and self.api_secret)


config = WebAppConfig()


def generate_signature(payload: str, timestamp: str) -> str:
    """Генерирует HMAC подпись для API запроса"""
    message = f"{timestamp}{payload}"
    signature = hmac.new(
        config.api_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return signature


def make_secure_api_request(
    endpoint: str, method: str = "GET", data: Optional[dict] = None
) -> Optional[dict]:
    """Выполняет защищенный API запрос к EDGE Gateway"""
    if not config.is_configured():
        logger.error("API не настроен - отсутствуют ключи или URL")
        return None

    try:
        url = f"{config.edge_gateway_url.rstrip('/')}/{endpoint.lstrip('/')}"
        timestamp = str(int(time.time()))
        payload = ""

        if data and method.upper() in ["POST", "PUT"]:
            payload = json.dumps(data)

        signature = generate_signature(payload, timestamp)

        headers = {
            "X-API-Key": config.api_key,
            "X-Timestamp": timestamp,
            "X-Signature": signature,
            "Content-Type": "application/json",
        }

        # Используем защищенный клиент если доступен
        session = create_secure_client() if create_secure_client else requests.Session()
        
        if method.upper() == "GET":
            response = session.get(url, headers=headers, timeout=config.api_timeout or 10)
        elif method.upper() == "POST":
            response = session.post(url, headers=headers, data=payload, timeout=config.api_timeout or 10)
        else:
            logger.error(f"Неподдерживаемый HTTP метод: {method}")
            return None

        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"API запрос неудачен: {response.status_code} - {response.text}")
            return None

    except requests.exceptions.Timeout:
        logger.error("Таймаут API запроса")
        return None
    except requests.exceptions.ConnectionError:
        logger.error("Ошибка соединения с API")
        return None
    except Exception as e:
        logger.error(f"Ошибка API запроса: {e}")
        return None


# ============================================================================
# ОСНОВНЫЕ МАРШРУТЫ ВЕБ-ПРИЛОЖЕНИЯ
# ============================================================================

@app.route("/")
def index():
    """Главная страница панели управления"""
    try:
        # Получаем статистику системы
        system_stats = api_gateway.get_system_statistics()
        
        # Получаем список устройств
        devices = device_registry.get_all_devices()
        
        # Получаем информацию о Tailscale сети
        tailscale_info = None
        if config.tailscale_enabled:
            tailscale_info = tailscale_integration.get_network_overview()
        
        return render_template(
            "dashboard.html",
            system_stats=system_stats,
            devices=devices,
            tailscale_info=tailscale_info,
            config=config,
        )
    except Exception as e:
        logger.error(f"Ошибка загрузки главной страницы: {e}")
        flash(f"Ошибка загрузки данных: {e}", "error")
        return render_template("dashboard.html", error=str(e))


@app.route("/health")
def health_check():
    """Health check endpoint"""
    health_status = {
        "status": "ok",
        "service": "cube-rs-web-app",
        "timestamp": time.time(),
        "version": "1.0.0",
        "components": {
            "device_registry": "ok",
            "rbac_system": "ok",
            "api_gateway": "ok" if config.is_configured() else "not_configured",
            "tailscale": "ok" if config.tailscale_enabled else "disabled",
            "security_monitor": "ok" if security_monitor else "not_available",
        },
    }
    
    # Проверяем соединение с EDGE Gateway
    edge_health = make_secure_api_request("health")
    if edge_health:
        health_status["components"]["edge_gateway"] = "connected"
        health_status["edge_gateway_info"] = edge_health
    else:
        health_status["components"]["edge_gateway"] = "disconnected"
        health_status["status"] = "degraded"
    
    return jsonify(health_status)


# ============================================================================
# API ENDPOINTS ДЛЯ AJAX ЗАПРОСОВ
# ============================================================================

@app.route("/api/data/current")
def get_current_data():
    """Получение текущих данных КУБ-1063"""
    try:
        # Запрашиваем данные через API Gateway
        data = api_gateway.get_current_modbus_data()
        
        if data:
            return jsonify({
                "status": "success",
                "data": data,
                "source": "edge_gateway",
                "timestamp": time.time()
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Не удалось получить данные от EDGE Gateway"
            }), 503
            
    except Exception as e:
        logger.error(f"Ошибка получения текущих данных: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/api/devices")
def get_devices_list():
    """Получение списка устройств"""
    try:
        devices = device_registry.get_all_devices()
        devices_data = [
            {
                "device_id": device.device_id,
                "hostname": device.hostname,
                "tailscale_ip": device.tailscale_ip,
                "status": device.status,
                "device_type": device.device_type,
                "last_seen": device.last_seen,
                "tags": device.tags,
                "metadata": device.metadata,
            }
            for device in devices
        ]
        
        return jsonify({
            "status": "success",
            "devices": devices_data,
            "total": len(devices_data)
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения списка устройств: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/api/tailscale/status")
def get_tailscale_status():
    """Получение статуса Tailscale сети"""
    try:
        if not config.tailscale_enabled:
            return jsonify({
                "status": "disabled",
                "message": "Tailscale интеграция отключена"
            })
        
        status = tailscale_integration.get_network_status()
        
        return jsonify({
            "status": "success",
            "tailscale_status": status
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения статуса Tailscale: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/api/security/events")
def get_security_events():
    """Получение событий безопасности"""
    try:
        if not security_monitor:
            return jsonify({
                "status": "disabled",
                "message": "Security monitoring не доступен"
            })
        
        events = security_monitor.get_recent_events(limit=50)
        
        return jsonify({
            "status": "success",
            "events": events,
            "total": len(events)
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения событий безопасности: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ============================================================================
# МАРШРУТЫ УПРАВЛЕНИЯ УСТРОЙСТВАМИ
# ============================================================================

@app.route("/devices")
def devices_page():
    """Страница управления устройствами"""
    try:
        devices = device_registry.get_all_devices()
        pending_requests = device_registry.get_pending_requests()
        
        return render_template(
            "devices.html",
            devices=devices,
            pending_requests=pending_requests,
            config=config,
        )
    except Exception as e:
        logger.error(f"Ошибка загрузки страницы устройств: {e}")
        flash(f"Ошибка загрузки устройств: {e}", "error")
        return redirect(url_for("index"))


@app.route("/devices/<device_id>")
def device_details(device_id):
    """Детальная информация об устройстве"""
    try:
        device = device_registry.get_device(device_id)
        if not device:
            flash("Устройство не найдено", "error")
            return redirect(url_for("devices_page"))
        
        # Получаем текущие данные с устройства
        device_data = None
        if device.device_type == "farm" and device.status == "active":
            device_data = api_gateway.get_device_data(device_id)
        
        return render_template(
            "device_details.html",
            device=device,
            device_data=device_data,
            config=config,
        )
        
    except Exception as e:
        logger.error(f"Ошибка загрузки информации об устройстве {device_id}: {e}")
        flash(f"Ошибка загрузки устройства: {e}", "error")
        return redirect(url_for("devices_page"))


@app.route("/api/devices/<device_id>/approve", methods=["POST"])
def approve_device(device_id):
    """Одобрение регистрации устройства"""
    try:
        success = device_registry.approve_device_registration(
            device_id, approved_by="web_admin"
        )
        
        if success:
            return jsonify({
                "status": "success",
                "message": "Устройство одобрено"
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Не удалось одобрить устройство"
            }), 400
            
    except Exception as e:
        logger.error(f"Ошибка одобрения устройства {device_id}: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/api/devices/<device_id>/revoke", methods=["POST"])
def revoke_device(device_id):
    """Отзыв устройства"""
    try:
        success = device_registry.revoke_device(device_id)
        
        if success:
            return jsonify({
                "status": "success",
                "message": "Устройство отозвано"
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Не удалось отозвать устройство"
            }), 400
            
    except Exception as e:
        logger.error(f"Ошибка отзыва устройства {device_id}: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ============================================================================
# МАРШРУТЫ БЕЗОПАСНОСТИ И МОНИТОРИНГА
# ============================================================================

@app.route("/security")
def security_page():
    """Страница мониторинга безопасности"""
    try:
        security_stats = None
        recent_events = []
        
        if security_monitor:
            security_stats = security_monitor.get_statistics()
            recent_events = security_monitor.get_recent_events(limit=20)
        
        return render_template(
            "security.html",
            security_stats=security_stats,
            recent_events=recent_events,
            config=config,
        )
        
    except Exception as e:
        logger.error(f"Ошибка загрузки страницы безопасности: {e}")
        flash(f"Ошибка загрузки данных безопасности: {e}", "error")
        return redirect(url_for("index"))


@app.route("/tailscale")
def tailscale_page():
    """Страница управления Tailscale сетью"""
    try:
        if not config.tailscale_enabled:
            flash("Tailscale интеграция отключена", "warning")
            return redirect(url_for("index"))
        
        network_info = tailscale_integration.get_network_overview()
        devices = tailscale_integration.get_devices_list()
        
        return render_template(
            "tailscale.html",
            network_info=network_info,
            devices=devices,
            config=config,
        )
        
    except Exception as e:
        logger.error(f"Ошибка загрузки страницы Tailscale: {e}")
        flash(f"Ошибка загрузки Tailscale: {e}", "error")
        return redirect(url_for("index"))


# ============================================================================
# ИНИЦИАЛИЗАЦИЯ И ЗАПУСК
# ============================================================================

def init_web_app():
    """Инициализация веб-приложения"""
    logger.info("🌐 Инициализация CUBE_RS Web App...")
    
    try:
        # Инициализируем компоненты
        logger.info("   📊 Инициализация Device Registry...")
        device_registry.init_database()
        
        logger.info("   🔐 Инициализация RBAC System...")
        rbac_system.init_database()
        
        logger.info("   🌉 Инициализация API Gateway...")
        api_gateway.configure(
            edge_url=config.edge_gateway_url,
            api_key=config.api_key,
            api_secret=config.api_secret
        )
        
        if config.tailscale_enabled:
            logger.info("   🔗 Инициализация Tailscale интеграции...")
            tailscale_integration.configure(
                tailnet=config.tailnet,
                api_key=config.tailscale_api_key
            )
        
        if security_monitor:
            logger.info("   🛡️ Запуск Security Monitor...")
            # Security monitor будет запущен в отдельном потоке
        
        logger.info("✅ Web App инициализирован успешно")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации Web App: {e}")
        raise


def create_app():
    """Фабрика приложений Flask"""
    init_web_app()
    return app


def main():
    """Основная функция для запуска веб-приложения"""
    logger.info("🚀 Запуск CUBE_RS Web Application...")
    
    try:
        # Инициализация
        init_web_app()
        
        # Показываем конфигурацию
        logger.info(f"🌐 Сервер: {config.host}:{config.port}")
        logger.info(f"🔗 EDGE Gateway: {config.edge_gateway_url}")
        logger.info(f"📡 Tailscale: {'✅' if config.tailscale_enabled else '❌'}")
        logger.info(f"🛡️ Security Monitor: {'✅' if security_monitor else '❌'}")
        
        # Запускаем веб-сервер
        logger.info("⚠️ Нажмите Ctrl+C для остановки")
        app.run(
            host=config.host,
            port=config.port,
            debug=config.debug,
            threaded=True
        )
        
    except KeyboardInterrupt:
        logger.info("👋 Получен сигнал остановки")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка веб-приложения: {e}")
        sys.exit(1)
    finally:
        logger.info("✅ Web App остановлен")


if __name__ == "__main__":
    main()