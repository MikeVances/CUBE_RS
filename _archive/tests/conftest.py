"""
Global pytest configuration and fixtures for CUBE_RS
Provides common fixtures, utilities and test setup
"""
import asyncio
import os
import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import aiosqlite
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

# Test data directory
TEST_DATA_DIR = Path(__file__).parent / "fixtures" / "data"
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)


# ===== ASYNC FIXTURES =====
@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def temp_db() -> AsyncGenerator[str, None]:
    """Create temporary SQLite database for tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Initialize test database schema
    async with aiosqlite.connect(db_path) as conn:
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

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS performance_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name VARCHAR(100) NOT NULL,
                metric_value REAL NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                tags TEXT
            )
        """
        )

        # Insert test data
        await conn.execute(
            """
            INSERT INTO modbus_data (device_id, function_code, register_address,
                                   register_count, data, timestamp, success)
            VALUES (1, 3, 0, 5, '[42, 100, 255, 0, 128]', '2024-01-01T12:00:00', 1)
        """
        )

        await conn.commit()

    yield db_path

    # Cleanup
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
async def mock_modbus_gateway():
    """Mock ModbusGateway for testing."""
    from unittest.mock import AsyncMock, MagicMock

    gateway = MagicMock()
    gateway.start_server = AsyncMock()
    gateway.stop_server = AsyncMock()
    gateway.read_modbus_registers = AsyncMock()
    gateway.handle_modbus_read = AsyncMock()
    gateway.save_to_database = AsyncMock()
    gateway.health_check = AsyncMock()
    gateway.running = True
    gateway.devices = {}

    return gateway


@pytest.fixture
async def aiohttp_client():
    """Create aiohttp test client."""
    clients = []

    async def _create_client(app: web.Application) -> TestClient:
        server = TestServer(app)
        client = TestClient(server, loop=asyncio.get_event_loop())
        await client.start_server()
        clients.append(client)
        return client

    yield _create_client

    # Cleanup
    for client in clients:
        await client.close()


# ===== SYNC FIXTURES =====
@pytest.fixture
def mock_config():
    """Mock configuration for tests."""
    from types import SimpleNamespace

    return SimpleNamespace(
        system=SimpleNamespace(log_level="INFO", debug=True),
        modbus_tcp=SimpleNamespace(port=5023, host="localhost", timeout=30),
        services=SimpleNamespace(
            gateway_enabled=True,
            dashboard_enabled=True,
            telegram_enabled=True,
            websocket_enabled=False,
            mqtt_enabled=False,
            dashboard_port=8501,
            websocket_port=8765,
        ),
        config_dir=Path("/tmp/cube_rs_test"),
    )


@pytest.fixture
def sample_modbus_requests():
    """Sample Modbus request data for tests."""
    return [
        {
            "device_id": 1,
            "function_code": 3,  # Read Holding Registers
            "register_address": 0,
            "register_count": 5,
        },
        {
            "device_id": 2,
            "function_code": 1,  # Read Coils
            "register_address": 100,
            "register_count": 10,
        },
        {
            "device_id": 1,
            "function_code": 4,  # Read Input Registers
            "register_address": 0,
            "register_count": 1,
        },
    ]


@pytest.fixture
def sample_modbus_responses():
    """Sample Modbus response data for tests."""
    return [
        {
            "success": True,
            "device_id": 1,
            "data": [42, 100, 255, 0, 128],
            "error": None,
        },
        {
            "success": False,
            "device_id": 2,
            "data": None,
            "error": "Device not responding",
        },
    ]


# ===== MARKERS =====
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "slow: Slow tests (skip with -m 'not slow')")
    config.addinivalue_line("markers", "async_test: Async tests")


# ===== PARAMETRIZE FIXTURES =====
@pytest.fixture(params=[1, 10, 50, 100])
def device_ids(request):
    """Parametrized device IDs for testing."""
    return request.param


@pytest.fixture(params=[1, 2, 3, 4, 5, 6, 15, 16])
def function_codes(request):
    """Parametrized Modbus function codes."""
    return request.param


# ===== UTILITIES =====
@pytest.fixture
def assert_logs():
    """Utility to assert log messages in tests."""
    import logging
    from unittest.mock import Mock

    def _assert_logs(logger_name: str, level: str, message_part: str):
        """Assert that log message was emitted."""
        logger = logging.getLogger(logger_name)
        handler = Mock()
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, level.upper()))

        return handler

    return _assert_logs


@pytest.fixture
def freeze_time():
    """Mock datetime.now() for consistent testing."""
    from datetime import datetime
    from unittest.mock import patch

    frozen_time = datetime(2024, 1, 1, 12, 0, 0)

    with patch("datetime.datetime") as mock_datetime:
        mock_datetime.now.return_value = frozen_time
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        yield frozen_time


# ===== PERFORMANCE FIXTURES =====
@pytest.fixture
async def benchmark():
    """Simple benchmarking fixture."""
    import time
    from collections.abc import Callable
    from typing import Any

    async def _benchmark(func: Callable, *args, **kwargs) -> dict[str, Any]:
        """Benchmark an async function."""
        start_time = time.perf_counter()
        result = await func(*args, **kwargs)
        end_time = time.perf_counter()

        return {
            "result": result,
            "duration": end_time - start_time,
            "duration_ms": (end_time - start_time) * 1000,
        }

    return _benchmark


# ===== DOCKER/TESTCONTAINERS FIXTURES =====
@pytest.fixture(scope="session")
async def postgres_container():
    """PostgreSQL test container (when needed for integration tests)."""
    pytest.skip("PostgreSQL container not implemented yet")
    # TODO: Implement when migrating to PostgreSQL
    # from testcontainers.postgres import PostgresContainer

    # with PostgresContainer("postgres:15") as postgres:
    #     yield postgres.get_connection_url()


# ===== CLEAN UP =====
@pytest.fixture(autouse=True)
def cleanup_temp_files():
    """Automatically cleanup temporary files after each test."""
    yield

    # Clean up any temporary files created during tests
    import glob

    temp_files = glob.glob("/tmp/cube_rs_test*")
    for temp_file in temp_files:
        try:
            if os.path.isfile(temp_file):
                os.unlink(temp_file)
            elif os.path.isdir(temp_file):
                import shutil

                shutil.rmtree(temp_file)
        except OSError:
            pass
