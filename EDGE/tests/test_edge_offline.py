#!/usr/bin/env python3
"""Integration tests for EDGE offline mode behaviour."""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import make_mocked_request

EDGE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(EDGE_ROOT))

from start import EDGEService  # noqa: E402
from core import device_registry as registry_module  # noqa: E402
from core.config_manager import get_config, reload_config  # noqa: E402
from core.device_registry import DeviceRegistry  # noqa: E402
from core.health_api import HealthAPI  # noqa: E402
from core.health_checker import health_checker  # noqa: E402


@pytest.mark.asyncio
async def test_edge_service_explicit_offline_mode(monkeypatch):
    """Service созданный в offline-mode не пытается аутентифицироваться."""
    config = get_config()
    service = EDGEService(config, offline_mode=True)

    # Должен пропустить попытку аутентификации и остаться в офлайне
    await service.setup_authentication()

    assert service.auth_client is None
    assert service.offline_mode is True
    assert service.offline_reason is not None


@pytest.mark.asyncio
async def test_edge_service_switches_offline_on_auth_failure(monkeypatch):
    """Если аутентификация падает, сервис должен перейти в offline-mode."""

    class DummyClient:
        def __init__(self, *args, **kwargs):
            self.last_error = "connection failed"

        def authenticate(self):
            raise ConnectionError("unreachable server")

    monkeypatch.setattr("start.EDGEAuthenticatedClient", DummyClient)
    config = get_config()
    service = EDGEService(config, offline_mode=False)

    await service.setup_authentication()

    assert service.offline_mode is True
    assert service.auth_client is None
    assert service.offline_reason == "connection failed"


def test_device_registry_returns_cached_data(monkeypatch):
    """DeviceRegistry должен возвращать данные даже если storage временно недоступен."""

    sample_payload = {
        "temp_inside": 276,
        "pressure": 101,
        "updated_at": "2024-01-01T12:00:00",
    }

    monkeypatch.setattr(registry_module, "MODBUS_STORAGE_AVAILABLE", True)
    monkeypatch.setattr(registry_module, "read_modbus_data", lambda: sample_payload.copy())

    registry = DeviceRegistry()
    device = next(iter(registry.get_devices(enabled_only=False)))

    fresh_data = registry.get_device_data(device.device_id, force_refresh=True)
    assert fresh_data is not None
    assert fresh_data["device_id"] == device.device_id

    # После сбоя чтения должны вернуться данные из кэша
    monkeypatch.setattr(registry_module, "read_modbus_data", lambda: None)
    cached_data = registry.get_device_data(device.device_id)

    assert cached_data == fresh_data


@pytest.mark.asyncio
async def test_health_api_requires_token(monkeypatch):
    """Проверяем, что health endpoints требуют токен при конфигурации."""

    os.environ["EDGE_HEALTH_TOKEN"] = "edge-secret"
    os.environ["EDGE_REQUIRE_HEALTH_TOKEN"] = "true"
    reload_config()

    api = HealthAPI()
    api.setup_routes()

    # Без токена должны получить 401
    request = make_mocked_request("GET", "/health")
    response = await api.health_endpoint(request)
    assert response.status == 401

    # Подготовим фиктивные данные для успешного ответа
    monkeypatch.setattr(
        health_checker,
        "get_overall_health",
        AsyncMock(return_value={"status": "healthy"}),
    )

    authorized_request = make_mocked_request(
        "GET",
        "/health",
        headers={"X-EDGE-Health-Token": "edge-secret"},
    )
    ok_response = await api.health_endpoint(authorized_request)
    assert ok_response.status == 200

    # Cleanup
    del os.environ["EDGE_HEALTH_TOKEN"]
    del os.environ["EDGE_REQUIRE_HEALTH_TOKEN"]
    reload_config()
