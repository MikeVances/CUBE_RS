#!/usr/bin/env python3
"""
Modbus RTU bus simulator over PTY (single serial port, multiple slave IDs).

- Creates one PTY (virtual serial port) and responds to FC03/FC04 for
  multiple devices (slave IDs) on the same port, emulating an RS‑485 bus.
- Includes minimal VFD map (U0-xx 0x1000..), and a lightweight KUB map stub.
  You can specify ID ranges for both.

Usage:
  python EDGE/tools/simulators/rtu_bus_sim.py --vfd 10-33 --kub 1-6

Then in another terminal point EDGE to the printed slave PTY path:
  export VFD_SERIAL_PORT=/dev/ttysXXX
  export VFD_ENABLE_LIVE_TEST=true
  export VFD_SLAVE_ID=10
  python EDGE/tests/test_vfd_inverter.py

Dependencies: only standard library (pty/select/termios).
"""

from __future__ import annotations

import argparse
import os
import pty
import re
import select
import subprocess
import sys
import termios
import time
from typing import Dict, List, Tuple


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def pack_crc(frame_wo_crc: bytes) -> bytes:
    c = crc16_modbus(frame_wo_crc)
    return frame_wo_crc + bytes((c & 0xFF, (c >> 8) & 0xFF))


def parse_id_ranges(spec: str) -> List[int]:
    """Parse ranges like "1-6,10,12-14" into a sorted list of IDs."""
    ids: set[int] = set()
    for part in re.split(r"[,\s]+", spec.strip()):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start = int(a)
            end = int(b)
            for i in range(min(start, end), max(start, end) + 1):
                ids.add(i)
        else:
            ids.add(int(part))
    return sorted(ids)


class BaseMap:
    def read(self, start: int, count: int) -> List[int] | None:
        raise NotImplementedError


class VFDMap(BaseMap):
    def __init__(self) -> None:
        self.regs: Dict[int, int] = {
            0x1000: 3,      # running_state (3=stop)
            0x1001: 0,      # fault_code
            0x1002: 263,    # set_frequency (26.3 Hz)
            0x1003: 0,      # running_frequency
            0x1004: 0,      # speed
            0x1005: 0,      # output voltage
            0x1006: 0,      # output current (0.1A)
            0x101A: 29,     # motor temp
            0x101B: 35,     # igbt temp
            0x102B: 0xAAAA,
            0x102C: 0xBBBB,
        }

    def read(self, start: int, count: int) -> List[int] | None:
        out: List[int] = []
        for off in range(count):
            addr = start + off
            val = self.regs.get(addr, 0)
            out.append(val & 0xFFFF)
        return out


class KUBMap(BaseMap):
    """Very lightweight KUB stub."""

    def __init__(self) -> None:
        # Holding/Input register map for KUB controller (plausible defaults)
        # Many values are scaled by 0.1 like in app_config mapping.
        self.regs: Dict[int, int] = {
            # Basic sensors
            0x0083: 1010,   # pressure (101.0 units)
            0x0084: 550,    # humidity 55.0%
            0x0085: 3000,   # CO2 ppm (raw)
            0x0086: 0,      # NH3 (raw)
            0x0087: 0,      # grv_base
            0x0088: 0,      # grv_tunnel
            0x0089: 450,    # damper (45.0%)
            0x008A: 100,    # air_intake_1
            0x008B: 200,    # air_intake_2
            0x008C: 300,    # air_intake_tunnel
            0x0092: 400,
            0x0093: 500,
            0x0094: 0,
            0x0095: 0,
            0x0096: 0,
            0x0097: 0,
            0x0098: 0,
            0x0099: 0,
            0x009A: 0,
            0x009B: 0,
            0x009C: 0,
            0x009D: 0,
            0x009E: 0,
            0x009F: 0,

            # Digital outputs bitfields
            0x0081: 0,      # digital_outputs_1
            0x0082: 0,      # digital_outputs_2
            0x00A2: 0,      # digital_outputs_3

            # Runtime counters and targets
            0x00D5: 230,    # temp_inside 23.0 C
            0x00D4: 220,    # temp_target 22.0 C
            0x00D6: 250,    # temp_vent_activation 25.0 C
            0x00D1: 500,    # ventilation_level 50.0%
            0x00D2: 1,      # ventilation_scheme
            0x00D0: 600,    # ventilation_target 60.0%
            0x00D3: 1234,   # day_counter

            # Alarms and warnings (active/registered)
            0x00C0: 0,
            0x00C1: 0,
            0x00C2: 0,
            0x00C3: 0,      # active_alarms
            0x00C4: 0,
            0x00C5: 0,
            0x00C6: 0,
            0x00C7: 0,      # registered_alarms
            0x00C8: 0,
            0x00C9: 0,
            0x00CA: 0,
            0x00CB: 0,      # active_warnings
            0x00CC: 0,
            0x00CD: 0,
            0x00CE: 0,
            0x00CF: 0,      # registered_warnings

            # Software/identity
            0x0301: 0x0102, # software_version stub
            0x0302: 0,
            0x0303: 0,
        }

    def read(self, start: int, count: int) -> List[int] | None:
        out: List[int] = []
        for off in range(count):
            addr = start + off
            val = self.regs.get(addr, 0)
            out.append(val & 0xFFFF)
        return out


class KUB1112Map(BaseMap):
    """Simplified map for KUB-1112 heating controller."""

    def __init__(self) -> None:
        self.regs: Dict[int, int] = {
            0x0301: 0x0201,
            0x0400: 500,
            0x0401: 1,
            0x0402: 150,
            0x0403: 50,
            0x0404: 80,
            0x0405: 350,
            0x0406: 120,
            0x0407: 0b0011,
            0x0408: 0b0101,
            0x0409: 2,
            0x0410: 0,
            0x0411: 0,
            0x0412: 0,
            0x0413: 0,
            0x0220: 1,
            0x0221: 9600,
        }

    def read(self, start: int, count: int) -> List[int] | None:
        out: List[int] = []
        for off in range(count):
            addr = start + off
            val = self.regs.get(addr, 0)
            out.append(val & 0xFFFF)
        return out


def set_raw(fd: int) -> None:
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = attrs[2] | termios.CLOCAL | termios.CREAD
    attrs[3] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def run_bus(
    vfd_ids: List[int],
    kub_ids: List[int],
    kub1112_ids: List[int],
    rfd: int | None = None,
    wfd: int | None = None,
    display_port: str | None = None,
) -> int:
    # If rfd/wfd provided, use stdin/stdout; otherwise create PTY pair
    if rfd is None or wfd is None:
        master_fd, slave_fd = pty.openpty()
        slave_name = os.ttyname(slave_fd)
        try:
            os.chmod(slave_name, 0o666)
        except Exception as exc:
            print(f"⚠️ Не удалось изменить права {slave_name}: {exc}")
        set_raw(master_fd)
        io_r = io_w = master_fd
    else:
        master_fd = None  # type: ignore[assignment]
        slave_fd = None   # type: ignore[assignment]
        slave_name = "<stdio>"
        io_r, io_w = rfd, wfd

    # Build device maps per slave ID
    devices: Dict[int, BaseMap] = {}
    for sid in vfd_ids:
        devices[sid] = VFDMap()
    for sid in kub_ids:
        devices.setdefault(sid, KUBMap())
    for sid in kub1112_ids:
        devices.setdefault(sid, KUB1112Map())

    port_label = display_port or slave_name
    print("─" * 80)
    print("🚌 RTU BUS симулятор (один порт, несколько устройств)")
    print(f"• Порт: {port_label}")
    if vfd_ids:
        print(f"• VFD IDs: {vfd_ids}")
    if kub_ids:
        print(f"• KUB IDs: {kub_ids}")
    if kub1112_ids:
        print(f"• KUB-1112 IDs: {kub1112_ids}")
    print("─" * 80, flush=True)

    poller = select.poll()
    poller.register(io_r, select.POLLIN)
    buf = bytearray()
    try:
        while True:
            events = poller.poll(1000)
            if not events:
                continue
            data = os.read(io_r, 4096)
            if not data:
                continue
            buf.extend(data)

            while len(buf) >= 8:
                frame = bytes(buf[:8])
                addr = frame[0]
                func = frame[1]
                start = (frame[2] << 8) | frame[3]
                count = (frame[4] << 8) | frame[5]
                recv_crc = (frame[7] << 8) | frame[6]
                calc_crc = crc16_modbus(frame[:6])
                if recv_crc != calc_crc:
                    buf.pop(0)
                    continue
                del buf[:8]

                dev = devices.get(addr)
                if not dev:
                    # No such slave on bus → ignore silently
                    continue

                if func not in (0x03, 0x04):
                    os.write(io_w, pack_crc(bytes([addr, func | 0x80, 0x01])))
                    continue

                regs = dev.read(start, count)
                if regs is None:
                    os.write(io_w, pack_crc(bytes([addr, func | 0x80, 0x02])))
                    continue
                bc = len(regs) * 2
                payload = bytearray([addr, func, bc])
                for val in regs:
                    payload.append((val >> 8) & 0xFF)
                    payload.append(val & 0xFF)
                os.write(io_w, pack_crc(bytes(payload)))
    except KeyboardInterrupt:
        print("\n⏹️  Остановлено пользователем")
    finally:
        if rfd is None or wfd is None:
            try:
                os.close(master_fd)  # type: ignore[arg-type]
            except Exception:
                pass
            try:
                os.close(slave_fd)  # type: ignore[arg-type]
            except Exception:
                pass
    return 0


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="RTU bus simulator (single PTY, multi-slave)")
    ap.add_argument("--vfd", default="10-33", help="VFD slave IDs (e.g. '10-33' or '10-15,20')")
    ap.add_argument("--kub", default="1-6", help="KUB-1063 slave IDs (e.g. '1-6')")
    ap.add_argument("--kub1112", default="", help="KUB-1112 slave IDs")
    ap.add_argument("--stdio", action="store_true", help="Use stdin/stdout instead of creating PTY (for use with socat link)")
    ap.add_argument("--port", help="Bind to fixed PTY path (requires write access)")
    args = ap.parse_args(argv)

    vfd_ids = parse_id_ranges(args.vfd) if args.vfd else []
    kub_ids = parse_id_ranges(args.kub) if args.kub else []
    kub1112_ids = parse_id_ranges(args.kub1112) if args.kub1112 else []
    if args.stdio:
        return run_bus(
            vfd_ids,
            kub_ids,
            kub1112_ids,
            rfd=sys.stdin.fileno(),
            wfd=sys.stdout.fileno(),
            display_port="<stdio>",
        )
    if args.port:
        # Use socat to create a PTY symlink to a fixed path
        temp_link = args.port
        tmp_command = [
            "socat",
            f"pty,link={temp_link},raw,echo=0,wait-slave=0",
            "STDIO",
        ]
        print(f"⚙️ Создаём PTY ссылку {args.port} через socat…")
        # Spawn socat and run simulator using its stdio
        with subprocess.Popen(tmp_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:
            assert proc.stdin and proc.stdout
            return run_bus(
                vfd_ids,
                kub_ids,
                kub1112_ids,
                rfd=proc.stdout.fileno(),
                wfd=proc.stdin.fileno(),
                display_port=args.port,
            )
    return run_bus(vfd_ids, kub_ids, kub1112_ids)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
