"""
EDGE Test Configuration - pytest fixtures for CUBE_RS EDGE
Provides fixtures for testing device adapters, modbus gateway, and tunnel integration
"""
import asyncio
import os
import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

import pytest
from unittest.mock import AsyncMock, MagicMock

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
def temp_edge_db():
    """Create temporary SQLite database for EDGE tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    import sqlite3

    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kub_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id INTEGER NOT NULL,
                    register_address INTEGER NOT NULL,
                    register_value INTEGER,
                    timestamp DATETIME NOT NULL,
                    success BOOLEAN NOT NULL DEFAULT 1,
                    response_time_ms REAL,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS device_status (
                    device_id INTEGER PRIMARY KEY,
                    device_type TEXT NOT NULL,
                    connection_status TEXT DEFAULT 'disconnected',
                    last_seen DATETIME,
                    error_count INTEGER DEFAULT 0,
                    last_error TEXT
                )
                """
            )

            conn.execute(
                """
                INSERT INTO kub_data (device_id, register_address, register_value, timestamp, success)
                VALUES (1, 0, 42, '2024-01-01T12:00:00', 1)
                """
            )

            conn.execute(
                """
                INSERT INTO device_status (device_id, device_type, connection_status, last_seen)
                VALUES (1, 'kub1063', 'connected', '2024-01-01T12:00:00')
                """
            )

            conn.commit()

        yield db_path
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


@pytest.fixture
def mock_kub1063_device():
    """Mock KUB1063 device adapter for testing."""
    device = MagicMock()
    device.device_id = 1
    device.device_type = "kub1063"
    device.connect = AsyncMock(return_value=True)
    device.disconnect = AsyncMock()
    device.read_register = AsyncMock(return_value=42)
    device.write_register = AsyncMock(return_value=True)
    device.get_status = AsyncMock(return_value={"connected": True, "errors": 0})
    device.health_check = AsyncMock(return_value=True)
    return device


@pytest.fixture
async def mock_modbus_gateway():
    """Mock ModbusGateway for EDGE testing."""
    gateway = MagicMock()
    gateway.start_server = AsyncMock()
    gateway.stop_server = AsyncMock()
    gateway.read_registers = AsyncMock(return_value=[42, 100, 255])
    gateway.write_registers = AsyncMock(return_value=True)
    gateway.get_device_status = AsyncMock(return_value="connected")
    gateway.running = True
    gateway.devices = {1: mock_kub1063_device()}
    
    return gateway


@pytest.fixture
async def mock_tunnel_integration():
    """Mock tunnel integration for testing."""
    tunnel = MagicMock()
    tunnel.connect_to_server = AsyncMock(return_value=True)
    tunnel.disconnect_from_server = AsyncMock()
    tunnel.send_data = AsyncMock(return_value=True)
    tunnel.receive_data = AsyncMock(return_value={"status": "ok"})
    tunnel.is_connected = True
    
    return tunnel


# ===== SYNC FIXTURES =====
@pytest.fixture
def mock_edge_config():
    """Mock EDGE configuration for tests."""
    from types import SimpleNamespace

    return SimpleNamespace(
        system=SimpleNamespace(log_level="INFO", debug=True),
        modbus=SimpleNamespace(
            timeout=5,
            retry_count=3,
            poll_interval=1.0
        ),
        devices=SimpleNamespace(
            kub1063=SimpleNamespace(
                enabled=True,
                device_id=1,
                registers=[0, 1, 2, 3, 4]
            ),
            kub1112=SimpleNamespace(
                enabled=False,
                device_id=2
            )
        ),
        tunnel=SimpleNamespace(
            enabled=True,
            server_url="ws://localhost:8081",
            heartbeat_interval=30
        ),
        config_dir=Path("/tmp/edge_test"),
        data_dir=Path("/tmp/edge_test/data"),
        log_dir=Path("/tmp/edge_test/logs")
    )


@pytest.fixture
def sample_kub1063_data():
    """Sample KUB1063 data for tests."""
    return {
        "temp_inside": 22.5,
        "temp_target": 20.0,
        "humidity": 65.0,
        "co2": 800,
        "nh3": 15,
        "pressure": 1013.25,
        "ventilation_level": 45,
        "ventilation_target": 50,
        "active_alarms": [],
        "active_warnings": ["high_humidity"],
        "timestamp": "2024-01-01T12:00:00Z"
    }


@pytest.fixture  
def sample_device_registry():
    """Sample device registry data."""
    return {
        1: {
            "device_id": 1,
            "device_type": "kub1063", 
            "hostname": "greenhouse-001",
            "connection_status": "connected",
            "last_seen": "2024-01-01T12:00:00Z",
            "capabilities": ["temperature", "humidity", "co2", "ventilation"]
        },
        2: {
            "device_id": 2,
            "device_type": "kub1112",
            "hostname": "climate-control-001", 
            "connection_status": "disconnected",
            "last_seen": "2024-01-01T11:00:00Z",
            "capabilities": ["climate_control", "sensors"]
        }
    }


# ===== MARKERS =====
def pytest_configure(config):
    """Configure custom pytest markers for EDGE."""
    config.addinivalue_line("markers", "unit: Unit tests for EDGE components")
    config.addinivalue_line("markers", "integration: Integration tests for EDGE")
    config.addinivalue_line("markers", "device: Device adapter tests")
    config.addinivalue_line("markers", "modbus: Modbus communication tests")
    config.addinivalue_line("markers", "tunnel: Tunnel integration tests")
    config.addinivalue_line("markers", "slow: Slow tests (skip with -m 'not slow')")


# ===== PARAMETRIZE FIXTURES =====
@pytest.fixture(params=[1, 2, 3])
def device_ids(request):
    """Parametrized device IDs for testing."""
    return request.param


@pytest.fixture(params=["kub1063", "kub1112"])
def device_types(request):
    """Parametrized device types."""
    return request.param


@pytest.fixture(params=[1, 2, 3, 4, 5, 6])
def modbus_function_codes(request):
    """Parametrized Modbus function codes."""
    return request.param


# ===== UTILITIES =====
@pytest.fixture
def temp_config_dir():
    """Create temporary config directory."""
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp(prefix="edge_test_")
    config_dir = Path(temp_dir) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    # Create basic config file
    config_file = config_dir / "app_config.yaml"
    config_content = """
system:
  log_level: INFO
  debug: true

modbus:
  timeout: 5
  retry_count: 3
  poll_interval: 1.0

devices:
  kub1063:
    enabled: true
    device_id: 1
    registers: [0, 1, 2, 3, 4]
"""
    
    with open(config_file, "w") as f:
        f.write(config_content)
    
    yield config_dir
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


# ===== PERFORMANCE FIXTURES =====
@pytest.fixture
async def benchmark():
    """Simple benchmarking fixture for EDGE tests."""
    import time
    from collections.abc import Callable

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


# ===== CLEAN UP =====
@pytest.fixture(autouse=True)
def cleanup_edge_temp_files():
    """Automatically cleanup EDGE temporary files after each test."""
    yield

    # Clean up any temporary files created during tests
    import glob
    import shutil

    temp_patterns = [
        "/tmp/edge_test*",
        "/tmp/kub_*.db",
        "/tmp/device_*.log"
    ]
    
    for pattern in temp_patterns:
        temp_files = glob.glob(pattern)
        for temp_file in temp_files:
            try:
                if os.path.isfile(temp_file):
                    os.unlink(temp_file)
                elif os.path.isdir(temp_file):
                    shutil.rmtree(temp_file)
            except OSError:
                pass
