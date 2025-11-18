#!/usr/bin/env python3
"""
EDGE launcher: start all on-farm services as one node.

Starts (config-driven):
- RS485 unified system (apps.edge.modbus.unified_system)
- Modbus TCP gateway (apps/edge/gateway/start_typed_gateway.py)
- Telegram bot (apps/edge/gateway/telegram_service/start.py) — optional
- Streamlit dashboard (apps/edge/gateway/web_dashboard/app.py) — optional

This wraps the existing project layout into a single, clear entrypoint
under `apps/edge`, without moving implementation files.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path

try:
    # Use core logging if available
    from core.log_filter import get_secure_logger
except Exception:  # pragma: no cover
    import logging as _logging

    def get_secure_logger(name: str):
        _logging.basicConfig(level=_logging.INFO)
        return _logging.getLogger(name)

ROOT = Path(__file__).resolve().parents[2]  # EDGE root

# Add EDGE root to Python path for core imports
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config_manager import get_config
logger = get_secure_logger(__name__)


def _cmd_modbus_system() -> list[str]:
    # Use the EDGE module path so a separate EDGE repo works without shims
    return [sys.executable, "-m", "apps.edge.modbus.unified_system"]


def _cmd_modbus_gateway() -> list[str]:
    # Use EDGE path
    return [sys.executable, str(ROOT / "apps/edge/gateway/start_typed_gateway.py")]


def _cmd_telegram_bot() -> list[str]:
    # Use EDGE path
    return [sys.executable, str(ROOT / "apps/edge/gateway/telegram_service/start.py")]


def _cmd_dashboard() -> list[str]:
    # Use the moved web_dashboard under EDGE
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(ROOT / "apps/edge/gateway/web_dashboard/app.py"),
        "--server.port",
        os.getenv("DASHBOARD_PORT", "8501"),
        "--server.address",
        "0.0.0.0",
        "--server.headless",
        "true",
    ]


async def main() -> int:
    cfg = get_config()

    procs: dict[str, subprocess.Popen] = {}
    restart_stats: dict[str, dict] = {}

    def start(name: str, cmd: list[str]) -> None:
        logger.info(f"🚀 EDGE: start {name} → {' '.join(cmd)}")
        # Ensure EDGE root is in PYTHONPATH for subprocesses
        env = os.environ.copy()
        current_path = env.get("PYTHONPATH", "")
        edge_root = str(ROOT)
        if edge_root not in current_path:
            env["PYTHONPATH"] = f"{edge_root}:{current_path}" if current_path else edge_root
        p = subprocess.Popen(cmd, cwd=str(ROOT), env=env)
        procs[name] = p
        restart_stats.setdefault(name, {"failures": 0, "last_start": asyncio.get_event_loop().time()})

    # Core edge services
    start("modbus-system", _cmd_modbus_system())
    start("modbus-gateway", _cmd_modbus_gateway())

    # Optional services per config
    if cfg.services.telegram_enabled:
        start("telegram-bot", _cmd_telegram_bot())

    if cfg.services.dashboard_enabled:
        try:
            # Prefer checking via module to avoid PATH issues
            subprocess.run([sys.executable, "-m", "streamlit", "--version"], capture_output=True, check=True)
            start("web-dashboard", _cmd_dashboard())
        except Exception:
            logger.warning("⚠️ Streamlit не найден — дашборд пропущен")

    # Graceful handling
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _stop(*_):
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:  # Windows fallback
            signal.signal(sig, lambda *_: _stop())

    logger.info("💡 EDGE node is running. Press Ctrl+C to stop.")

    try:
        while not stop_event.is_set():
            dead = [k for k, p in procs.items() if p.poll() is not None]
            for name in dead:
                rc = procs[name].returncode
                logger.warning(f"⚠️ Process {name} exited (code {rc})")
                del procs[name]

                # Watchdog restart policy
                if os.getenv("EDGE_WATCHDOG_ENABLED", "true").lower() in ("1", "true", "yes", "on"):
                    stats = restart_stats.setdefault(name, {"failures": 0, "last_start": 0.0})
                    stats["failures"] = stats.get("failures", 0) + 1
                    delay = min(60, 2 ** max(0, stats["failures"] - 1))
                    try:
                        custom_max = int(os.getenv("EDGE_WATCHDOG_BACKOFF_MAX", "60"))
                        delay = min(delay, custom_max)
                    except Exception:
                        pass
                    logger.info(f"🛡️ Watchdog: restarting {name} in {delay}s (failure #{stats['failures']})")
                    await asyncio.sleep(delay)

                    # Build command by name and restart
                    try:
                        if name == "modbus-system":
                            cmd = _cmd_modbus_system()
                        elif name == "modbus-gateway":
                            cmd = _cmd_modbus_gateway()
                        elif name == "telegram-bot":
                            cmd = _cmd_telegram_bot()
                        elif name == "web-dashboard":
                            cmd = _cmd_dashboard()
                        else:
                            cmd = None
                        if cmd:
                            start(name, cmd)
                        else:
                            logger.error(f"❌ Watchdog: unknown service {name}, cannot restart")
                    except Exception as e:
                        logger.error(f"❌ Watchdog: failed to restart {name}: {e}")
            if not procs:
                logger.error("❌ All EDGE processes have exited")
                break
            # decay failure counters after stability window
            now = asyncio.get_event_loop().time()
            stable_sec = int(os.getenv("EDGE_WATCHDOG_STABLE_SEC", "300"))
            for name, p in procs.items():
                st = restart_stats.setdefault(name, {"failures": 0, "last_start": now})
                if st.get("failures", 0) > 0 and now - st.get("last_start", now) > stable_sec:
                    logger.info(f"🟢 Watchdog: {name} stable for {stable_sec}s, resetting failures")
                    st["failures"] = 0
                    st["last_start"] = now
            await asyncio.sleep(3)
    finally:
        logger.info("🛑 Stopping EDGE services…")
        for k, p in procs.items():
            try:
                p.terminate()
                p.wait(timeout=10)
                logger.info(f"✅ {k} stopped")
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass

    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
        sys.exit(0)
