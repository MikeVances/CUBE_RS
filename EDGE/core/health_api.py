#!/usr/bin/env python3
"""
EDGE Health API - HTTP эндпоинты для мониторинга здоровья системы
"""

import asyncio
import json
import logging
from contextlib import suppress
from typing import Optional

from aiohttp import web, ClientSession

from .health_checker import health_checker
from .error_handler import get_error_stats
from .log_filter import get_secure_logger
from .config_manager import get_config

logger = get_secure_logger(__name__)

class HealthAPI:
    """HTTP API для health checks"""
    
    def __init__(self, port: int = 8090):
        self.port = port
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        config = get_config()
        security = getattr(config, "security", None)
        self.require_token = bool(security and getattr(security, "require_health_token", False))
        self.expected_token = getattr(security, "health_token", None)

    def setup_routes(self):
        """Настройка маршрутов"""
        self.app = web.Application()

        # Health endpoints
        self.app.router.add_get('/health', self.health_endpoint)
        self.app.router.add_get('/health/{component}', self.component_health_endpoint)
        self.app.router.add_get('/metrics', self.metrics_endpoint)
        self.app.router.add_get('/errors', self.errors_endpoint)
        self.app.router.add_get('/', self.root_endpoint)
    
    async def health_endpoint(self, request):
        """Общее состояние здоровья системы"""
        if not self._is_authorized(request):
            return self._unauthorized_response()
        try:
            health_data = await health_checker.get_overall_health()
            return web.json_response(health_data)
        except Exception as e:
            logger.error(f"Health endpoint error: {e}")
            return web.json_response(
                {"error": "Health check failed", "details": str(e)}, 
                status=500
            )
    
    async def component_health_endpoint(self, request):
        """Состояние конкретного компонента"""
        if not self._is_authorized(request):
            return self._unauthorized_response()
        try:
            component_name = request.match_info['component']
            from .health_checker import check_component_health

            health_check = await check_component_health(component_name)
            if health_check:
                return web.json_response({
                    "component": component_name,
                    "status": health_check.status.name.lower(),
                    "details": health_check.details,
                    "response_time_ms": health_check.response_time_ms,
                    "timestamp": health_check.timestamp.isoformat()
                })
            else:
                return web.json_response(
                    {"error": "Component not found", "component": component_name}, 
                    status=404
                )
        except Exception as e:
            logger.error(f"Component health endpoint error: {e}")
            return web.json_response(
                {"error": "Component health check failed", "details": str(e)}, 
                status=500
            )
    
    async def metrics_endpoint(self, request):
        """Системные метрики"""
        if not self._is_authorized(request):
            return self._unauthorized_response()
        try:
            system_metrics = await health_checker.get_system_metrics()
            return web.json_response({
                "metrics": {
                    "cpu_percent": system_metrics.cpu_percent,
                    "memory_percent": system_metrics.memory_percent,
                    "disk_percent": system_metrics.disk_percent,
                    "uptime_seconds": system_metrics.uptime_seconds,
                    "process_count": system_metrics.process_count,
                    "load_average": system_metrics.load_average,
                }
            })
        except Exception as e:
            logger.error(f"Metrics endpoint error: {e}")
            return web.json_response(
                {"error": "Metrics collection failed", "details": str(e)}, 
                status=500
            )
    
    async def errors_endpoint(self, request):
        """Статистика ошибок"""
        if not self._is_authorized(request):
            return self._unauthorized_response()
        try:
            error_stats = get_error_stats()
            return web.json_response(error_stats)
        except Exception as e:
            logger.error(f"Errors endpoint error: {e}")
            return web.json_response(
                {"error": "Error stats collection failed", "details": str(e)}, 
                status=500
            )
    
    async def root_endpoint(self, request):
        """Главная страница API"""
        if not self._is_authorized(request):
            return self._unauthorized_response()
        return web.json_response({
            "service": "CUBE_RS EDGE Health API",
            "version": "1.0",
            "endpoints": {
                "/health": "Overall system health",
                "/health/{component}": "Component-specific health",
                "/metrics": "System metrics", 
                "/errors": "Error statistics"
            }
        })
    
    async def start(self):
        """Запуск HTTP сервера"""
        try:
            self.setup_routes()
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(self.runner, '0.0.0.0', self.port)
            await self.site.start()
            
            logger.info(f"🏥 Health API запущен на http://0.0.0.0:{self.port}")
            logger.info("   Эндпоинты:")
            logger.info(f"     • Health: http://0.0.0.0:{self.port}/health")
            logger.info(f"     • Metrics: http://0.0.0.0:{self.port}/metrics") 
            logger.info(f"     • Errors: http://0.0.0.0:{self.port}/errors")
            
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Health API: {e}")
            return False
    
    async def stop(self):
        """Остановка HTTP сервера"""
        try:
            if self.site is not None:
                with suppress(Exception):
                    await self.site.stop()
                self.site = None

            if self.runner is not None:
                with suppress(Exception):
                    await self.runner.shutdown()
                with suppress(Exception):
                    await self.runner.cleanup()
                self.runner = None

            if self.app is not None:
                with suppress(Exception):
                    await self.app.shutdown()
                with suppress(Exception):
                    await self.app.cleanup()
                self.app = None

            logger.info("🛑 Health API остановлен")
        except Exception as e:
            logger.error(f"❌ Ошибка остановки Health API: {e}")

    def _is_authorized(self, request) -> bool:
        if not self.require_token:
            return True
        token = request.headers.get('X-EDGE-Health-Token') or request.query.get('token')
        if not token:
            logger.warning("🔒 Health API запрос без токена отклонён")
            return False
        if token != self.expected_token:
            logger.warning("🔒 Health API запрос с неверным токеном")
            return False
        return True

    def _unauthorized_response(self):
        return web.json_response({"error": "unauthorized"}, status=401)

# Глобальный экземпляр
health_api = HealthAPI()

async def start_health_api(port: int = 8090):
    """Запуск Health API сервера"""
    global health_api
    health_api = HealthAPI(port)
    return await health_api.start()

async def stop_health_api():
    """Остановка Health API сервера"""
    if health_api:
        await health_api.stop()
