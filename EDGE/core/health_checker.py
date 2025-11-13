#!/usr/bin/env python3
"""
Система комплексных health checks для CUBE_RS.
Проверяет состояние всех критически важных компонентов системы.
"""

import asyncio
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import aiosqlite
import psutil

from .log_filter import get_secure_logger
from .types import HealthCheck, HealthStatus

logger = get_secure_logger(__name__)


class ComponentType(Enum):
    """Типы компонентов для мониторинга."""

    DATABASE = "database"
    MODBUS_CLIENT = "modbus_client"
    TELEGRAM_BOT = "telegram_bot"
    API_GATEWAY = "api_gateway"
    SYSTEM = "system"
    NETWORK = "network"


@dataclass
class SystemMetrics:
    """Системные метрики."""

    cpu_percent: float
    memory_percent: float
    disk_percent: float
    uptime_seconds: float
    process_count: int
    load_average: list[float]


@dataclass
class DatabaseHealth:
    """Состояние базы данных."""

    is_accessible: bool
    connection_time_ms: float
    table_count: int
    last_write_age_seconds: Optional[float]
    db_size_mb: float
    wal_mode: bool


@dataclass
class ModbusHealth:
    """Состояние Modbus клиентов."""

    active_connections: int
    successful_requests: int
    failed_requests: int
    last_success_time: Optional[datetime]
    average_response_time_ms: float


@dataclass
class NetworkHealth:
    """Состояние сетевых подключений."""

    tcp_connections: int
    listening_ports: list[int]
    network_interfaces: list[str]
    dns_resolution_time_ms: float


class HealthChecker:
    """Централизованная система health checks."""

    def __init__(self):
        self.start_time = datetime.now()
        self.check_cache: dict[ComponentType, HealthCheck] = {}
        self.cache_ttl = timedelta(seconds=30)  # Кэшируем результаты на 30 сек

    async def get_overall_health(self) -> dict[str, Any]:
        """Получить общее состояние системы."""
        checks = await self.run_all_checks()

        # Определяем общий статус
        overall_status = HealthStatus.HEALTHY
        critical_issues = []
        warnings = []

        for check in checks:
            if check.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
                critical_issues.append(f"{check.service_name}: {check.details}")
            elif check.status == HealthStatus.DEGRADED:
                if overall_status == HealthStatus.HEALTHY:
                    overall_status = HealthStatus.DEGRADED
                warnings.append(f"{check.service_name}: {check.details}")

        # Считаем метрики
        healthy_count = sum(1 for c in checks if c.status == HealthStatus.HEALTHY)
        total_count = len(checks)
        health_percentage = (
            (healthy_count / total_count * 100) if total_count > 0 else 0
        )

        uptime = datetime.now() - self.start_time

        return {
            "status": overall_status.name.lower(),
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": uptime.total_seconds(),
            "health_percentage": round(health_percentage, 1),
            "components": {
                "total": total_count,
                "healthy": healthy_count,
                "degraded": sum(1 for c in checks if c.status == HealthStatus.DEGRADED),
                "unhealthy": sum(
                    1 for c in checks if c.status == HealthStatus.UNHEALTHY
                ),
            },
            "checks": [asdict(check) for check in checks],
            "critical_issues": critical_issues,
            "warnings": warnings,
            "system_metrics": asdict(await self.get_system_metrics()),
        }

    async def run_all_checks(self) -> list[HealthCheck]:
        """Запустить все проверки состояния."""
        tasks = [
            self._check_database(),
            self._check_modbus_client(),
            self._check_telegram_bot(),
            self._check_api_gateway(),
            self._check_system_resources(),
            self._check_network(),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        checks = []
        for result in results:
            if isinstance(result, HealthCheck):
                checks.append(result)
            elif isinstance(result, Exception):
                logger.error(f"Health check failed: {result}")
                checks.append(
                    HealthCheck(
                        service_name="unknown",
                        status=HealthStatus.UNHEALTHY,
                        details=f"Check failed: {str(result)}",
                    )
                )

        return checks

    async def _check_database(self) -> HealthCheck:
        """Проверка состояния базы данных."""
        start_time = time.perf_counter()

        try:
            database_url = os.getenv("DATABASE_URL", "sqlite:///kub_data.db")
            db_path = database_url.replace("sqlite:///", "")

            if not os.path.exists(db_path):
                return HealthCheck(
                    service_name="database",
                    status=HealthStatus.UNHEALTHY,
                    details="Database file not found",
                    response_time_ms=0,
                )

            async with aiosqlite.connect(db_path, timeout=5) as conn:
                # Проверяем доступность
                await conn.execute("SELECT 1")

                # Проверяем WAL режим
                cursor = await conn.execute("PRAGMA journal_mode")
                journal_mode = (await cursor.fetchone())[0]

                # Считаем таблицы
                cursor = await conn.execute(
                    """
                    SELECT COUNT(*) FROM sqlite_master
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """
                )
                table_count = (await cursor.fetchone())[0]

                # Проверяем последнее обновление данных
                last_update_age = None
                try:
                    cursor = await conn.execute(
                        """
                        SELECT updated_at FROM latest_data
                        ORDER BY updated_at DESC LIMIT 1
                        """
                    )
                    row = await cursor.fetchone()
                    if row and row[0]:
                        last_update = datetime.fromisoformat(str(row[0]))
                        last_update_age = (datetime.now() - last_update).total_seconds()
                except Exception:
                    last_update_age = None

            # Размер БД
            db_size_mb = os.path.getsize(db_path) / 1024 / 1024

            response_time = (time.perf_counter() - start_time) * 1000

            # Определяем статус
            if table_count == 0:
                status = HealthStatus.UNHEALTHY
                details = "No tables found in database"
            elif last_update_age and last_update_age > 300:  # 5 минут
                status = HealthStatus.DEGRADED
                details = f"Data is stale ({last_update_age:.0f}s old)"
            elif response_time > 1000:  # 1 секунда
                status = HealthStatus.DEGRADED
                details = f"Slow database response ({response_time:.0f}ms)"
            else:
                status = HealthStatus.HEALTHY
                details = f"Tables: {table_count}, Size: {db_size_mb:.1f}MB, WAL: {journal_mode == 'wal'}"

            return HealthCheck(
                service_name="database",
                status=status,
                details=details,
                response_time_ms=response_time,
            )

        except Exception as e:
            response_time = (time.perf_counter() - start_time) * 1000
            logger.error(f"Database health check failed: {e}")
            return HealthCheck(
                service_name="database",
                status=HealthStatus.UNHEALTHY,
                details=f"Connection failed: {str(e)}",
                response_time_ms=response_time,
            )

    async def _check_modbus_client(self) -> HealthCheck:
        """Проверка состояния Modbus клиентов."""
        start_time = time.perf_counter()

        try:
            # Проверяем наличие активных соединений через процессы
            active_connections = 0
            modbus_processes = []

            for proc in psutil.process_iter(["pid", "name", "connections"]):
                try:
                    if "python" in proc.info["name"].lower():
                        # Проверяем командную строку на наличие modbus
                        cmdline = " ".join(proc.cmdline())
                        if "modbus" in cmdline.lower() or "gateway" in cmdline.lower():
                            modbus_processes.append(proc)
                            connections = proc.connections()
                            active_connections += len(
                                [c for c in connections if c.status == "ESTABLISHED"]
                            )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            response_time = (time.perf_counter() - start_time) * 1000

            if not modbus_processes:
                status = HealthStatus.UNHEALTHY
                details = "No Modbus processes running"
            elif active_connections == 0:
                status = HealthStatus.DEGRADED
                details = f"Modbus processes running ({len(modbus_processes)}) but no active connections"
            else:
                status = HealthStatus.HEALTHY
                details = f"Processes: {len(modbus_processes)}, Active connections: {active_connections}"

            return HealthCheck(
                service_name="modbus_client",
                status=status,
                details=details,
                response_time_ms=response_time,
            )

        except Exception as e:
            response_time = (time.perf_counter() - start_time) * 1000
            return HealthCheck(
                service_name="modbus_client",
                status=HealthStatus.UNHEALTHY,
                details=f"Check failed: {str(e)}",
                response_time_ms=response_time,
            )

    async def _check_telegram_bot(self) -> HealthCheck:
        """Проверка состояния Telegram бота."""
        start_time = time.perf_counter()

        try:
            # Проверяем наличие токена
            telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
            if not telegram_token:
                return HealthCheck(
                    service_name="telegram_bot",
                    status=HealthStatus.UNHEALTHY,
                    details="TELEGRAM_BOT_TOKEN not configured",
                )

            # Проверяем процесс бота
            bot_processes = []
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if "python" in proc.info["name"].lower():
                        cmdline = " ".join(proc.cmdline())
                        if "telegram" in cmdline.lower() or "bot" in cmdline.lower():
                            bot_processes.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            response_time = (time.perf_counter() - start_time) * 1000

            if not bot_processes:
                status = HealthStatus.DEGRADED
                details = "Telegram bot process not found (may be integrated)"
            else:
                status = HealthStatus.HEALTHY
                details = f"Bot processes: {len(bot_processes)}, Token configured"

            return HealthCheck(
                service_name="telegram_bot",
                status=status,
                details=details,
                response_time_ms=response_time,
            )

        except Exception as e:
            response_time = (time.perf_counter() - start_time) * 1000
            return HealthCheck(
                service_name="telegram_bot",
                status=HealthStatus.DEGRADED,
                details=f"Check failed: {str(e)}",
                response_time_ms=response_time,
            )

    async def _check_api_gateway(self) -> HealthCheck:
        """Проверка состояния API Gateway."""
        start_time = time.perf_counter()

        try:
            api_port = int(os.getenv("API_PORT", 8000))

            # Проверяем что порт прослушивается
            listening_ports = []
            for conn in psutil.net_connections():
                if conn.status == "LISTEN" and conn.laddr.port == api_port:
                    listening_ports.append(conn.laddr.port)

            response_time = (time.perf_counter() - start_time) * 1000

            if api_port not in listening_ports:
                status = HealthStatus.DEGRADED
                details = f"API Gateway not listening on port {api_port}"
            else:
                status = HealthStatus.HEALTHY
                details = f"API Gateway listening on port {api_port}"

            return HealthCheck(
                service_name="api_gateway",
                status=status,
                details=details,
                response_time_ms=response_time,
            )

        except Exception as e:
            response_time = (time.perf_counter() - start_time) * 1000
            return HealthCheck(
                service_name="api_gateway",
                status=HealthStatus.UNHEALTHY,
                details=f"Check failed: {str(e)}",
                response_time_ms=response_time,
            )

    async def _check_system_resources(self) -> HealthCheck:
        """Проверка системных ресурсов."""
        start_time = time.perf_counter()

        try:
            metrics = await self.get_system_metrics()

            response_time = (time.perf_counter() - start_time) * 1000

            critical_issues = []
            warnings = []

            # Критические пороги
            if metrics.cpu_percent > 90:
                critical_issues.append(
                    f"CPU usage critical: {metrics.cpu_percent:.1f}%"
                )
            elif metrics.cpu_percent > 70:
                warnings.append(f"CPU usage high: {metrics.cpu_percent:.1f}%")

            if metrics.memory_percent > 95:
                critical_issues.append(
                    f"Memory usage critical: {metrics.memory_percent:.1f}%"
                )
            elif metrics.memory_percent > 80:
                warnings.append(f"Memory usage high: {metrics.memory_percent:.1f}%")

            if metrics.disk_percent > 98:
                critical_issues.append(
                    f"Disk usage critical: {metrics.disk_percent:.1f}%"
                )
            elif metrics.disk_percent > 90:
                warnings.append(f"Disk usage high: {metrics.disk_percent:.1f}%")

            if critical_issues:
                status = HealthStatus.UNHEALTHY
                details = "; ".join(critical_issues)
            elif warnings:
                status = HealthStatus.DEGRADED
                details = "; ".join(warnings)
            else:
                status = HealthStatus.HEALTHY
                details = f"CPU: {metrics.cpu_percent:.1f}%, RAM: {metrics.memory_percent:.1f}%, Disk: {metrics.disk_percent:.1f}%"

            return HealthCheck(
                service_name="system",
                status=status,
                details=details,
                response_time_ms=response_time,
            )

        except Exception as e:
            response_time = (time.perf_counter() - start_time) * 1000
            return HealthCheck(
                service_name="system",
                status=HealthStatus.UNHEALTHY,
                details=f"Resource check failed: {str(e)}",
                response_time_ms=response_time,
            )

    async def _check_network(self) -> HealthCheck:
        """Проверка сетевых подключений."""
        start_time = time.perf_counter()

        try:
            # Подсчитываем активные соединения
            connections = psutil.net_connections()
            tcp_established = len([c for c in connections if c.status == "ESTABLISHED"])
            tcp_listening = len([c for c in connections if c.status == "LISTEN"])

            # Получаем сетевые интерфейсы
            interfaces = list(psutil.net_if_addrs().keys())
            active_interfaces = [
                name for name, stats in psutil.net_if_stats().items() if stats.isup
            ]

            response_time = (time.perf_counter() - start_time) * 1000

            if not active_interfaces:
                status = HealthStatus.UNHEALTHY
                details = "No active network interfaces"
            elif tcp_listening == 0:
                status = HealthStatus.DEGRADED
                details = "No listening TCP ports found"
            else:
                status = HealthStatus.HEALTHY
                details = f"TCP connections: {tcp_established}, Listening: {tcp_listening}, Interfaces: {len(active_interfaces)}"

            return HealthCheck(
                service_name="network",
                status=status,
                details=details,
                response_time_ms=response_time,
            )

        except Exception as e:
            response_time = (time.perf_counter() - start_time) * 1000
            return HealthCheck(
                service_name="network",
                status=HealthStatus.UNHEALTHY,
                details=f"Network check failed: {str(e)}",
                response_time_ms=response_time,
            )

    async def get_system_metrics(self) -> SystemMetrics:
        """Получить системные метрики."""
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)

            # Memory
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            # Disk
            disk = psutil.disk_usage("/")
            disk_percent = (disk.used / disk.total) * 100

            # Uptime
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime_seconds = (datetime.now() - boot_time).total_seconds()

            # Process count
            process_count = len(psutil.pids())

            # Load average (Unix only)
            try:
                load_average = list(os.getloadavg())
            except (AttributeError, OSError):
                load_average = [0.0, 0.0, 0.0]  # Windows fallback

            return SystemMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                disk_percent=disk_percent,
                uptime_seconds=uptime_seconds,
                process_count=process_count,
                load_average=load_average,
            )

        except Exception as e:
            logger.error(f"Failed to get system metrics: {e}")
            return SystemMetrics(
                cpu_percent=0.0,
                memory_percent=0.0,
                disk_percent=0.0,
                uptime_seconds=0.0,
                process_count=0,
                load_average=[0.0, 0.0, 0.0],
            )

    async def check_component(self, component: ComponentType) -> HealthCheck:
        """Проверить конкретный компонент."""
        # Используем кэш если данные свежие
        if component in self.check_cache:
            cached_check = self.check_cache[component]
            if datetime.now() - cached_check.timestamp < self.cache_ttl:
                return cached_check

        # Выполняем проверку
        if component == ComponentType.DATABASE:
            check = await self._check_database()
        elif component == ComponentType.MODBUS_CLIENT:
            check = await self._check_modbus_client()
        elif component == ComponentType.TELEGRAM_BOT:
            check = await self._check_telegram_bot()
        elif component == ComponentType.API_GATEWAY:
            check = await self._check_api_gateway()
        elif component == ComponentType.SYSTEM:
            check = await self._check_system_resources()
        elif component == ComponentType.NETWORK:
            check = await self._check_network()
        else:
            check = HealthCheck(
                service_name=component.value,
                status=HealthStatus.UNKNOWN,
                details="Unknown component type",
            )

        # Кэшируем результат
        self.check_cache[component] = check
        return check


# Глобальный экземпляр
health_checker = HealthChecker()


async def get_health_status() -> dict[str, Any]:
    """Получить статус здоровья системы."""
    return await health_checker.get_overall_health()


async def check_component_health(component_name: str) -> Optional[HealthCheck]:
    """Проверить здоровье конкретного компонента."""
    try:
        component = ComponentType(component_name.lower())
        return await health_checker.check_component(component)
    except ValueError:
        return None
