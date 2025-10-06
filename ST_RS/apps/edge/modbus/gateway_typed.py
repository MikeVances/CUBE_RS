"""
Typed Modbus TCP Gateway for КУБ-1063
Async version with full type safety and modern Python practices.

This is the typed version that will gradually replace gateway.py
"""
import asyncio
import logging

# Configure structured logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import aiosqlite
from aiohttp import web
from aiohttp.web import Request, Response, json_response

from core.error_handler import ErrorContext, handle_errors, retry_on_failure
from core.health_checker import check_component_health, get_health_status

# Import our type definitions
from core.types import (
    APIResponse,
    ModbusConnectionInfo,
    ModbusConnectionType,
    ModbusDevice,
    ModbusError,
    ModbusFunctionCode,
    ModbusRequest,
    ModbusResponse,
)

# Import our async Modbus client
from .async_client import AsyncModbusClient, ModbusConnectionPool

if os.getenv("ENVIRONMENT") == "production":
    from core.log_filter import setup_structured_logging_production

    logger = setup_structured_logging_production()
else:
    from core.log_filter import setup_structured_logging

    logger = setup_structured_logging()


class TypedModbusGateway:
    """
    Type-safe async Modbus TCP Gateway.

    Handles multiple concurrent Modbus connections with full type safety,
    comprehensive error handling, and performance monitoring.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 5023,
        db_path: str = "kub_data.db",
        max_concurrent_requests: int = 100,
        connection_pool_size: int = 10,
    ) -> None:
        """Initialize the typed Modbus gateway."""
        self.host = host
        self.port = port
        self.db_path = Path(db_path)
        self.max_concurrent_requests = max_concurrent_requests

        # Runtime state
        self.running: bool = False
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None

        # Modbus client with connection pooling
        self.connection_pool = ModbusConnectionPool(
            max_connections=connection_pool_size,
            connection_timeout=5.0,
            idle_timeout=300.0,
        )
        self.modbus_client = AsyncModbusClient(
            connection_pool=self.connection_pool,
            default_retry_count=3,
            default_retry_delay=1.0,
        )

        # Performance monitoring
        self.request_counter: int = 0
        self.error_counter: int = 0
        self.start_time: datetime = datetime.now()
        self.response_times: list[float] = []

        # Concurrency control
        self.request_semaphore = asyncio.Semaphore(max_concurrent_requests)
        self.db_lock = asyncio.Lock()

        logger.info(
            "🏗️ TypedModbusGateway initialized",
            extra={
                "host": self.host,
                "port": self.port,
                "db_path": str(self.db_path),
                "max_concurrent": self.max_concurrent_requests,
                "connection_pool_size": connection_pool_size,
            },
        )

    async def start_server(self) -> None:
        """Start the async HTTP server for Modbus operations."""
        if self.running:
            logger.warning("Gateway already running")
            return

        try:
            # Initialize database
            await self._init_database()

            # Start Modbus client
            await self.modbus_client.start()

            # Register default test devices (for development)
            await self._register_default_devices()

            # Create aiohttp application
            self.app = web.Application()

            # Add middleware
            self.app.middlewares.append(self._error_middleware)
            self.app.middlewares.append(self._metrics_middleware)
            self.app.middlewares.append(self._cors_middleware)

            # Setup routes
            self._setup_routes()

            # Start server
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()

            self.running = True
            self.start_time = datetime.now()

            logger.info(
                "🚀 TypedModbusGateway started",
                extra={
                    "address": f"{self.host}:{self.port}",
                    "endpoints": [
                        f"http://{self.host}:{self.port}/modbus/read",
                        f"http://{self.host}:{self.port}/modbus/write",
                        f"http://{self.host}:{self.port}/health",
                        f"http://{self.host}:{self.port}/metrics",
                    ],
                },
            )

        except Exception as e:
            logger.error(f"❌ Failed to start gateway: {e}", exc_info=True)
            await self.stop_server()
            raise

    async def stop_server(self) -> None:
        """Gracefully stop the server."""
        if not self.running:
            return

        logger.info("🛑 Stopping TypedModbusGateway...")

        self.running = False

        # Stop Modbus client
        await self.modbus_client.stop()

        # Stop HTTP server
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

        logger.info("✅ TypedModbusGateway stopped gracefully")

    def _setup_routes(self) -> None:
        """Setup HTTP routes."""
        if not self.app:
            raise RuntimeError("App not initialized")

        # Modbus operations
        self.app.router.add_post("/modbus/read", self._handle_modbus_read)
        self.app.router.add_post("/modbus/write", self._handle_modbus_write)

        # Monitoring endpoints
        self.app.router.add_get("/health", self._handle_health_check)
        self.app.router.add_get("/health/detailed", self._handle_detailed_health_check)
        self.app.router.add_get(
            "/health/{component}", self._handle_component_health_check
        )
        self.app.router.add_get("/metrics", self._handle_metrics)
        self.app.router.add_get("/errors", self._handle_error_stats)
        self.app.router.add_get("/devices", self._handle_devices)
        self.app.router.add_get("/connections", self._handle_connections)

        # Administrative endpoints
        self.app.router.add_post("/devices", self._handle_register_device)
        self.app.router.add_post(
            "/devices/{device_id}/connect", self._handle_device_connect
        )
        self.app.router.add_delete(
            "/devices/{device_id}", self._handle_device_disconnect
        )

    @web.middleware
    async def _error_middleware(self, request: Request, handler: Any) -> Response:
        """Global error handling middleware."""
        start_time = time.perf_counter()

        try:
            response = await handler(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log successful requests
            logger.info(
                "Request completed",
                extra={
                    "method": request.method,
                    "path": request.path_qs,
                    "status": response.status,
                    "duration_ms": round(duration_ms, 2),
                    "remote_ip": request.remote,
                    "user_agent": request.headers.get("User-Agent", "unknown"),
                },
            )

            # Track response time
            self.response_times.append(duration_ms)
            if len(self.response_times) > 1000:  # Keep only recent measurements
                self.response_times = self.response_times[-500:]

            return response

        except web.HTTPException:
            # Re-raise HTTP exceptions (they're handled by aiohttp)
            raise
        except Exception as e:
            # Handle unexpected errors
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.error_counter += 1

            logger.error(
                "Request failed",
                extra={
                    "method": request.method,
                    "path": request.path_qs,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                    "remote_ip": request.remote,
                },
                exc_info=True,
            )

            # Return structured error response
            error_response = APIResponse.error_response(
                f"Internal server error: {type(e).__name__}"
            )
            return json_response(error_response.model_dump(mode="json"), status=500)

    @web.middleware
    async def _metrics_middleware(self, request: Request, handler: Any) -> Response:
        """Metrics collection middleware."""
        self.request_counter += 1
        return await handler(request)

    @web.middleware
    async def _cors_middleware(self, request: Request, handler: Any) -> Response:
        """CORS middleware for web dashboard."""
        if request.method == "OPTIONS":
            # Handle preflight
            return web.Response(
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                }
            )

        response = await handler(request)

        # Add CORS headers
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"

        return response

    @handle_errors(component="modbus_gateway", operation="read_registers")
    async def _handle_modbus_read(self, request: Request) -> Response:
        """Handle Modbus read request with full type safety."""
        async with self.request_semaphore:
            try:
                # Parse and validate request
                request_data = await request.json()
                modbus_request = ModbusRequest(**request_data)

                # Create error context for detailed logging
                error_context = ErrorContext(
                    component="modbus_gateway",
                    operation="read_registers",
                    device_id=modbus_request.device_id,
                    additional_data={
                        "register_address": modbus_request.register_address,
                        "register_count": modbus_request.register_count,
                        "function_code": modbus_request.function_code.value,
                    },
                )

                # Execute request through real Modbus client with retry
                response = await self.modbus_client.execute_request(modbus_request)

                # Save to database with error handling
                await self._save_to_database_safe(response, error_context)

                # Return structured response
                api_response = APIResponse.success_response(
                    response.model_dump(mode="json")
                )
                return json_response(api_response.model_dump(mode="json"))

            except ValueError as e:
                logger.warning("Invalid request data", error=str(e))
                error_response = APIResponse.error_response(f"Validation error: {e}")
                return json_response(error_response.model_dump(mode="json"), status=400)

            except ModbusError as e:
                logger.error("Modbus operation failed", error=str(e))
                error_response = APIResponse.error_response(f"Modbus error: {e}")
                return json_response(error_response.model_dump(mode="json"), status=502)

            except Exception as e:
                logger.error(
                    "Unexpected error in modbus read", error=str(e), exc_info=True
                )
                error_response = APIResponse.error_response("Internal server error")
                return json_response(error_response.model_dump(mode="json"), status=500)

    async def _handle_modbus_write(self, request: Request) -> Response:
        """Handle Modbus write request."""
        async with self.request_semaphore:
            try:
                request_data = await request.json()
                modbus_request = ModbusRequest(**request_data)

                # Validate write operation
                if not modbus_request.write_values:
                    raise ValueError("Write values are required for write operations")

                # Check function code is for writing
                write_functions = {
                    ModbusFunctionCode.WRITE_SINGLE_COIL,
                    ModbusFunctionCode.WRITE_SINGLE_REGISTER,
                    ModbusFunctionCode.WRITE_MULTIPLE_COILS,
                    ModbusFunctionCode.WRITE_MULTIPLE_REGISTERS,
                }

                if modbus_request.function_code not in write_functions:
                    raise ValueError(
                        f"Function code {modbus_request.function_code} is not for write operations"
                    )

                # Execute request through real Modbus client
                response = await self.modbus_client.execute_request(modbus_request)
                await self._save_to_database(response)

                api_response = APIResponse.success_response(
                    response.model_dump(mode="json")
                )
                return json_response(api_response.model_dump(mode="json"))

            except ValueError as e:
                error_response = APIResponse.error_response(f"Validation error: {e}")
                return json_response(error_response.model_dump(mode="json"), status=400)
            except Exception as e:
                logger.error(f"Write operation failed: {e}", exc_info=True)
                error_response = APIResponse.error_response("Write operation failed")
                return json_response(error_response.model_dump(mode="json"), status=500)

    async def _handle_health_check(self, request: Request) -> Response:
        """Basic health check endpoint - quick status only."""
        try:
            # Quick health check
            db_healthy = await self._check_database_health()
            uptime_seconds = (datetime.now() - self.start_time).total_seconds()

            # Basic gateway stats
            total_requests = self.request_counter
            success_rate = (
                (total_requests - self.error_counter) / total_requests * 100
                if total_requests > 0
                else 100.0
            )

            overall_healthy = db_healthy and success_rate > 80

            health_data = {
                "status": "healthy" if overall_healthy else "degraded",
                "timestamp": datetime.now().isoformat(),
                "uptime_seconds": round(uptime_seconds, 1),
                "version": "2.0.0-async-core",
                "service": "modbus-gateway",
            }

            status_code = 200 if overall_healthy else 503
            return json_response(health_data, status=status_code)

        except Exception as e:
            logger.error("Health check failed", error=str(e))
            return json_response(
                {
                    "status": "unhealthy",
                    "timestamp": datetime.now().isoformat(),
                    "error": "Health check failed",
                },
                status=503,
            )

    async def _handle_detailed_health_check(self, request: Request) -> Response:
        """Comprehensive health check with all system components."""
        try:
            health_status = await get_health_status()

            # Add gateway-specific metrics
            health_status["gateway_metrics"] = {
                "total_requests": self.request_counter,
                "error_count": self.error_counter,
                "success_rate_percent": round(
                    (self.request_counter - self.error_counter)
                    / self.request_counter
                    * 100
                    if self.request_counter > 0
                    else 100.0,
                    2,
                ),
                "avg_response_time_ms": round(
                    sum(self.response_times) / len(self.response_times)
                    if self.response_times
                    else 0.0,
                    2,
                ),
                "concurrent_limit": self.max_concurrent_requests,
                "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
            }

            status_code = (
                200
                if health_status["status"] == "healthy"
                else (503 if health_status["status"] == "unhealthy" else 200)
            )
            return json_response(health_status, status=status_code)

        except Exception as e:
            logger.error("Detailed health check failed", error=str(e))
            return json_response(
                {
                    "status": "unhealthy",
                    "timestamp": datetime.now().isoformat(),
                    "error": "Detailed health check failed",
                },
                status=503,
            )

    async def _handle_component_health_check(self, request: Request) -> Response:
        """Health check for specific component."""
        try:
            component = request.match_info["component"]
            health_check = await check_component_health(component)

            if health_check is None:
                return json_response(
                    {
                        "error": f"Unknown component: {component}",
                        "available_components": [
                            "database",
                            "modbus_client",
                            "telegram_bot",
                            "api_gateway",
                            "system",
                            "network",
                        ],
                    },
                    status=400,
                )

            status_code = (
                200
                if health_check.is_healthy
                else (503 if health_check.status.name == "UNHEALTHY" else 200)
            )

            return json_response(
                {
                    "component": health_check.service_name,
                    "status": health_check.status.name.lower(),
                    "details": health_check.details,
                    "response_time_ms": health_check.response_time_ms,
                    "timestamp": health_check.timestamp.isoformat(),
                    "is_healthy": health_check.is_healthy,
                },
                status=status_code,
            )

        except Exception as e:
            logger.error(
                "Component health check failed",
                error=str(e),
                component=request.match_info.get("component"),
            )
            return json_response({"error": "Component health check failed"}, status=503)

    async def _handle_metrics(self, request: Request) -> Response:
        """Prometheus-style metrics endpoint."""
        try:
            metrics = []

            # Request metrics
            metrics.append(f"cube_rs_requests_total {self.request_counter}")
            metrics.append(f"cube_rs_errors_total {self.error_counter}")

            # Response time metrics
            if self.response_times:
                sorted_times = sorted(self.response_times)
                p50_idx = int(len(sorted_times) * 0.5)
                p95_idx = int(len(sorted_times) * 0.95)
                p99_idx = int(len(sorted_times) * 0.99)

                metrics.append(
                    f"cube_rs_response_time_p50_ms {sorted_times[p50_idx]:.2f}"
                )
                metrics.append(
                    f"cube_rs_response_time_p95_ms {sorted_times[p95_idx]:.2f}"
                )
                metrics.append(
                    f"cube_rs_response_time_p99_ms {sorted_times[p99_idx]:.2f}"
                )

            # Device metrics
            device_count = (
                len(self.modbus_client.device_registry.devices)
                if self.modbus_client
                else 0
            )
            metrics.append(f"cube_rs_connected_devices {device_count}")

            # System metrics
            uptime = (datetime.now() - self.start_time).total_seconds()
            metrics.append(f"cube_rs_uptime_seconds {uptime:.1f}")
            metrics.append(f"cube_rs_memory_usage_mb {self._get_memory_usage():.1f}")

            return web.Response(text="\n".join(metrics), content_type="text/plain")

        except Exception as e:
            logger.error("Metrics generation failed", error=str(e), exc_info=True)
            return web.Response(text="# Metrics unavailable", status=503)

    async def _handle_error_stats(self, request: Request) -> Response:
        """Error statistics endpoint."""
        try:
            from core.error_handler import get_error_stats

            error_stats = get_error_stats()

            return json_response(error_stats)

        except Exception as e:
            logger.error("Error stats generation failed", error=str(e))
            return json_response({"error": "Error stats unavailable"}, status=503)

    async def _save_to_database(self, response: ModbusResponse) -> None:
        """Save Modbus response to database with proper async handling."""
        async with self.db_lock:
            try:
                async with aiosqlite.connect(self.db_path) as conn:
                    await conn.execute(
                        """
                        INSERT INTO modbus_data (
                            device_id, function_code, register_address, register_count,
                            data, timestamp, success, response_time_ms, error_message
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            response.request.device_id,
                            response.request.function_code.value,
                            response.request.register_address,
                            response.request.register_count,
                            str(response.data) if response.data else None,
                            response.timestamp.isoformat(),
                            response.success,
                            response.response_time_ms,
                            response.error_message,
                        ),
                    )
                    await conn.commit()

            except Exception as e:
                logger.error("Database save failed", error=str(e), exc_info=True)
                # Don't re-raise - this shouldn't fail the Modbus operation

    @retry_on_failure(component="modbus_gateway", max_attempts=3, base_delay=1.0)
    async def _save_to_database_safe(
        self, response: ModbusResponse, context: ErrorContext
    ) -> None:
        """Safe database save with error handling and retries."""
        await self._save_to_database(response)

    async def _init_database(self) -> None:
        """Initialize database schema."""
        async with aiosqlite.connect(self.db_path) as conn:
            # Create table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS modbus_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id INTEGER NOT NULL,
                    function_code INTEGER NOT NULL,
                    register_address INTEGER NOT NULL,
                    register_count INTEGER NOT NULL,
                    data TEXT,
                    timestamp DATETIME NOT NULL,
                    success BOOLEAN NOT NULL DEFAULT 1,
                    response_time_ms REAL,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create indexes separately
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_device_timestamp
                ON modbus_data (device_id, timestamp DESC)
            """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON modbus_data (timestamp DESC)
            """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_success
                ON modbus_data (success)
            """
            )

            # Enable WAL mode for better concurrency
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.commit()

    async def _check_database_health(self) -> bool:
        """Check if database is accessible."""
        try:
            async with aiosqlite.connect(self.db_path, timeout=5.0) as conn:
                await conn.execute("SELECT 1")
                return True
        except Exception:
            return False

    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        try:
            import psutil  # type: ignore[import-untyped]

            process = psutil.Process()
            return float(process.memory_info().rss / 1024 / 1024)
        except ImportError:
            return 0.0

    async def _register_default_devices(self) -> None:
        """Register default test devices for development."""
        # TCP device
        tcp_device = ModbusDevice(
            device_id=1,
            name="Test TCP Device",
            connection_info=ModbusConnectionInfo(
                connection_type=ModbusConnectionType.TCP,
                host="127.0.0.1",
                port=5020,  # Default Modbus TCP port for testing
                device_address=1,
                timeout=3.0,
                retry_count=3,
            ),
            description="Default TCP test device for development",
        )

        # Resolve RTU port from ENV or defaults and build RTU device
        rtu_port = os.getenv("MODBUS_RTU_PORT") or "/dev/tty.usbserial-21230"
        # RTU device (if available for testing)
        rtu_device = ModbusDevice(
            device_id=2,
            name="Test RTU Device",
            connection_info=ModbusConnectionInfo(
                connection_type=ModbusConnectionType.RTU,
                host=rtu_port,  # Serial port from ENV/default
                device_address=1,
                timeout=3.0,
                retry_count=2,
            ),
            description="Default RTU test device for development",
        )

        # Register devices
        self.modbus_client.register_device(tcp_device)
        # Only register RTU device if serial port exists
        if os.path.exists(rtu_port):
            self.modbus_client.register_device(rtu_device)

        logger.info("🔧 Registered default test devices")

    async def _handle_devices(self, request: Request) -> Response:
        """List registered devices with their status."""
        connection_stats = self.modbus_client.get_connection_stats()
        devices_data = connection_stats.get("device_health", {})

        api_response = APIResponse.success_response(devices_data)
        return json_response(api_response.model_dump(mode="json"))

    async def _handle_connections(self, request: Request) -> Response:
        """Get connection pool statistics."""
        connection_stats = self.modbus_client.get_connection_stats()
        pool_stats = connection_stats.get("pool_stats", {})

        api_response = APIResponse.success_response(pool_stats)
        return json_response(api_response.model_dump(mode="json"))

    async def _handle_register_device(self, request: Request) -> Response:
        """Register a new Modbus device."""
        try:
            device_data = await request.json()

            # Create connection info
            connection_info = ModbusConnectionInfo(
                connection_type=ModbusConnectionType(device_data["connection_type"]),
                host=device_data["host"],
                port=device_data.get("port", 502),
                device_address=device_data.get("device_address", 1),
                timeout=device_data.get("timeout", 5.0),
                retry_count=device_data.get("retry_count", 3),
            )

            # Create device
            device = ModbusDevice(
                device_id=device_data["device_id"],
                name=device_data["name"],
                connection_info=connection_info,
                description=device_data.get("description", ""),
                enabled=device_data.get("enabled", True),
            )

            # Register device
            self.modbus_client.register_device(device)

            api_response = APIResponse.success_response(
                {
                    "device_id": device.device_id,
                    "name": device.name,
                    "status": "registered",
                }
            )
            return json_response(api_response.model_dump(mode="json"), status=201)

        except Exception as e:
            logger.error(f"Failed to register device: {e}", exc_info=True)
            error_response = APIResponse.error_response(f"Registration failed: {e}")
            return json_response(error_response.model_dump(mode="json"), status=400)

    async def _handle_device_connect(self, request: Request) -> Response:
        """Connect to a device."""
        # TODO: Implement device connection logic
        return json_response({"status": "not_implemented"}, status=501)

    async def _handle_device_disconnect(self, request: Request) -> Response:
        """Disconnect from a device."""
        # TODO: Implement device disconnection logic
        return json_response({"status": "not_implemented"}, status=501)


# ===== STANDALONE EXECUTION =====
async def main() -> None:
    """Main entry point for standalone execution."""
    import signal

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
        handlers=[logging.StreamHandler(), logging.FileHandler("logs/gateway_typed.log")],
    )

    # Create and start gateway
    gateway = TypedModbusGateway()

    # Setup graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}, shutting down...")
        shutdown_event.set()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        await gateway.start_server()
        logger.info("🎯 Gateway is running. Press Ctrl+C to stop.")
        await shutdown_event.wait()

    except KeyboardInterrupt:
        logger.info("🛑 Shutdown requested by user")
    except Exception as e:
        logger.error(f"❌ Gateway failed: {e}", exc_info=True)
    finally:
        await gateway.stop_server()


if __name__ == "__main__":
    asyncio.run(main())
