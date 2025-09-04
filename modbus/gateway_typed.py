"""
Typed Modbus TCP Gateway for КУБ-1063
Async version with full type safety and modern Python practices.

This is the typed version that will gradually replace gateway.py
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Set, Any, AsyncContextManager
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from aiohttp import web, ClientSession
from aiohttp.web import Request, Response, json_response

# Import our type definitions
from core.types import (
    ModbusRequest, ModbusResponse, ModbusDevice, DeviceId, RegisterValue,
    APIResponse, SystemEvent, EventType, PerformanceMetric,
    AsyncDatabaseProtocol, AsyncModbusClientProtocol,
    ModbusFunctionCode, DatabaseRecord, CubeRSError, ModbusError
)

# Configure structured logging
logger = logging.getLogger(__name__)


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
        max_concurrent_requests: int = 100
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
        
        # Device management
        self.connected_devices: Dict[DeviceId, ModbusDevice] = {}
        self.device_stats: Dict[DeviceId, Dict[str, Any]] = {}
        
        # Performance monitoring
        self.request_counter: int = 0
        self.error_counter: int = 0
        self.start_time: datetime = datetime.now()
        self.response_times: List[float] = []
        
        # Concurrency control
        self.request_semaphore = asyncio.Semaphore(max_concurrent_requests)
        self.db_lock = asyncio.Lock()
        
        logger.info(
            f"🏗️ TypedModbusGateway initialized",
            extra={
                "host": self.host,
                "port": self.port, 
                "db_path": str(self.db_path),
                "max_concurrent": self.max_concurrent_requests
            }
        )

    async def start_server(self) -> None:
        """Start the async HTTP server for Modbus operations."""
        if self.running:
            logger.warning("Gateway already running")
            return
            
        try:
            # Initialize database
            await self._init_database()
            
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
                f"🚀 TypedModbusGateway started",
                extra={
                    "address": f"{self.host}:{self.port}",
                    "endpoints": [
                        f"http://{self.host}:{self.port}/modbus/read",
                        f"http://{self.host}:{self.port}/modbus/write", 
                        f"http://{self.host}:{self.port}/health",
                        f"http://{self.host}:{self.port}/metrics"
                    ]
                }
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
        self.app.router.add_post('/modbus/read', self._handle_modbus_read)
        self.app.router.add_post('/modbus/write', self._handle_modbus_write)
        
        # Monitoring endpoints
        self.app.router.add_get('/health', self._handle_health_check)
        self.app.router.add_get('/metrics', self._handle_metrics)
        self.app.router.add_get('/devices', self._handle_devices)
        
        # Administrative endpoints
        self.app.router.add_post('/devices/{device_id}/connect', self._handle_device_connect)
        self.app.router.add_delete('/devices/{device_id}', self._handle_device_disconnect)

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
                    "user_agent": request.headers.get("User-Agent", "unknown")
                }
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
                    "remote_ip": request.remote
                },
                exc_info=True
            )
            
            # Return structured error response
            error_response = APIResponse.error_response(
                f"Internal server error: {type(e).__name__}"
            )
            return json_response(error_response.model_dump(), status=500)

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
                    "Access-Control-Allow-Headers": "Content-Type, Authorization"
                }
            )
            
        response = await handler(request)
        
        # Add CORS headers
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        
        return response

    async def _handle_modbus_read(self, request: Request) -> Response:
        """Handle Modbus read request with full type safety."""
        async with self.request_semaphore:
            try:
                # Parse and validate request
                request_data = await request.json()
                modbus_request = ModbusRequest(**request_data)
                
                # Perform read operation
                response = await self._execute_modbus_read(modbus_request)
                
                # Save to database
                await self._save_to_database(response)
                
                # Return structured response
                api_response = APIResponse.success_response(response.model_dump())
                return json_response(api_response.model_dump())
                
            except ValueError as e:
                logger.warning(f"Invalid request data: {e}")
                error_response = APIResponse.error_response(f"Validation error: {e}")
                return json_response(error_response.model_dump(), status=400)
                
            except ModbusError as e:
                logger.error(f"Modbus operation failed: {e}")
                error_response = APIResponse.error_response(f"Modbus error: {e}")
                return json_response(error_response.model_dump(), status=502)
                
            except Exception as e:
                logger.error(f"Unexpected error in modbus read: {e}", exc_info=True)
                error_response = APIResponse.error_response("Internal server error")
                return json_response(error_response.model_dump(), status=500)

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
                    ModbusFunctionCode.WRITE_MULTIPLE_REGISTERS
                }
                
                if modbus_request.function_code not in write_functions:
                    raise ValueError(f"Function code {modbus_request.function_code} is not for write operations")
                
                response = await self._execute_modbus_write(modbus_request)
                await self._save_to_database(response)
                
                api_response = APIResponse.success_response(response.model_dump())
                return json_response(api_response.model_dump())
                
            except ValueError as e:
                error_response = APIResponse.error_response(f"Validation error: {e}")
                return json_response(error_response.model_dump(), status=400)
            except Exception as e:
                logger.error(f"Write operation failed: {e}", exc_info=True)
                error_response = APIResponse.error_response("Write operation failed")
                return json_response(error_response.model_dump(), status=500)

    async def _handle_health_check(self, request: Request) -> Response:
        """Health check endpoint with detailed status."""
        try:
            # Test database connection
            db_healthy = await self._check_database_health()
            
            # Calculate uptime
            uptime_seconds = (datetime.now() - self.start_time).total_seconds()
            
            # Calculate success rate
            total_requests = self.request_counter
            success_rate = (
                (total_requests - self.error_counter) / total_requests * 100
                if total_requests > 0 else 100.0
            )
            
            # Calculate average response time
            avg_response_time = (
                sum(self.response_times) / len(self.response_times)
                if self.response_times else 0.0
            )
            
            health_data = {
                "status": "healthy" if db_healthy else "degraded",
                "timestamp": datetime.now().isoformat(),
                "uptime_seconds": round(uptime_seconds, 1),
                "version": "2.0.0-typed",
                "database_healthy": db_healthy,
                "total_requests": total_requests,
                "error_count": self.error_counter,
                "success_rate_percent": round(success_rate, 2),
                "avg_response_time_ms": round(avg_response_time, 2),
                "connected_devices": len(self.connected_devices),
                "concurrent_limit": self.max_concurrent_requests,
                "memory_usage_mb": self._get_memory_usage()
            }
            
            status_code = 200 if db_healthy else 503
            api_response = APIResponse.success_response(health_data)
            return json_response(api_response.model_dump(), status=status_code)
            
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            error_response = APIResponse.error_response("Health check failed")
            return json_response(error_response.model_dump(), status=503)

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
                
                metrics.append(f"cube_rs_response_time_p50_ms {sorted_times[p50_idx]:.2f}")
                metrics.append(f"cube_rs_response_time_p95_ms {sorted_times[p95_idx]:.2f}") 
                metrics.append(f"cube_rs_response_time_p99_ms {sorted_times[p99_idx]:.2f}")
            
            # Device metrics
            metrics.append(f"cube_rs_connected_devices {len(self.connected_devices)}")
            
            # System metrics
            uptime = (datetime.now() - self.start_time).total_seconds()
            metrics.append(f"cube_rs_uptime_seconds {uptime:.1f}")
            metrics.append(f"cube_rs_memory_usage_mb {self._get_memory_usage():.1f}")
            
            return web.Response(text="\n".join(metrics), content_type="text/plain")
            
        except Exception as e:
            logger.error(f"Metrics generation failed: {e}", exc_info=True)
            return web.Response(text="# Metrics unavailable", status=503)

    async def _execute_modbus_read(self, request: ModbusRequest) -> ModbusResponse:
        """Execute Modbus read operation with proper error handling."""
        start_time = time.perf_counter()
        
        try:
            # For now, simulate reading with test data
            # TODO: Replace with real pymodbus async client
            await asyncio.sleep(0.01)  # Simulate I/O delay
            
            # Generate test data based on function code
            test_data: List[RegisterValue]
            if request.function_code == ModbusFunctionCode.READ_COILS:
                # Boolean values for coils
                test_data = [bool(i % 2) for i in range(request.register_count)]
            elif request.function_code == ModbusFunctionCode.READ_DISCRETE_INPUTS:
                # Boolean values for discrete inputs
                test_data = [bool((i + 1) % 2) for i in range(request.register_count)]
            else:
                # Integer values for registers
                test_data = [42 + i * 10 for i in range(request.register_count)]
            
            response_time_ms = (time.perf_counter() - start_time) * 1000
            
            return ModbusResponse(
                request=request,
                success=True,
                data=test_data,
                response_time_ms=response_time_ms
            )
            
        except Exception as e:
            response_time_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"Modbus read failed: {e}", exc_info=True)
            
            return ModbusResponse(
                request=request,
                success=False,
                error_message=str(e),
                response_time_ms=response_time_ms
            )

    async def _execute_modbus_write(self, request: ModbusRequest) -> ModbusResponse:
        """Execute Modbus write operation."""
        start_time = time.perf_counter()
        
        try:
            # TODO: Implement real Modbus writing
            await asyncio.sleep(0.02)  # Simulate write delay
            
            response_time_ms = (time.perf_counter() - start_time) * 1000
            
            return ModbusResponse(
                request=request,
                success=True,
                response_time_ms=response_time_ms
            )
            
        except Exception as e:
            response_time_ms = (time.perf_counter() - start_time) * 1000
            
            return ModbusResponse(
                request=request,
                success=False,
                error_message=str(e),
                response_time_ms=response_time_ms
            )

    async def _save_to_database(self, response: ModbusResponse) -> None:
        """Save Modbus response to database with proper async handling."""
        async with self.db_lock:
            try:
                async with aiosqlite.connect(self.db_path) as conn:
                    await conn.execute("""
                        INSERT INTO modbus_data (
                            device_id, function_code, register_address, register_count,
                            data, timestamp, success, response_time_ms, error_message
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        response.request.device_id,
                        response.request.function_code.value,
                        response.request.register_address,
                        response.request.register_count,
                        str(response.data) if response.data else None,
                        response.timestamp.isoformat(),
                        response.success,
                        response.response_time_ms,
                        response.error_message
                    ))
                    await conn.commit()
                    
            except Exception as e:
                logger.error(f"Database save failed: {e}", exc_info=True)
                # Don't re-raise - this shouldn't fail the Modbus operation

    async def _init_database(self) -> None:
        """Initialize database schema."""
        async with aiosqlite.connect(self.db_path) as conn:
            # Create table
            await conn.execute("""
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
            """)
            
            # Create indexes separately
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_device_timestamp 
                ON modbus_data (device_id, timestamp DESC)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON modbus_data (timestamp DESC)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_success 
                ON modbus_data (success)
            """)
            
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

    # Placeholder methods for device management
    async def _handle_devices(self, request: Request) -> Response:
        """List connected devices."""
        devices_data = [
            {
                "device_id": device.device_id,
                "name": device.name,
                "enabled": device.enabled,
                "stats": self.device_stats.get(device.device_id, {})
            }
            for device in self.connected_devices.values()
        ]
        
        api_response = APIResponse.success_response(devices_data)
        return json_response(api_response.model_dump())

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
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("gateway_typed.log")
        ]
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