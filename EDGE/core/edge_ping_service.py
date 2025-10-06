#!/usr/bin/env python3
"""
EDGE Ping Service: periodically reports the node's addresses (Tailscale/local)
and identity to configured server endpoints.

Sources for endpoints (priority):
- ENV: EDGE_PING_SERVERS (comma-separated URLs)
- Encrypted config via SecurityManager: config/secrets/edge_ping.enc
  format: {"servers": ["https://server-1/api/edge/ping", ...], "auth_token": "..."}

Payload example:
{
  "device_uid": "0x1A2B3C4D",
  "software_version": "1.2",
  "tailscale_ip": "100.x.x.x",
  "local_ips": ["192.168.x.x", "10.x.x.x"],
  "hostname": "edge-001",
  "timestamp": "ISO"
}
"""

from __future__ import annotations

import asyncio
import os
import socket
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiosqlite

from .utils.paths import resolve_under_root


def _resolve_db_path() -> str:
    try:
        from .config_manager import get_config
        cfg = get_config()
        db_file = getattr(cfg.database, "file", None) or "kub_data.db"
        return resolve_under_root(db_file)
    except Exception:
        # Fallback to default path
        return resolve_under_root("kub_data.db")


async def _load_identity(device_registry) -> Dict[str, Any]:
    """Load device identity from Device Registry."""
    ident: Dict[str, Any] = {}
    try:
        # Используем первое доступное устройство для идентификации EDGE
        devices = device_registry.get_devices()
        if devices:
            first_device = devices[0]
            ident["device_uid"] = first_device.device_id
            ident["device_type"] = first_device.device_type
            ident["software_version"] = "EDGE-1.0"
        else:
            # Fallback если нет устройств
            ident["device_uid"] = f"EDGE-{socket.gethostname()}"
            ident["device_type"] = "EDGE"
            ident["software_version"] = "EDGE-1.0"
    except Exception:
        # Emergency fallback
        ident["device_uid"] = f"EDGE-{socket.gethostname()}"
        ident["device_type"] = "EDGE"  
        ident["software_version"] = "EDGE-1.0"
    return ident


def _get_local_ips() -> List[str]:
    ips: List[str] = []
    try:
        host = socket.gethostname()
        for addr in socket.getaddrinfo(host, None):
            ip = addr[4][0]
            if ":" in ip:  # skip IPv6 for brevity
                continue
            if ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips


def _get_tailscale_ip() -> Optional[str]:
    # Try environment override first
    env_ip = os.getenv("EDGE_TAILSCALE_IP")
    if env_ip:
        return env_ip
    # Try `tailscale ip -4` if available (non-blocking best-effort)
    try:
        import subprocess

        out = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=2
        )
        ip = out.stdout.strip().splitlines()[0] if out.returncode == 0 else ""
        return ip or None
    except Exception:
        return None


def _load_endpoints() -> Dict[str, Any]:
    # ENV first
    servers_csv = os.getenv("EDGE_PING_SERVERS", "").strip()
    if servers_csv:
        return {"servers": [s.strip() for s in servers_csv.split(",") if s.strip()]}
    # Encrypted config via SecurityManager
    try:
        from .security_manager import SecurityManager
        sm = SecurityManager()
        cfg = sm.load_encrypted_config("edge_ping")
        if isinstance(cfg, dict) and cfg.get("servers"):
            return cfg
    except Exception:
        pass
    return {"servers": []}


async def _post_json(url: str, payload: Dict[str, Any], auth_token: Optional[str] = None) -> int:
    import aiohttp

    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=8) as r:
                return r.status
    except Exception:
        return 0


async def run_edge_ping_service(device_registry, interval_sec: int = 300) -> None:
    """
    Run EDGE Ping Service with Device Registry integration
    """
    from .log_filter import get_secure_logger
    
    logger = get_secure_logger(__name__)
    
    endpoints = _load_endpoints()
    servers: List[str] = endpoints.get("servers", [])
    auth_token: Optional[str] = endpoints.get("auth_token")
    
    if not servers:
        logger.info("No EDGE ping servers configured, skipping ping service")
        return  # nothing to do

    logger.info(f"🚀 Starting EDGE Ping Service (interval: {interval_sec}s)")
    logger.info(f"   Servers: {len(servers)} configured")

    while True:
        try:
            ident = await _load_identity(device_registry)
            
            # Собираем данные о всех устройствах
            devices_info = []
            devices = device_registry.get_devices()
            for device_info in devices:
                device_data = device_registry.get_device_data(device_info.device_id)
                devices_info.append({
                    "device_id": device_info.device_id,
                    "device_type": device_info.device_type,
                    "has_data": bool(device_data)
                })
            
            payload: Dict[str, Any] = {
                **ident,
                "tailscale_ip": _get_tailscale_ip(),
                "local_ips": _get_local_ips(),
                "hostname": socket.gethostname(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "devices": devices_info,
                "devices_count": len(devices_info)
            }
            
            # Send to all servers
            tasks = [
                _post_json(url, payload, auth_token=auth_token) for url in servers
            ]
            statuses = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Log successful pings
            success_count = sum(1 for s in statuses if isinstance(s, int) and 200 <= s < 300)
            if success_count > 0:
                logger.debug(f"📡 Ping successful to {success_count}/{len(servers)} servers")
            else:
                logger.warning(f"⚠️ Ping failed to all {len(servers)} servers")
                
        except Exception as e:
            logger.error(f"❌ EDGE Ping error: {e}")
            
        await asyncio.sleep(interval_sec)
