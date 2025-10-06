"""
Production Async Modbus Client with Connection Pooling
Provides high-performance, reliable Modbus communications with real devices.
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, AsyncContextManager, Optional

from pymodbus.client import AsyncModbusSerialClient, AsyncModbusTcpClient
from pymodbus.exceptions import ConnectionException
from pymodbus.pdu import ExceptionResponse

from ..core.types import (
    DeviceId,
    ModbusConnectionStatus,
    ModbusConnectionType,
    ModbusDevice,
    ModbusError,
    ModbusFunctionCode,
    ModbusRequest,
    ModbusResponse,
)

try:
    from ..core.log_filter import get_secure_logger
    logger = get_secure_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


@dataclass
class ConnectionStats:
    """Connection statistics for monitoring."""

    created_at: datetime = field(default_factory=datetime.now)
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    last_used: datetime = field(default_factory=datetime.now)

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100


class ModbusConnectionPool:
    """Async connection pool for Modbus clients."""

    def __init__(
        self,
        max_connections: int = 10,
        connection_timeout: float = 5.0,
        idle_timeout: float = 300.0,  # 5 minutes
    ):
        self.max_connections = max_connections
        self.connection_timeout = connection_timeout
        self.idle_timeout = idle_timeout

        # Pool management
        self._tcp_pools: dict[str, list[AsyncModbusTcpClient]] = {}
        self._serial_pools: dict[str, list[AsyncModbusSerialClient]] = {}
        self._pool_locks: dict[str, asyncio.Lock] = {}
        self._stats: dict[str, ConnectionStats] = {}

        # Connection tracking
        self._active_connections: set[str] = set()
        self._cleanup_task: Optional[asyncio.Task] = None

        logger.info(
            f"🔧 ModbusConnectionPool initialized: max={max_connections}, timeout={connection_timeout}s"
        )

    async def start(self) -> None:
        """Start the connection pool and cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_idle_connections())
        logger.info("🚀 ModbusConnectionPool started")

    async def stop(self) -> None:
        """Stop the connection pool and close all connections."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Close all connections
        for pool_name, clients in list(self._tcp_pools.items()):
            for client in clients:
                try:
                    await client.close()
                except Exception as e:
                    logger.warning(f"Error closing TCP connection {pool_name}: {e}")

        for pool_name, clients in list(self._serial_pools.items()):
            for client in clients:
                try:
                    await client.close()
                except Exception as e:
                    logger.warning(f"Error closing serial connection {pool_name}: {e}")

        self._tcp_pools.clear()
        self._serial_pools.clear()
        self._active_connections.clear()

        logger.info("🛑 ModbusConnectionPool stopped")

    def _get_pool_key(self, device: ModbusDevice) -> str:
        """Generate unique pool key for device."""
        conn = device.connection_info
        if conn.connection_type == ModbusConnectionType.TCP:
            return f"tcp:{conn.host}:{conn.port}"
        else:
            return f"serial:{conn.host}"  # host used as serial port path

    async def _create_tcp_client(self, device: ModbusDevice) -> AsyncModbusTcpClient:
        """Create new TCP client."""
        conn = device.connection_info
        client = AsyncModbusTcpClient(
            host=conn.host,
            port=conn.port,
            timeout=conn.timeout,
            retries=0,  # We handle retries at higher level
        )

        try:
            await asyncio.wait_for(client.connect(), timeout=conn.timeout)
            if not client.connected:
                raise ConnectionException(
                    f"Failed to connect to {conn.host}:{conn.port}"
                )

            logger.debug(f"✅ Created TCP connection to {conn.host}:{conn.port}")
            return client

        except Exception as e:
            try:
                await client.close()
            except:
                pass
            raise ConnectionException(f"TCP connection failed: {e}")

    async def _create_serial_client(
        self, device: ModbusDevice
    ) -> AsyncModbusSerialClient:
        """Create new serial client."""
        conn = device.connection_info
        client = AsyncModbusSerialClient(
            port=conn.host,  # host field used as serial port
            timeout=conn.timeout,
            retries=0,
            # RTU settings
            baudrate=9600,
            bytesize=8,
            parity="N",
            stopbits=1,
        )

        try:
            await asyncio.wait_for(client.connect(), timeout=conn.timeout)
            if not client.connected:
                raise ConnectionException(
                    f"Failed to connect to serial port {conn.host}"
                )

            logger.debug(f"✅ Created serial connection to {conn.host}")
            return client

        except Exception as e:
            try:
                await client.close()
            except:
                pass
            raise ConnectionException(f"Serial connection failed: {e}")

    @asynccontextmanager
    async def get_client(self, device: ModbusDevice) -> AsyncContextManager[Any]:
        """Get client from pool or create new one."""
        pool_key = self._get_pool_key(device)

        # Ensure pool lock exists
        if pool_key not in self._pool_locks:
            self._pool_locks[pool_key] = asyncio.Lock()

        async with self._pool_locks[pool_key]:
            client = None

            try:
                # Try to get existing client from pool
                if device.connection_info.connection_type == ModbusConnectionType.TCP:
                    pool = self._tcp_pools.get(pool_key, [])
                    if pool:
                        client = pool.pop()
                        # Verify connection is still good
                        if not client.connected:
                            await client.close()
                            client = None
                else:
                    pool = self._serial_pools.get(pool_key, [])
                    if pool:
                        client = pool.pop()
                        if not client.connected:
                            await client.close()
                            client = None

                # Create new client if needed
                if client is None:
                    if (
                        device.connection_info.connection_type
                        == ModbusConnectionType.TCP
                    ):
                        client = await self._create_tcp_client(device)
                    else:
                        client = await self._create_serial_client(device)

                # Update stats
                if pool_key not in self._stats:
                    self._stats[pool_key] = ConnectionStats()
                self._stats[pool_key].last_used = datetime.now()

                # Track active connection
                self._active_connections.add(pool_key)

                yield client

            except Exception:
                if client:
                    try:
                        await client.close()
                    except:
                        pass
                    client = None
                raise

            finally:
                # Return client to pool if still connected
                if client and client.connected:
                    if (
                        device.connection_info.connection_type
                        == ModbusConnectionType.TCP
                    ):
                        if pool_key not in self._tcp_pools:
                            self._tcp_pools[pool_key] = []
                        if len(self._tcp_pools[pool_key]) < self.max_connections:
                            self._tcp_pools[pool_key].append(client)
                        else:
                            await client.close()
                    else:
                        if pool_key not in self._serial_pools:
                            self._serial_pools[pool_key] = []
                        if len(self._serial_pools[pool_key]) < self.max_connections:
                            self._serial_pools[pool_key].append(client)
                        else:
                            await client.close()

                # Remove from active connections
                self._active_connections.discard(pool_key)

    async def _cleanup_idle_connections(self) -> None:
        """Cleanup idle connections periodically."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute

                cutoff_time = datetime.now() - timedelta(seconds=self.idle_timeout)

                # Cleanup idle connections
                for pool_key, stats in list(self._stats.items()):
                    if (
                        stats.last_used < cutoff_time
                        and pool_key not in self._active_connections
                    ):
                        await self._close_pool_connections(pool_key)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in connection cleanup: {e}")

    async def _close_pool_connections(self, pool_key: str) -> None:
        """Close all connections in a pool."""
        # Close TCP connections
        if pool_key in self._tcp_pools:
            for client in self._tcp_pools[pool_key]:
                try:
                    await client.close()
                except Exception as e:
                    logger.debug(f"Error closing TCP client: {e}")
            del self._tcp_pools[pool_key]

        # Close serial connections
        if pool_key in self._serial_pools:
            for client in self._serial_pools[pool_key]:
                try:
                    await client.close()
                except Exception as e:
                    logger.debug(f"Error closing serial client: {e}")
            del self._serial_pools[pool_key]

        # Remove stats
        if pool_key in self._stats:
            del self._stats[pool_key]

        # Remove lock
        if pool_key in self._pool_locks:
            del self._pool_locks[pool_key]

        logger.debug(f"🧹 Cleaned up idle connections for {pool_key}")

    def get_stats(self) -> dict[str, dict[str, Any]]:
        """Get connection pool statistics."""
        return {
            pool_key: {
                "total_requests": stats.total_requests,
                "successful_requests": stats.successful_requests,
                "failed_requests": stats.failed_requests,
                "success_rate": stats.success_rate,
                "last_used": stats.last_used.isoformat(),
                "tcp_pool_size": len(self._tcp_pools.get(pool_key, [])),
                "serial_pool_size": len(self._serial_pools.get(pool_key, [])),
                "active": pool_key in self._active_connections,
            }
            for pool_key, stats in self._stats.items()
        }


class AsyncModbusClient:
    """Production async Modbus client with retry logic and error handling."""

    def __init__(
        self,
        connection_pool: Optional[ModbusConnectionPool] = None,
        default_retry_count: int = 3,
        default_retry_delay: float = 1.0,
    ):
        self.pool = connection_pool or ModbusConnectionPool()
        self.default_retry_count = default_retry_count
        self.default_retry_delay = default_retry_delay
        self.device_registry: dict[DeviceId, ModbusDevice] = {}

        logger.info("🔧 AsyncModbusClient initialized")

    async def start(self) -> None:
        """Start the Modbus client."""
        await self.pool.start()
        logger.info("🚀 AsyncModbusClient started")

    async def stop(self) -> None:
        """Stop the Modbus client."""
        await self.pool.stop()
        logger.info("🛑 AsyncModbusClient stopped")

    def register_device(self, device: ModbusDevice) -> None:
        """Register a device for monitoring and management."""
        self.device_registry[device.device_id] = device
        logger.info(f"📝 Registered device {device.device_id}: {device.name}")

    def unregister_device(self, device_id: DeviceId) -> None:
        """Unregister a device."""
        if device_id in self.device_registry:
            device = self.device_registry.pop(device_id)
            logger.info(f"🗑️ Unregistered device {device_id}: {device.name}")

    def get_device(self, device_id: DeviceId) -> Optional[ModbusDevice]:
        """Get registered device by ID."""
        return self.device_registry.get(device_id)

    async def execute_request(self, request: ModbusRequest) -> ModbusResponse:
        """Execute a Modbus request with retry logic and error handling."""
        device = self.device_registry.get(request.device_id)
        if not device:
            raise ModbusError(
                f"Device {request.device_id} not registered", request.device_id
            )

        if not device.enabled:
            raise ModbusError(
                f"Device {request.device_id} is disabled", request.device_id
            )

        retry_count = device.connection_info.retry_count or self.default_retry_count
        retry_delay = self.default_retry_delay

        last_exception = None

        for attempt in range(retry_count + 1):
            try:
                device.total_requests += 1
                start_time = time.perf_counter()

                # Update device status
                if device.status != ModbusConnectionStatus.CONNECTED:
                    device.status = ModbusConnectionStatus.CONNECTING

                # Execute request
                if request.write_values is not None:
                    response = await self._execute_write_request(device, request)
                else:
                    response = await self._execute_read_request(device, request)

                # Update device stats on success
                device.successful_requests += 1
                device.status = ModbusConnectionStatus.CONNECTED
                device.last_success = datetime.now()
                device.last_error = None

                return response

            except Exception as e:
                last_exception = e
                device.status = ModbusConnectionStatus.ERROR
                device.last_error = str(e)

                logger.warning(
                    f"Modbus request failed (attempt {attempt + 1}/{retry_count + 1})",
                    extra={
                        "device_id": request.device_id,
                        "function_code": request.function_code,
                        "error": str(e),
                        "attempt": attempt + 1,
                    },
                )

                if attempt < retry_count:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5  # Exponential backoff

        # All retries failed
        response_time_ms = time.perf_counter() * 1000
        return ModbusResponse(
            request=request,
            success=False,
            error_message=f"All {retry_count + 1} attempts failed. Last error: {last_exception}",
            response_time_ms=response_time_ms,
        )

    async def _execute_read_request(
        self, device: ModbusDevice, request: ModbusRequest
    ) -> ModbusResponse:
        """Execute a Modbus read request."""
        start_time = time.perf_counter()

        async with self.pool.get_client(device) as client:
            slave_address = device.connection_info.device_address

            try:
                if request.function_code == ModbusFunctionCode.READ_COILS:
                    result = await client.read_coils(
                        request.register_address,
                        request.register_count,
                        slave=slave_address,
                    )
                elif request.function_code == ModbusFunctionCode.READ_DISCRETE_INPUTS:
                    result = await client.read_discrete_inputs(
                        request.register_address,
                        request.register_count,
                        slave=slave_address,
                    )
                elif request.function_code == ModbusFunctionCode.READ_HOLDING_REGISTERS:
                    result = await client.read_holding_registers(
                        request.register_address,
                        request.register_count,
                        slave=slave_address,
                    )
                elif request.function_code == ModbusFunctionCode.READ_INPUT_REGISTERS:
                    result = await client.read_input_registers(
                        request.register_address,
                        request.register_count,
                        slave=slave_address,
                    )
                else:
                    raise ModbusError(
                        f"Unsupported read function code: {request.function_code}",
                        request.device_id,
                    )

                # Check for Modbus errors
                if isinstance(result, ExceptionResponse):
                    raise ModbusError(f"Modbus exception: {result}", request.device_id)

                if result.isError():
                    raise ModbusError(f"Modbus error: {result}", request.device_id)

                # Extract data based on function code
                if request.function_code in [
                    ModbusFunctionCode.READ_COILS,
                    ModbusFunctionCode.READ_DISCRETE_INPUTS,
                ]:
                    data = [bool(bit) for bit in result.bits[: request.register_count]]
                else:
                    data = list(result.registers)

                response_time_ms = (time.perf_counter() - start_time) * 1000

                return ModbusResponse(
                    request=request,
                    success=True,
                    data=data,
                    response_time_ms=response_time_ms,
                )

            except Exception as e:
                response_time_ms = (time.perf_counter() - start_time) * 1000
                raise ModbusError(f"Read operation failed: {e}", request.device_id)

    async def _execute_write_request(
        self, device: ModbusDevice, request: ModbusRequest
    ) -> ModbusResponse:
        """Execute a Modbus write request."""
        start_time = time.perf_counter()

        if not request.write_values:
            raise ModbusError(
                "Write values are required for write operations", request.device_id
            )

        async with self.pool.get_client(device) as client:
            slave_address = device.connection_info.device_address

            try:
                if request.function_code == ModbusFunctionCode.WRITE_SINGLE_COIL:
                    if len(request.write_values) != 1:
                        raise ModbusError(
                            "Single coil write requires exactly one value",
                            request.device_id,
                        )
                    result = await client.write_coil(
                        request.register_address,
                        bool(request.write_values[0]),
                        slave=slave_address,
                    )
                elif request.function_code == ModbusFunctionCode.WRITE_SINGLE_REGISTER:
                    if len(request.write_values) != 1:
                        raise ModbusError(
                            "Single register write requires exactly one value",
                            request.device_id,
                        )
                    result = await client.write_register(
                        request.register_address,
                        int(request.write_values[0]),
                        slave=slave_address,
                    )
                elif request.function_code == ModbusFunctionCode.WRITE_MULTIPLE_COILS:
                    coil_values = [bool(v) for v in request.write_values]
                    result = await client.write_coils(
                        request.register_address, coil_values, slave=slave_address
                    )
                elif (
                    request.function_code == ModbusFunctionCode.WRITE_MULTIPLE_REGISTERS
                ):
                    register_values = [int(v) for v in request.write_values]
                    result = await client.write_registers(
                        request.register_address, register_values, slave=slave_address
                    )
                else:
                    raise ModbusError(
                        f"Unsupported write function code: {request.function_code}",
                        request.device_id,
                    )

                # Check for Modbus errors
                if isinstance(result, ExceptionResponse):
                    raise ModbusError(f"Modbus exception: {result}", request.device_id)

                if result.isError():
                    raise ModbusError(f"Modbus error: {result}", request.device_id)

                response_time_ms = (time.perf_counter() - start_time) * 1000

                return ModbusResponse(
                    request=request, success=True, response_time_ms=response_time_ms
                )

            except Exception as e:
                response_time_ms = (time.perf_counter() - start_time) * 1000
                raise ModbusError(f"Write operation failed: {e}", request.device_id)

    def get_connection_stats(self) -> dict[str, Any]:
        """Get connection pool statistics."""
        return {
            "pool_stats": self.pool.get_stats(),
            "registered_devices": len(self.device_registry),
            "device_health": {
                device_id: {
                    "name": device.name,
                    "enabled": device.enabled,
                    "status": device.status.name,
                    "success_rate": device.success_rate,
                    "is_healthy": device.is_healthy,
                    "last_success": device.last_success.isoformat()
                    if device.last_success
                    else None,
                    "last_error": device.last_error,
                    "total_requests": device.total_requests,
                    "successful_requests": device.successful_requests,
                }
                for device_id, device in self.device_registry.items()
            },
        }
