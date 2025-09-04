"""
Integration tests for AsyncModbusClient
Tests real Modbus communication with mock devices and error scenarios.
"""
import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
from typing import List, Dict, Any

from core.types import (
    ModbusDevice, ModbusRequest, ModbusResponse, ModbusFunctionCode,
    ModbusConnectionInfo, ModbusConnectionType, ModbusConnectionStatus,
    ModbusError
)
from modbus.async_client import AsyncModbusClient, ModbusConnectionPool


@pytest.mark.integration
class TestModbusConnectionPool:
    """Integration tests for connection pool management."""

    @pytest.fixture
    async def connection_pool(self):
        """Create connection pool for testing."""
        pool = ModbusConnectionPool(
            max_connections=5,
            connection_timeout=2.0,
            idle_timeout=10.0
        )
        await pool.start()
        yield pool
        await pool.stop()

    @pytest.fixture
    def tcp_device(self):
        """Create TCP device for testing."""
        return ModbusDevice(
            device_id=1,
            name="Test TCP Device",
            connection_info=ModbusConnectionInfo(
                connection_type=ModbusConnectionType.TCP,
                host="127.0.0.1",
                port=5020,  # Non-standard port to avoid conflicts
                device_address=1,
                timeout=2.0,
                retry_count=2
            )
        )

    @pytest.mark.asyncio
    async def test_connection_pool_initialization(self, connection_pool):
        """Test connection pool initializes correctly."""
        assert connection_pool.max_connections == 5
        assert connection_pool.connection_timeout == 2.0
        assert connection_pool.idle_timeout == 10.0
        assert len(connection_pool._tcp_pools) == 0
        assert len(connection_pool._serial_pools) == 0

    @pytest.mark.asyncio
    async def test_connection_pool_stats(self, connection_pool):
        """Test connection pool statistics."""
        stats = connection_pool.get_stats()
        assert isinstance(stats, dict)
        assert len(stats) == 0  # No connections created yet

    @pytest.mark.asyncio
    async def test_tcp_client_creation_failure(self, connection_pool, tcp_device):
        """Test handling of TCP connection failures."""
        # Try to connect to non-existent server
        tcp_device.connection_info.port = 9999  # Non-existent port
        
        with pytest.raises(Exception):  # Should raise ConnectionException
            async with connection_pool.get_client(tcp_device) as client:
                pass

    @pytest.mark.asyncio 
    async def test_pool_key_generation(self, connection_pool):
        """Test pool key generation for different device types."""
        tcp_device = ModbusDevice(
            device_id=1,
            name="TCP Device",
            connection_info=ModbusConnectionInfo(
                connection_type=ModbusConnectionType.TCP,
                host="192.168.1.100",
                port=502,
                device_address=1
            )
        )
        
        rtu_device = ModbusDevice(
            device_id=2,
            name="RTU Device",
            connection_info=ModbusConnectionInfo(
                connection_type=ModbusConnectionType.RTU,
                host="/dev/ttyUSB0",
                device_address=1
            )
        )
        
        tcp_key = connection_pool._get_pool_key(tcp_device)
        rtu_key = connection_pool._get_pool_key(rtu_device)
        
        assert tcp_key == "tcp:192.168.1.100:502"
        assert rtu_key == "serial:/dev/ttyUSB0"
        assert tcp_key != rtu_key


@pytest.mark.integration
class TestAsyncModbusClient:
    """Integration tests for AsyncModbusClient."""

    @pytest.fixture
    async def modbus_client(self):
        """Create Modbus client for testing."""
        client = AsyncModbusClient(
            connection_pool=ModbusConnectionPool(max_connections=3),
            default_retry_count=2,
            default_retry_delay=0.1
        )
        await client.start()
        yield client
        await client.stop()

    @pytest.fixture
    def tcp_device(self):
        """Create TCP device for testing."""
        return ModbusDevice(
            device_id=1,
            name="Test TCP Device",
            connection_info=ModbusConnectionInfo(
                connection_type=ModbusConnectionType.TCP,
                host="127.0.0.1",
                port=5020,
                device_address=1,
                timeout=1.0,
                retry_count=1
            )
        )

    @pytest.fixture
    def read_request(self):
        """Create read request for testing."""
        return ModbusRequest(
            device_id=1,
            function_code=ModbusFunctionCode.READ_HOLDING_REGISTERS,
            register_address=0,
            register_count=5
        )

    @pytest.fixture 
    def write_request(self):
        """Create write request for testing."""
        return ModbusRequest(
            device_id=1,
            function_code=ModbusFunctionCode.WRITE_SINGLE_REGISTER,
            register_address=100,
            register_count=1,
            write_values=[1234]
        )

    @pytest.mark.asyncio
    async def test_device_registration(self, modbus_client, tcp_device):
        """Test device registration and management."""
        # Register device
        modbus_client.register_device(tcp_device)
        
        # Verify registration
        registered_device = modbus_client.get_device(tcp_device.device_id)
        assert registered_device is not None
        assert registered_device.device_id == tcp_device.device_id
        assert registered_device.name == tcp_device.name
        
        # Check stats
        stats = modbus_client.get_connection_stats()
        assert stats["registered_devices"] == 1
        assert tcp_device.device_id in stats["device_health"]

    @pytest.mark.asyncio
    async def test_device_unregistration(self, modbus_client, tcp_device):
        """Test device unregistration."""
        # Register and then unregister
        modbus_client.register_device(tcp_device)
        modbus_client.unregister_device(tcp_device.device_id)
        
        # Verify unregistration
        registered_device = modbus_client.get_device(tcp_device.device_id)
        assert registered_device is None
        
        stats = modbus_client.get_connection_stats()
        assert stats["registered_devices"] == 0

    @pytest.mark.asyncio
    async def test_unregistered_device_request(self, modbus_client, read_request):
        """Test request to unregistered device."""
        with pytest.raises(ModbusError, match="Device 1 not registered"):
            await modbus_client.execute_request(read_request)

    @pytest.mark.asyncio
    async def test_disabled_device_request(self, modbus_client, tcp_device, read_request):
        """Test request to disabled device."""
        # Register disabled device
        tcp_device.enabled = False
        modbus_client.register_device(tcp_device)
        
        with pytest.raises(ModbusError, match="Device 1 is disabled"):
            await modbus_client.execute_request(read_request)

    @pytest.mark.asyncio
    @patch('modbus.async_client.AsyncModbusTcpClient')
    async def test_successful_read_request(self, mock_tcp_client_class, modbus_client, tcp_device, read_request):
        """Test successful read request execution."""
        # Mock the client and its methods
        mock_client = AsyncMock()
        mock_client.connected = True
        mock_tcp_client_class.return_value = mock_client
        
        # Mock successful connection
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = AsyncMock()
        
        # Mock successful read response
        mock_response = Mock()
        mock_response.isError.return_value = False
        mock_response.registers = [42, 100, 255, 0, 128]
        mock_client.read_holding_registers = AsyncMock(return_value=mock_response)
        
        # Register device and execute request
        modbus_client.register_device(tcp_device)
        response = await modbus_client.execute_request(read_request)
        
        # Verify response
        assert response.success is True
        assert response.data == [42, 100, 255, 0, 128]
        assert response.error_message is None
        assert response.response_time_ms > 0
        
        # Verify device stats updated
        device = modbus_client.get_device(tcp_device.device_id)
        assert device.total_requests == 1
        assert device.successful_requests == 1
        assert device.status == ModbusConnectionStatus.CONNECTED
        assert device.last_success is not None

    @pytest.mark.asyncio
    @patch('modbus.async_client.AsyncModbusTcpClient')
    async def test_successful_write_request(self, mock_tcp_client_class, modbus_client, tcp_device, write_request):
        """Test successful write request execution."""
        # Mock the client and its methods
        mock_client = AsyncMock()
        mock_client.connected = True
        mock_tcp_client_class.return_value = mock_client
        
        # Mock successful connection
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = AsyncMock()
        
        # Mock successful write response
        mock_response = Mock()
        mock_response.isError.return_value = False
        mock_client.write_register = AsyncMock(return_value=mock_response)
        
        # Register device and execute request
        modbus_client.register_device(tcp_device)
        response = await modbus_client.execute_request(write_request)
        
        # Verify response
        assert response.success is True
        assert response.error_message is None
        assert response.response_time_ms > 0
        
        # Verify write was called with correct parameters
        mock_client.write_register.assert_called_once_with(
            write_request.register_address,
            write_request.write_values[0],
            slave=tcp_device.connection_info.device_address
        )

    @pytest.mark.asyncio
    @patch('modbus.async_client.AsyncModbusTcpClient')
    async def test_connection_failure_with_retry(self, mock_tcp_client_class, modbus_client, tcp_device, read_request):
        """Test connection failure handling with retry logic."""
        # Mock client that always fails to connect
        mock_client = AsyncMock()
        mock_client.connected = False
        mock_tcp_client_class.return_value = mock_client
        
        mock_client.connect = AsyncMock(side_effect=Exception("Connection failed"))
        mock_client.close = AsyncMock()
        
        # Register device and execute request
        modbus_client.register_device(tcp_device)
        response = await modbus_client.execute_request(read_request)
        
        # Verify response indicates failure
        assert response.success is False
        assert "Connection failed" in response.error_message
        assert response.data is None
        
        # Verify device stats updated
        device = modbus_client.get_device(tcp_device.device_id)
        assert device.total_requests == 1
        assert device.successful_requests == 0
        assert device.status == ModbusConnectionStatus.ERROR
        assert device.last_error is not None

    @pytest.mark.asyncio
    async def test_connection_stats_collection(self, modbus_client, tcp_device):
        """Test connection statistics collection."""
        modbus_client.register_device(tcp_device)
        
        stats = modbus_client.get_connection_stats()
        
        assert "pool_stats" in stats
        assert "registered_devices" in stats
        assert "device_health" in stats
        assert stats["registered_devices"] == 1
        assert tcp_device.device_id in stats["device_health"]
        
        device_stats = stats["device_health"][tcp_device.device_id]
        assert "name" in device_stats
        assert "enabled" in device_stats
        assert "status" in device_stats
        assert "success_rate" in device_stats
        assert "is_healthy" in device_stats

    @pytest.mark.asyncio
    @patch('modbus.async_client.AsyncModbusTcpClient') 
    async def test_different_function_codes(self, mock_tcp_client_class, modbus_client, tcp_device):
        """Test different Modbus function codes."""
        mock_client = AsyncMock()
        mock_client.connected = True
        mock_tcp_client_class.return_value = mock_client
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = AsyncMock()
        
        modbus_client.register_device(tcp_device)
        
        # Test READ_COILS
        mock_response_coils = Mock()
        mock_response_coils.isError.return_value = False
        mock_response_coils.bits = [True, False, True, False, True]
        mock_client.read_coils = AsyncMock(return_value=mock_response_coils)
        
        coils_request = ModbusRequest(
            device_id=1,
            function_code=ModbusFunctionCode.READ_COILS,
            register_address=0,
            register_count=5
        )
        
        response = await modbus_client.execute_request(coils_request)
        assert response.success is True
        assert response.data == [True, False, True, False, True]
        
        # Test READ_DISCRETE_INPUTS
        mock_response_discrete = Mock()
        mock_response_discrete.isError.return_value = False
        mock_response_discrete.bits = [False, True, False]
        mock_client.read_discrete_inputs = AsyncMock(return_value=mock_response_discrete)
        
        discrete_request = ModbusRequest(
            device_id=1,
            function_code=ModbusFunctionCode.READ_DISCRETE_INPUTS,
            register_address=10,
            register_count=3
        )
        
        response = await modbus_client.execute_request(discrete_request)
        assert response.success is True
        assert response.data == [False, True, False]

    @pytest.mark.asyncio
    async def test_device_health_calculation(self, modbus_client, tcp_device):
        """Test device health status calculation."""
        modbus_client.register_device(tcp_device)
        device = modbus_client.get_device(tcp_device.device_id)
        
        # Initially unhealthy (no requests yet)
        assert device.success_rate == 0.0
        assert device.is_healthy is False
        
        # Simulate some requests
        device.total_requests = 100
        device.successful_requests = 95
        device.status = ModbusConnectionStatus.CONNECTED
        
        # Now should be healthy (95% success rate > 80%)
        assert device.success_rate == 95.0
        assert device.is_healthy is True
        
        # Simulate degraded performance
        device.successful_requests = 70  # 70% success rate
        assert device.success_rate == 70.0
        assert device.is_healthy is False  # Below 80% threshold


@pytest.mark.integration
@pytest.mark.slow
class TestModbusClientPerformance:
    """Performance tests for Modbus client."""

    @pytest.fixture
    async def modbus_client(self):
        """Create high-performance Modbus client."""
        client = AsyncModbusClient(
            connection_pool=ModbusConnectionPool(max_connections=20),
            default_retry_count=1,
            default_retry_delay=0.05
        )
        await client.start()
        yield client
        await client.stop()

    @pytest.mark.asyncio
    @patch('modbus.async_client.AsyncModbusTcpClient')
    async def test_concurrent_requests(self, mock_tcp_client_class, modbus_client):
        """Test handling multiple concurrent requests."""
        # Setup mock client
        mock_client = AsyncMock()
        mock_client.connected = True
        mock_tcp_client_class.return_value = mock_client
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = AsyncMock()
        
        # Mock successful responses
        mock_response = Mock()
        mock_response.isError.return_value = False
        mock_response.registers = [42, 100, 255]
        mock_client.read_holding_registers = AsyncMock(return_value=mock_response)
        
        # Register multiple devices
        devices = []
        for i in range(5):
            device = ModbusDevice(
                device_id=i + 1,
                name=f"Device {i + 1}",
                connection_info=ModbusConnectionInfo(
                    connection_type=ModbusConnectionType.TCP,
                    host="127.0.0.1",
                    port=5020 + i,
                    device_address=1,
                    timeout=1.0
                )
            )
            devices.append(device)
            modbus_client.register_device(device)
        
        # Create concurrent requests
        requests = []
        for i in range(20):  # 20 concurrent requests across 5 devices
            request = ModbusRequest(
                device_id=(i % 5) + 1,
                function_code=ModbusFunctionCode.READ_HOLDING_REGISTERS,
                register_address=i * 10,
                register_count=3
            )
            requests.append(modbus_client.execute_request(request))
        
        # Execute all requests concurrently
        start_time = asyncio.get_event_loop().time()
        responses = await asyncio.gather(*requests)
        end_time = asyncio.get_event_loop().time()
        
        # Verify all requests succeeded
        assert len(responses) == 20
        assert all(response.success for response in responses)
        
        # Should complete relatively quickly (concurrent execution)
        total_time = end_time - start_time
        assert total_time < 2.0  # Should be much faster than sequential
        
        # Verify device statistics
        for device in devices:
            registered_device = modbus_client.get_device(device.device_id)
            assert registered_device.total_requests >= 3  # At least 3 requests per device
            assert registered_device.successful_requests >= 3

    @pytest.mark.asyncio
    async def test_connection_pool_efficiency(self, modbus_client):
        """Test connection pool reuse efficiency."""
        # Register device
        device = ModbusDevice(
            device_id=1,
            name="Pool Test Device",
            connection_info=ModbusConnectionInfo(
                connection_type=ModbusConnectionType.TCP,
                host="127.0.0.1",
                port=5020,
                device_address=1,
                timeout=1.0
            )
        )
        modbus_client.register_device(device)
        
        # Get initial pool stats
        initial_stats = modbus_client.get_connection_stats()
        initial_pool_stats = initial_stats.get("pool_stats", {})
        
        # Should start with empty pool
        assert len(initial_pool_stats) == 0