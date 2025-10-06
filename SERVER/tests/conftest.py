"""
SERVER Test Configuration - pytest fixtures for CUBE_RS SERVER
Provides fixtures for testing web application, tunnel broker, and security components
"""
import asyncio
import os
import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

import aiosqlite
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
async def temp_server_db() -> AsyncGenerator[str, None]:
    """Create temporary SQLite database for SERVER tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Initialize SERVER test database schema
    async with aiosqlite.connect(db_path) as conn:
        # Users table (RBAC)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role_id TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        """
        )

        # Roles table (RBAC)  
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS roles (
                role_id TEXT PRIMARY KEY,
                role_name TEXT UNIQUE NOT NULL,
                description TEXT,
                permissions TEXT
            )
        """
        )

        # Registered devices table
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS registered_devices (
                device_id TEXT PRIMARY KEY,
                hostname TEXT NOT NULL,
                tailscale_ip TEXT NOT NULL,
                device_type TEXT DEFAULT 'unknown',
                status TEXT DEFAULT 'pending',
                registration_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP
            )
        """
        )

        # Tunnel connections table
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS active_connections (
                request_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                farm_id TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at REAL NOT NULL,
                last_activity REAL NOT NULL
            )
        """
        )

        # Insert test data
        await conn.execute(
            """
            INSERT INTO roles (role_id, role_name, description, permissions)
            VALUES ('admin', 'Administrator', 'Full access', '["device:view", "device:configure", "user:manage"]')
        """
        )
        
        await conn.execute(
            """
            INSERT INTO users (user_id, username, password_hash, role_id)
            VALUES ('test-user', 'testuser', 'hashed_password', 'admin')
        """
        )
        
        await conn.execute(
            """
            INSERT INTO registered_devices (device_id, hostname, tailscale_ip, device_type, status)
            VALUES ('test-device', 'test-farm-001', '100.100.100.1', 'farm', 'active')
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
async def mock_flask_app():
    """Mock Flask application for testing."""
    from flask import Flask
    
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    
    @app.route('/test')
    def test_route():
        return {'status': 'ok'}
    
    return app


@pytest.fixture
async def mock_rbac_system():
    """Mock RBAC system for testing."""
    rbac = MagicMock()
    rbac.authenticate_user = AsyncMock(return_value={"user_id": "test-user", "role": "admin"})
    rbac.check_permission = AsyncMock(return_value=True)
    rbac.create_user = AsyncMock(return_value=True)
    rbac.get_user_permissions = AsyncMock(return_value=["device:view", "device:configure"])
    rbac.audit_log = AsyncMock()
    
    return rbac


@pytest.fixture
async def mock_device_registry():
    """Mock device registry for testing."""
    registry = MagicMock()
    registry.register_device = AsyncMock(return_value={"status": "success", "device_id": "test-device"})
    registry.get_device = AsyncMock(return_value={"device_id": "test-device", "status": "active"})
    registry.list_devices = AsyncMock(return_value=[{"device_id": "test-device", "status": "active"}])
    registry.update_device_status = AsyncMock(return_value=True)
    registry.revoke_device = AsyncMock(return_value=True)
    
    return registry


@pytest.fixture
async def mock_tunnel_broker():
    """Mock tunnel broker for testing."""
    broker = MagicMock()
    broker.create_connection = AsyncMock(return_value={"request_id": "test-request", "status": "pending"})
    broker.get_connection_status = AsyncMock(return_value="connected")
    broker.close_connection = AsyncMock(return_value=True)
    broker.list_active_connections = AsyncMock(return_value=[])
    broker.cleanup_expired_connections = AsyncMock(return_value=2)
    broker.running = True
    
    return broker


@pytest.fixture
async def mock_tailscale_integration():
    """Mock Tailscale integration for testing."""
    tailscale = MagicMock()
    tailscale.get_network_overview = AsyncMock(return_value={
        "status": "success",
        "devices": {"total": 5, "online": 3},
        "farms": {"total": 2, "online": 1}
    })
    tailscale.get_devices_list = AsyncMock(return_value=[
        {"id": "device1", "hostname": "farm-001", "online": True}
    ])
    tailscale.send_farm_command = AsyncMock(return_value={"status": "success"})
    
    return tailscale


# ===== SYNC FIXTURES =====
@pytest.fixture
def mock_server_config():
    """Mock SERVER configuration for tests."""
    from types import SimpleNamespace

    return SimpleNamespace(
        server=SimpleNamespace(
            host="0.0.0.0",
            port=8080,
            debug=False
        ),
        tunnel_broker=SimpleNamespace(
            port=8081,
            max_connections=100,
            connection_timeout=300
        ),
        security=SimpleNamespace(
            secret_key="test-secret-key",
            session_timeout=3600,
            max_login_attempts=3
        ),
        database=SimpleNamespace(
            url="sqlite:///test.db",
            pool_size=10
        ),
        tailscale=SimpleNamespace(
            enabled=True,
            tailnet="test-tailnet.ts.net",
            api_key="test-api-key"
        ),
        config_dir=Path("/tmp/server_test"),
        data_dir=Path("/tmp/server_test/data"),
        log_dir=Path("/tmp/server_test/logs")
    )


@pytest.fixture
def sample_user_data():
    """Sample user data for testing."""
    return {
        "user_id": "test-user-123",
        "username": "testuser",
        "role": "farm_operator",
        "permissions": ["device:view", "device:connect", "device:configure"],
        "is_active": True,
        "created_at": "2024-01-01T12:00:00Z",
        "last_login": "2024-01-01T12:00:00Z"
    }


@pytest.fixture
def sample_device_data():
    """Sample device data for testing."""
    return {
        "device_id": "farm-001-device",
        "hostname": "greenhouse-001",
        "tailscale_ip": "100.100.100.1",
        "device_type": "farm",
        "status": "active",
        "registration_time": "2024-01-01T12:00:00Z",
        "last_seen": "2024-01-01T12:00:00Z",
        "capabilities": ["kub1063", "monitoring"]
    }


@pytest.fixture
def sample_tunnel_connection():
    """Sample tunnel connection data."""
    return {
        "request_id": "conn-123-456",
        "user_id": "test-user",
        "farm_id": "farm-001",
        "status": "connected",
        "created_at": 1704110400.0,  # 2024-01-01T12:00:00Z
        "last_activity": 1704110400.0,
        "app_offer": {"type": "offer", "sdp": "test-sdp"},
        "farm_answer": {"type": "answer", "sdp": "test-answer-sdp"}
    }


# ===== MARKERS =====
def pytest_configure(config):
    """Configure custom pytest markers for SERVER."""
    config.addinivalue_line("markers", "unit: Unit tests for SERVER components")
    config.addinivalue_line("markers", "integration: Integration tests for SERVER")
    config.addinivalue_line("markers", "webapp: Web application tests")
    config.addinivalue_line("markers", "rbac: RBAC system tests") 
    config.addinivalue_line("markers", "tunnel: Tunnel broker tests")
    config.addinivalue_line("markers", "api: API endpoint tests")
    config.addinivalue_line("markers", "security: Security tests")
    config.addinivalue_line("markers", "slow: Slow tests (skip with -m 'not slow')")


# ===== PARAMETRIZE FIXTURES =====
@pytest.fixture(params=["admin", "farm_operator", "viewer", "mobile_user"])
def user_roles(request):
    """Parametrized user roles for testing."""
    return request.param


@pytest.fixture(params=["farm", "mobile", "gateway", "edge"])  
def device_types(request):
    """Parametrized device types."""
    return request.param


@pytest.fixture(params=["pending", "active", "inactive", "revoked"])
def device_statuses(request):
    """Parametrized device statuses."""
    return request.param


# ===== UTILITIES =====
@pytest.fixture
def mock_request():
    """Mock Flask request object."""
    from unittest.mock import Mock
    
    request = Mock()
    request.remote_addr = "127.0.0.1"
    request.user_agent.string = "pytest"
    request.headers = {"Content-Type": "application/json"}
    request.get_json.return_value = {}
    
    return request


@pytest.fixture
def temp_server_config_dir():
    """Create temporary SERVER config directory."""
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp(prefix="server_test_")
    config_dir = Path(temp_dir) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    # Create basic config file
    config_file = config_dir / "server.env"
    config_content = """
FLASK_ENV=testing
FLASK_DEBUG=1
SECRET_KEY=test-secret-key
DATABASE_URL=sqlite:///test.db
"""
    
    with open(config_file, "w") as f:
        f.write(config_content)
    
    yield config_dir
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


# ===== WEB CLIENT FIXTURES =====
@pytest.fixture
async def web_client(mock_flask_app):
    """Create Flask test client."""
    with mock_flask_app.test_client() as client:
        with mock_flask_app.app_context():
            yield client


@pytest.fixture
def api_headers():
    """Standard API headers for testing."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "CUBE_RS-Test-Client/1.0"
    }


# ===== PERFORMANCE FIXTURES =====
@pytest.fixture
async def benchmark():
    """Simple benchmarking fixture for SERVER tests."""
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
def cleanup_server_temp_files():
    """Automatically cleanup SERVER temporary files after each test."""
    yield

    # Clean up any temporary files created during tests
    import glob
    import shutil

    temp_patterns = [
        "/tmp/server_test*",
        "/tmp/rbac_*.db", 
        "/tmp/device_registry_*.db",
        "/tmp/tunnel_broker_*.db"
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