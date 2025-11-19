#!/usr/bin/env python3
"""Unified launcher for EDGE node (gateway + runtime services)."""

import argparse
import asyncio
import os
import signal
import sys
from pathlib import Path
from typing import Any, List, Tuple

import yaml

EDGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EDGE_DIR.parent
sys.path.insert(0, str(EDGE_DIR))

# Ensure relative paths resolve from project root
os.chdir(PROJECT_ROOT)

# Provide safe defaults so config validation doesn't fail when Telegram is disabled
if os.getenv("EDGE_USE_DUMMY_TELEGRAM_TOKEN"):
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy-edge-startup")

# After chdir we can reference config relative to root
from core.config_manager import get_config, reload_config
from core.utils.paths import get_project_root
import inspect

PROJECT_ROOT = get_project_root(EDGE_DIR)
CONFIG_DIR = PROJECT_ROOT / "config"

try:
    # Optional dependency for autoscan
    from pymodbus.client import ModbusSerialClient  # type: ignore
    try:
        from pymodbus.framer import FramerType  # type: ignore
    except Exception:  # pragma: no cover - optional
        FramerType = None  # type: ignore
except Exception:  # pragma: no cover - optional
    ModbusSerialClient = None  # type: ignore
    FramerType = None  # type: ignore


def build_start_command(args: argparse.Namespace) -> List[str]:
    """Compose command line for start.py based on arguments."""
    cmd = [sys.executable, "start.py"]

    if args.offline:
        cmd.append("--offline")
    if args.log_level:
        cmd.extend(["--log-level", args.log_level])
    if args.disable_telegram:
        cmd.append("--disable-telegram")
    if args.disable_websocket:
        cmd.append("--disable-websocket")
    if args.disable_mqtt:
        cmd.append("--disable-mqtt")
    if args.disable_health_api:
        cmd.append("--disable-health-api")
    if args.disable_edge_ping:
        cmd.append("--disable-edge-ping")

    return cmd


async def stream_output(prefix: str, stream: asyncio.StreamReader):
    """Prefix process output for readability."""
    while True:
        line = await stream.readline()
        if not line:
            break
        print(f"[{prefix}] {line.decode().rstrip()}", flush=True)


async def start_process(name: str, cmd: List[str]) -> asyncio.subprocess.Process:
    """Start subprocess with prefixed output."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(EDGE_DIR),
    )
    assert proc.stdout is not None
    asyncio.create_task(stream_output(name, proc.stdout))
    return proc


def read_config_defaults() -> Tuple[str, int]:
    cfg_path = CONFIG_DIR / "app_config.yaml"
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f) or {}
            except yaml.YAMLError:
                data = {}
    else:
        data = {}

    rs485 = data.get("rs485", {})
    modbus_tcp = data.get("modbus_tcp", {})
    return rs485.get("port", "/dev/ttyUSB0"), int(modbus_tcp.get("port", 5023))


def _resolve_port_overrides(args: argparse.Namespace) -> tuple[str, int]:
    """Resolve RS485 and Modbus TCP ports with precedence:
    1) CLI args
    2) Environment variables
    3) Config defaults
    """
    cfg_rs485, cfg_modbus_port = read_config_defaults()

    env_rtu = os.getenv("MODBUS_RTU_PORT")
    env_tcp = os.getenv("MODBUS_TCP_PORT")

    rs485_port = args.rs485_port or env_rtu or cfg_rs485
    modbus_port = (
        args.modbus_port if args.modbus_port is not None else int(env_tcp) if env_tcp else cfg_modbus_port
    )
    return rs485_port, modbus_port


def read_polling_interval_defaults() -> dict[str, float]:
    cfg_path = CONFIG_DIR / "app_config.yaml"
    if not cfg_path.exists():
        return {}
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return {}
    polling = data.get("polling", {}) or {}
    defaults = polling.get("default_intervals", {}) or {}
    result: dict[str, float] = {}
    for key, value in defaults.items():
        try:
            result[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return result


def _make_reader(client):
    fn_h = getattr(client, "read_holding_registers")
    fn_i = getattr(client, "read_input_registers")
    sig_h = inspect.signature(fn_h)
    sig_i = inspect.signature(fn_i)
    kw_h = "slave" if "slave" in sig_h.parameters else ("unit" if "unit" in sig_h.parameters else None)
    kw_i = "slave" if "slave" in sig_i.parameters else ("unit" if "unit" in sig_i.parameters else None)

    def read(kind: str, address: int, count: int, slave_id: int):
        if kind == "holding":
            kwargs = {kw_h: slave_id} if kw_h else {}
            return fn_h(address, count, **kwargs)
        else:
            kwargs = {kw_i: slave_id} if kw_i else {}
            return fn_i(address, count, **kwargs)

    return read


AUTOSCAN_DEVICE_PROBES = [
    (
        "VFD-INVERTER",
        [
            {"kind": "holding", "address": 0x1000, "require_non_zero": True},
            {"kind": "input", "address": 0x1000, "require_non_zero": True},
        ],
    ),
    (
        "KUB-1112",
        [
            {"kind": "holding", "address": 0x0405, "require_non_zero": True},
            {"kind": "holding", "address": 0x0400, "require_non_zero": False},
        ],
    ),
    (
        "KUB-1063",
        [
            {"kind": "holding", "address": 0x160E, "expected_value": 1},
            {"kind": "holding", "address": 0x0301, "require_non_zero": True},
        ],
    ),
]


def _detect_device_type(read, slave_id: int) -> tuple[str | None, dict[str, Any] | None]:
    for device_type, probes in AUTOSCAN_DEVICE_PROBES:
        requires_positive = any(
            probe.get("require_non_zero") or probe.get("expected_value") is not None for probe in probes
        )
        positive_info: dict[str, Any] | None = None
        fallback_info: dict[str, Any] | None = None
        for probe in probes:
            try:
                r = read(
                    probe.get("kind", "holding"),
                    probe["address"],
                    probe.get("count", 1),
                    slave_id,
                )
                if not hasattr(r, "isError") or r.isError() or not getattr(r, "registers", None):
                    continue
                registers = getattr(r, "registers", [])
                expected_value = probe.get("expected_value")
                positive_probe = probe.get("require_non_zero") or expected_value is not None
                if expected_value is not None:
                    if not registers or registers[0] != expected_value:
                        continue
                if probe.get("require_non_zero"):
                    if not any(val not in (0, None) for val in registers):
                        continue
                info = {
                    "address": f"0x{probe['address']:04X}",
                    "fn": probe.get("kind", "holding"),
                    "value": registers[0] if registers else None,
                }
                if positive_probe:
                    positive_info = info
                    break
                fallback_info = info
            except Exception:
                continue
        if positive_info:
            return device_type, positive_info
        if not requires_positive and fallback_info:
            return device_type, fallback_info
    return None, None


def _autoscan_and_write_config(rs485_port: str, start_id: int, end_id: int) -> None:
    """Scan RTU bus for KUB/VFD devices and write config/devices.yaml."""
    # Build client (3.x or 2.x)
    if ModbusSerialClient is None:
        print("⚠️ pymodbus не установлен — пропускаем автоскан")
        return
    if FramerType is not None:
        client = ModbusSerialClient(port=rs485_port, framer=FramerType.RTU, baudrate=9600, bytesize=8, parity="N", stopbits=1, timeout=0.5)  # type: ignore[arg-type]
    else:
        client = ModbusSerialClient(port=rs485_port, baudrate=9600, bytesize=8, parity="N", stopbits=1, timeout=0.5)

    if not client.connect():
        print(f"❌ Автоскан: не удалось подключиться к {rs485_port}")
        return
    interval_defaults = read_polling_interval_defaults()
    try:
        read = _make_reader(client)
        discovered: list[dict] = []
        device_id = 1
        for sid in range(start_id, end_id + 1):
            dev_type, _ = _detect_device_type(read, sid)
            if dev_type:
                entry = {
                    "device_id": device_id,
                    "device_type": dev_type,
                    "slave_id": sid,
                    "name": f"{dev_type} #{sid}",
                    "description": "Автоскан EDGE",
                    "enabled": True,
                    "location": None,
                }
                default_interval = interval_defaults.get(dev_type)
                if default_interval and default_interval > 0:
                    entry["poll_interval"] = float(default_interval)
                discovered.append(entry)
                device_id += 1

        if not discovered:
            print("⚠️ Автоскан: устройства не найдены в указанном диапазоне")
            return

        cfg_path = CONFIG_DIR / "devices.yaml"
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cfg_path, "w", encoding="utf-8") as fh:
            yaml.safe_dump({"devices": discovered}, fh, allow_unicode=True, sort_keys=False)
        print(f"💾 devices.yaml обновлён: {cfg_path} (устройств: {len(discovered)})")
    finally:
        try:
            client.close()
        except Exception:
            pass


async def run(args: argparse.Namespace) -> int:
    # Resolve ports with precedence (args > env > config)
    rs485_port, modbus_port = _resolve_port_overrides(args)

    # Optional autoscan to generate devices.yaml
    if args.autoscan:
        print(f"🔎 Автоскан шины {rs485_port} (ID {args.scan_start}-{args.scan_end}) и обновление config/devices.yaml…")
        _autoscan_and_write_config(rs485_port, args.scan_start, args.scan_end)

    # Propagate overrides to environment so gateway/start.py see consistent values
    os.environ["MODBUS_RTU_PORT"] = rs485_port
    os.environ["MODBUS_TCP_PORT"] = str(modbus_port)
    os.environ.setdefault("USE_UNIVERSAL_READER", "true")

    if args.offline:
        os.environ["EDGE_OFFLINE_MODE"] = "true"

    # Reload config after applying overrides
    config = reload_config()
    if config is None:
        config = get_config()
    config.rs485.port = rs485_port
    config.modbus_tcp.port = modbus_port

    processes = []
    print("⏭️ Legacy Modbus gateway отключён (universal reader mode)")

    start_cmd = build_start_command(args)
    print(f"🚀 Starting EDGE runtime: {' '.join(start_cmd)}")
    runtime = await start_process("RUNTIME", start_cmd)
    processes.append(runtime)

    stop = asyncio.Future()

    def handle_exit(signame: str):
        if not stop.done():
            print(f"🛑 Received {signame}, stopping services...")
            stop.set_result(None)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_exit, sig.name)

    async def wait_process(proc: asyncio.subprocess.Process) -> int:
        return await proc.wait()

    tasks = [asyncio.create_task(wait_process(p)) for p in processes]

    done, pending = await asyncio.wait(tasks + [stop], return_when=asyncio.FIRST_COMPLETED)

    # If one of the processes exits unexpectedly, notify and stop.
    for task in done:
        if task in tasks:
            rc = task.result()
            print(f"⚠️ Process exited with code {rc}")
            stop.set_result(None)

    # Terminate all child processes
    for proc in processes:
        if proc.returncode is None:
            try:
                proc.send_signal(signal.SIGINT)
            except ProcessLookupError:
                pass

    # Wait for graceful shutdown
    await asyncio.wait(tasks, timeout=args.shutdown_timeout)

    # Force kill lingering processes
    for proc in processes:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()

    loop.remove_signal_handler(signal.SIGINT)
    loop.remove_signal_handler(signal.SIGTERM)

    # Return last non-zero code, or 0
    rc = 0
    for proc in processes:
        if proc.returncode not in (None, 0):
            rc = proc.returncode
    return rc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified EDGE launcher")
    parser.add_argument("--offline", action="store_true", help="Run runtime in offline mode")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Log level for runtime")
    parser.add_argument("--disable-telegram", action="store_true", help="Do not start Telegram bot")
    parser.add_argument("--disable-websocket", action="store_true", help="Disable WebSocket server")
    parser.add_argument("--disable-mqtt", action="store_true", help="Disable MQTT publisher")
    parser.add_argument("--disable-edge-ping", action="store_true", help="Disable EDGE ping service")
    parser.add_argument("--disable-health-api", action="store_true", help="Disable health API")
    parser.add_argument("--rs485-port", help="Override RS485 serial port (defaults to config)")
    parser.add_argument("--modbus-port", type=int, help="Override Modbus TCP port")
    parser.add_argument("--shutdown-timeout", type=float, default=5.0, help="Grace period for shutdown")
    parser.add_argument("--autoscan", action="store_true", help="Scan RTU bus and regenerate config/devices.yaml before start")
    parser.add_argument("--scan-start", type=int, default=1, help="Autoscan start slave ID")
    parser.add_argument("--scan-end", type=int, default=40, help="Autoscan end slave ID")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    try:
        exit_code = asyncio.run(run(arguments))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        sys.exit(0)
