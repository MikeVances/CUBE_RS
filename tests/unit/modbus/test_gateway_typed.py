"""
Unit tests for TypedModbusGateway
Tests core functionality with proper async patterns and type safety
"""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from core.types import ModbusRequest, ModbusResponse, ModbusFunctionCode, APIResponse
from modbus.gateway_typed import TypedModbusGateway


class TestTypedModbusGateway(AioHTTPTestCase):
    """Integration tests for TypedModbusGateway HTTP endpoints."""

    async def get_application(self) -> web.Application:
        """Create test application."""
        self.gateway = TypedModbusGateway(
            host="127.0.0.1",
            port=0,  # Let test server choose port
            db_path=":memory:",
            max_concurrent_requests=10
        )
        await self.gateway._init_database()
        self.gateway._setup_routes()
        return self.gateway.app

    async def setUpAsync(self) -> None:
        """Setup test environment."""
        await super().setUpAsync()
        self.gateway.running = True
        self.gateway.start_time = datetime.now()

    @unittest_run_loop
    async def test_health_check_endpoint(self):
        """Test health check endpoint returns proper status."""
        resp = await self.client.request("GET", "/health")
        self.assertEqual(resp.status, 200)
        
        data = await resp.json()
        
        # Validate response structure
        self.assertTrue(data["success"])
        self.assertIn("data", data)
        
        health_data = data["data"]
        self.assertEqual(health_data["status"], "healthy")
        self.assertIn("timestamp", health_data)
        self.assertIn("version", health_data)
        self.assertIn("uptime_seconds", health_data)
        self.assertIn("database_healthy", health_data)
        self.assertTrue(health_data["database_healthy"])

    @unittest_run_loop
    async def test_metrics_endpoint(self):
        """Test metrics endpoint returns Prometheus-style metrics."""
        resp = await self.client.request("GET", "/metrics")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.content_type, "text/plain")
        
        metrics_text = await resp.text()
        self.assertIn("cube_rs_requests_total", metrics_text)
        self.assertIn("cube_rs_errors_total", metrics_text)
        self.assertIn("cube_rs_connected_devices", metrics_text)

    @unittest_run_loop  
    async def test_modbus_read_valid_request(self):
        """Test valid Modbus read request."""
        request_data = {
            "device_id": 1,
            "function_code": 3,  # READ_HOLDING_REGISTERS
            "register_address": 0,
            "register_count": 5
        }
        
        resp = await self.client.request("POST", "/modbus/read", json=request_data)
        self.assertEqual(resp.status, 200)
        
        data = await resp.json()
        self.assertTrue(data["success"])
        self.assertIn("data", data)
        
        modbus_response = data["data"]
        self.assertTrue(modbus_response["success"])
        self.assertEqual(modbus_response["request"]["device_id"], 1)
        self.assertEqual(modbus_response["request"]["function_code"], 3)
        self.assertIsInstance(modbus_response["data"], list)
        self.assertEqual(len(modbus_response["data"]), 5)
        self.assertIsInstance(modbus_response["response_time_ms"], float)

    @unittest_run_loop
    async def test_modbus_read_invalid_device_id(self):
        """Test Modbus read with invalid device ID."""
        request_data = {
            "device_id": 300,  # Invalid (>255)
            "function_code": 3,
            "register_address": 0,
            "register_count": 1
        }
        
        resp = await self.client.request("POST", "/modbus/read", json=request_data)
        self.assertEqual(resp.status, 400)
        
        data = await resp.json()
        self.assertFalse(data["success"])
        self.assertIn("error", data)
        self.assertIn("Validation error", data["error"])

    @unittest_run_loop
    async def test_modbus_read_invalid_function_code(self):
        """Test Modbus read with unsupported function code."""
        request_data = {
            "device_id": 1,
            "function_code": 99,  # Unsupported
            "register_address": 0,
            "register_count": 1
        }
        
        resp = await self.client.request("POST", "/modbus/read", json=request_data)
        self.assertEqual(resp.status, 400)

    @unittest_run_loop
    async def test_modbus_write_valid_request(self):
        """Test valid Modbus write request."""
        request_data = {
            "device_id": 1,
            "function_code": 6,  # WRITE_SINGLE_REGISTER
            "register_address": 100,
            "register_count": 1,
            "write_values": [1234]
        }
        
        resp = await self.client.request("POST", "/modbus/write", json=request_data)
        self.assertEqual(resp.status, 200)
        
        data = await resp.json()
        self.assertTrue(data["success"])

    @unittest_run_loop
    async def test_modbus_write_missing_values(self):
        """Test Modbus write without write values."""
        request_data = {
            "device_id": 1,
            "function_code": 6,
            "register_address": 100,
            "register_count": 1
            # Missing write_values
        }
        
        resp = await self.client.request("POST", "/modbus/write", json=request_data)
        self.assertEqual(resp.status, 400)

    @unittest_run_loop
    async def test_cors_headers(self):
        """Test CORS headers are properly set."""
        resp = await self.client.request("OPTIONS", "/health")
        self.assertEqual(resp.status, 200)
        self.assertIn("Access-Control-Allow-Origin", resp.headers)
        self.assertEqual(resp.headers["Access-Control-Allow-Origin"], "*")

    @unittest_run_loop
    async def test_error_handling_invalid_json(self):
        """Test error handling for invalid JSON."""
        resp = await self.client.request(
            "POST", 
            "/modbus/read",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(resp.status, 500)  # Should be handled by error middleware


@pytest.mark.unit
class TestTypedModbusGatewayUnit:
    """Unit tests for TypedModbusGateway business logic."""

    @pytest.fixture
    def gateway(self):
        """Create gateway instance for testing."""
        return TypedModbusGateway(
            host="127.0.0.1",
            port=5023,
            db_path=":memory:",
            max_concurrent_requests=5
        )

    def test_gateway_initialization(self, gateway):
        """Test gateway initializes with correct parameters."""
        assert gateway.host == "127.0.0.1"
        assert gateway.port == 5023
        assert gateway.db_path == Path(":memory:")
        assert gateway.max_concurrent_requests == 5
        assert not gateway.running
        assert gateway.request_counter == 0
        assert gateway.error_counter == 0
        assert len(gateway.connected_devices) == 0

    @pytest.mark.asyncio
    async def test_database_initialization(self, gateway):
        """Test database schema initialization."""
        await gateway._init_database()
        
        # Verify database was created and tables exist
        assert await gateway._check_database_health()

    @pytest.mark.asyncio  
    async def test_execute_modbus_read_success(self, gateway):
        """Test successful Modbus read execution."""
        request = ModbusRequest(
            device_id=1,
            function_code=ModbusFunctionCode.READ_HOLDING_REGISTERS,
            register_address=0,
            register_count=3
        )
        
        response = await gateway._execute_modbus_read(request)
        
        assert response.success
        assert response.request == request
        assert response.data is not None
        assert len(response.data) == 3
        assert response.error_message is None
        assert response.response_time_ms > 0
        assert isinstance(response.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_execute_modbus_read_coils(self, gateway):
        """Test reading coils returns boolean values."""
        request = ModbusRequest(
            device_id=2,
            function_code=ModbusFunctionCode.READ_COILS,
            register_address=10,
            register_count=5
        )
        
        response = await gateway._execute_modbus_read(request)
        
        assert response.success
        assert len(response.data) == 5
        # Verify all values are boolean for coils
        assert all(isinstance(val, bool) for val in response.data)

    @pytest.mark.asyncio
    async def test_execute_modbus_write_success(self, gateway):
        """Test successful Modbus write execution."""
        request = ModbusRequest(
            device_id=1,
            function_code=ModbusFunctionCode.WRITE_SINGLE_REGISTER,
            register_address=100,
            register_count=1,
            write_values=[1234]
        )
        
        response = await gateway._execute_modbus_write(request)
        
        assert response.success
        assert response.request == request
        assert response.error_message is None
        assert response.response_time_ms > 0

    @pytest.mark.asyncio
    async def test_save_to_database(self, gateway, temp_db):
        """Test saving Modbus response to database."""
        gateway.db_path = Path(temp_db)
        await gateway._init_database()
        
        # Create test response
        request = ModbusRequest(
            device_id=1,
            function_code=ModbusFunctionCode.READ_HOLDING_REGISTERS,
            register_address=0,
            register_count=2
        )
        
        response = ModbusResponse(
            request=request,
            success=True,
            data=[42, 100],
            response_time_ms=15.5
        )
        
        # Save to database
        await gateway._save_to_database(response)
        
        # Verify data was saved
        import aiosqlite
        async with aiosqlite.connect(temp_db) as conn:
            cursor = await conn.execute(
                "SELECT device_id, function_code, data, success, response_time_ms FROM modbus_data ORDER BY id DESC LIMIT 1"
            )
            row = await cursor.fetchone()
            
            assert row is not None
            assert row[0] == 1  # device_id
            assert row[1] == 3  # function_code
            assert "[42, 100]" in row[2]  # data should contain our test data
            assert row[3] == 1  # success (True)
            assert row[4] == 15.5  # response_time_ms

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, gateway):
        """Test concurrent request handling with semaphore."""
        request = ModbusRequest(
            device_id=1,
            function_code=ModbusFunctionCode.READ_HOLDING_REGISTERS,
            register_address=0,
            register_count=1
        )
        
        # Start multiple concurrent requests
        tasks = [
            gateway._execute_modbus_read(request)
            for _ in range(10)
        ]
        
        responses = await asyncio.gather(*tasks)
        
        # All should succeed
        assert len(responses) == 10
        assert all(response.success for response in responses)

    def test_memory_usage_tracking(self, gateway):
        """Test memory usage tracking."""
        memory_usage = gateway._get_memory_usage()
        assert isinstance(memory_usage, float)
        assert memory_usage >= 0

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, gateway):
        """Test graceful shutdown doesn't raise exceptions."""
        # Should not raise even if server wasn't started
        await gateway.stop_server()
        
        # Should handle repeated calls gracefully
        await gateway.stop_server()
        await gateway.stop_server()


# ===== PROPERTY-BASED TESTS =====
@pytest.mark.unit 
class TestModbusRequestValidation:
    """Property-based tests for Modbus request validation."""

    def test_valid_modbus_request_creation(self):
        """Test creating valid ModbusRequest instances."""
        request = ModbusRequest(
            device_id=1,
            function_code=ModbusFunctionCode.READ_HOLDING_REGISTERS,
            register_address=100,
            register_count=10
        )
        
        assert request.device_id == 1
        assert request.function_code == ModbusFunctionCode.READ_HOLDING_REGISTERS
        assert request.register_address == 100
        assert request.register_count == 10
        assert request.write_values is None

    def test_modbus_request_with_write_values(self):
        """Test ModbusRequest with write values."""
        request = ModbusRequest(
            device_id=5,
            function_code=ModbusFunctionCode.WRITE_MULTIPLE_REGISTERS,
            register_address=0,
            register_count=3,
            write_values=[100, 200, 300]
        )
        
        assert request.write_values == [100, 200, 300]

    def test_invalid_device_id_raises_validation_error(self):
        """Test invalid device ID raises validation error."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="Input should be less than or equal to 255"):
            ModbusRequest(
                device_id=300,  # > 255
                function_code=ModbusFunctionCode.READ_HOLDING_REGISTERS,
                register_address=0,
                register_count=1
            )

    def test_invalid_register_address_raises_validation_error(self):
        """Test invalid register address raises validation error."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ModbusRequest(
                device_id=1,
                function_code=ModbusFunctionCode.READ_HOLDING_REGISTERS,
                register_address=-1,  # Negative
                register_count=1
            )

    def test_invalid_register_count_raises_validation_error(self):
        """Test invalid register count raises validation error."""  
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ModbusRequest(
                device_id=1,
                function_code=ModbusFunctionCode.READ_HOLDING_REGISTERS,
                register_address=0,
                register_count=0  # Must be >= 1
            )

    @pytest.mark.parametrize("function_code", [
        ModbusFunctionCode.READ_COILS,
        ModbusFunctionCode.READ_DISCRETE_INPUTS,
        ModbusFunctionCode.READ_HOLDING_REGISTERS,
        ModbusFunctionCode.READ_INPUT_REGISTERS,
        ModbusFunctionCode.WRITE_SINGLE_COIL,
        ModbusFunctionCode.WRITE_SINGLE_REGISTER,
    ])
    def test_supported_function_codes(self, function_code):
        """Test all supported function codes work."""
        request = ModbusRequest(
            device_id=1,
            function_code=function_code,
            register_address=0,
            register_count=1
        )
        assert request.function_code == function_code


# ===== PERFORMANCE TESTS =====
@pytest.mark.unit
@pytest.mark.slow
class TestTypedModbusGatewayPerformance:
    """Performance tests for TypedModbusGateway."""

    @pytest.mark.asyncio
    async def test_response_time_tracking(self):
        """Test response time tracking accuracy."""
        gateway = TypedModbusGateway(db_path=":memory:")
        
        request = ModbusRequest(
            device_id=1,
            function_code=ModbusFunctionCode.READ_HOLDING_REGISTERS,
            register_address=0,
            register_count=1
        )
        
        response = await gateway._execute_modbus_read(request)
        
        # Response time should be reasonable (< 100ms for simulated operation)
        assert 0 < response.response_time_ms < 100
        assert isinstance(response.response_time_ms, float)

    @pytest.mark.asyncio
    async def test_concurrent_performance(self, benchmark):
        """Benchmark concurrent request handling."""
        gateway = TypedModbusGateway(db_path=":memory:", max_concurrent_requests=50)
        
        request = ModbusRequest(
            device_id=1,
            function_code=ModbusFunctionCode.READ_HOLDING_REGISTERS,
            register_address=0,
            register_count=10
        )
        
        async def execute_requests():
            """Execute multiple concurrent requests."""
            tasks = [
                gateway._execute_modbus_read(request)
                for _ in range(20)
            ]
            return await asyncio.gather(*tasks)
        
        result = await benchmark(execute_requests)
        responses = result["result"]
        
        # All requests should succeed
        assert len(responses) == 20
        assert all(response.success for response in responses)
        
        # Total time should be reasonable for concurrent execution
        assert result["duration_ms"] < 1000  # Should complete in <1 second