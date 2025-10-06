#!/usr/bin/env python3
"""Unified launcher for EDGE node (gateway + runtime services)."""

import argparse
import asyncio
import os
import signal
import sys
from pathlib import Path
from typing import List, Tuple

import yaml

EDGE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EDGE_DIR))

from core.config_manager import get_config, reload_config


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


def build_gateway_command(rs485_port: str, args: argparse.Namespace) -> List[str]:
    """Compose command line for modbus gateway."""
    cmd = [sys.executable, "modbus/gateway.py", "--port", rs485_port]
    if args.modbus_port:
        cmd.extend(["--modbus-port", str(args.modbus_port)])
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
    cfg_path = EDGE_DIR / "config" / "app_config.yaml"
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


async def run(args: argparse.Namespace) -> int:
    cfg_rs485, cfg_modbus_port = read_config_defaults()

    rs485_port = args.rs485_port or cfg_rs485
    modbus_port = args.modbus_port if args.modbus_port is not None else cfg_modbus_port

    # Propagate overrides to environment so gateway/start.py see consistent values
    os.environ["MODBUS_RTU_PORT"] = rs485_port
    os.environ["MODBUS_TCP_PORT"] = str(modbus_port)

    if args.offline:
        os.environ["EDGE_OFFLINE_MODE"] = "true"

    # Reload config after applying overrides
    config = reload_config()
    if config is None:
        config = get_config()
    config.rs485.port = rs485_port
    config.modbus_tcp.port = modbus_port

    processes = []

    if not args.no_gateway:
        gateway_cmd = build_gateway_command(rs485_port, args)
        print(f"🚀 Starting Modbus gateway: {' '.join(gateway_cmd)}")
        gateway = await start_process("GATEWAY", gateway_cmd)
        processes.append(gateway)
        # Give gateway a moment to initialize; if it dies immediately, abort.
        await asyncio.sleep(args.gateway_startup_delay)
        if gateway.returncode is not None:
            print("❌ Gateway exited early, stopping launcher")
            return gateway.returncode
    else:
        print("⏭️ Modbus gateway launch skipped (no-gateway flag)")

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
    parser.add_argument("--no-gateway", action="store_true", help="Do not launch modbus gateway")
    parser.add_argument("--gateway-startup-delay", type=float, default=2.0, help="Seconds to wait after starting gateway")
    parser.add_argument("--shutdown-timeout", type=float, default=5.0, help="Grace period for shutdown")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    try:
        exit_code = asyncio.run(run(arguments))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        sys.exit(0)
