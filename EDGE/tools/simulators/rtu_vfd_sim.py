#!/usr/bin/env python3
"""
Простой программный симулятор Modbus RTU (VFD) поверх виртуального TTY (PTY).

Назначение:
- Создать пару master/slave псевдотерминалов (PTY) на macOS/Linux.
- EDGE/тесты подключаются к пути slave (как к обычному последовательному порту).
- Симулятор читает запросы на стороне master и отдаёт ответы, эмулируя часть
  карты регистров VFD (FC03 и FC04).

Запуск (в одном терминале):
    python EDGE/tools/simulators/rtu_vfd_sim.py --slave-id 1

Выведет путь к slave-порту. В другом терминале запустите:
    export VFD_SERIAL_PORT=<путь_из_вывода>
    export VFD_ENABLE_LIVE_TEST=true
    python EDGE/tests/test_vfd_inverter.py

Зависимости: стандартная библиотека (без pyserial).
"""

from __future__ import annotations

import argparse
import os
import pty
import select
import sys
import termios
import time
from typing import Dict


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


class VFDMap:
    """Минимальная карта регистров для ответов FC03/FC04.
    Адреса взяты из адаптера (U0-xx → 0x1000..).
    """

    def __init__(self) -> None:
        self.regs: Dict[int, int] = {
            0x1000: 3,      # running_state (3=стоп)
            0x1001: 0,      # fault_code
            0x1002: 263,    # set_frequency (26.3 Hz → 263 с масштабом 0.1)
            0x1003: 0,      # running_frequency
            0x1004: 0,      # speed rpm
            0x1005: 0,      # output voltage
            0x1006: 0,      # output current (0.1A)
            0x101A: 29,     # motor temp
            0x101B: 35,     # igbt temp
            0x102B: 0xAAAA, # serial low (для примера)
            0x102C: 0xBBBB, # serial high
        }

    def read(self, start: int, count: int) -> list[int] | None:
        out = []
        for off in range(count):
            addr = start + off
            if addr not in self.regs:
                return None
            out.append(self.regs[addr] & 0xFFFF)
        return out


def set_raw(fd: int) -> None:
    """Настройка master PTY в «сырое» состояние (минимум обработки)."""
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0  # iflag
    attrs[1] = 0  # oflag
    attrs[2] = attrs[2] | termios.CLOCAL | termios.CREAD  # cflag
    attrs[3] = 0  # lflag
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def run(slave_id: int) -> int:
    master_fd, slave_fd = pty.openpty()
    slave_name = os.ttyname(slave_fd)
    set_raw(master_fd)

    print("─" * 72)
    print("👾 RTU VFD симулятор запущен")
    print(f"• Slave ID: {slave_id}")
    print(f"• Подключайтесь к этому порту из EDGE: {slave_name}")
    print("  Пример: export VFD_SERIAL_PORT=" + slave_name)
    print("─" * 72, flush=True)

    vmap = VFDMap()
    poller = select.poll()
    poller.register(master_fd, select.POLLIN)

    try:
        buf = bytearray()
        while True:
            events = poller.poll(1000)  # 1s
            if not events:
                # чуть изменяем частоту/температуру для правдоподобности
                vmap.regs[0x1003] = max(0, vmap.regs[0x1003] - 1)
                continue
            data = os.read(master_fd, 4096)
            if not data:
                continue
            buf.extend(data)

            # Пытаемся разобрать стандартный запрос FC03/FC04 (8 байт)
            while len(buf) >= 8:
                frame = bytes(buf[:8])
                addr = frame[0]
                func = frame[1]
                start = (frame[2] << 8) | frame[3]
                count = (frame[4] << 8) | frame[5]
                recv_crc = (frame[7] << 8) | frame[6]
                calc_crc = crc16_modbus(frame[:6])

                # Если кадр не наш — удаляем первый байт и продолжаем
                if recv_crc != calc_crc:
                    buf.pop(0)
                    continue

                # Съедаем 8 байт
                del buf[:8]

                if addr != slave_id:
                    # Игнорируем кадры для других адресов
                    continue

                if func in (0x03, 0x04):
                    regs = vmap.read(start, count)
                    if regs is None:
                        # Exception: Illegal Address (0x02)
                        resp = bytes([addr, func | 0x80, 0x02])
                        os.write(master_fd, pack_crc(resp))
                        continue
                    bc = len(regs) * 2
                    payload = bytearray([addr, func, bc])
                    for val in regs:
                        payload.append((val >> 8) & 0xFF)
                        payload.append(val & 0xFF)
                    os.write(master_fd, pack_crc(bytes(payload)))
                else:
                    # Unsupported function → Illegal Function (0x01)
                    resp = bytes([addr, func | 0x80, 0x01])
                    os.write(master_fd, pack_crc(resp))
    except KeyboardInterrupt:
        print("\n⏹️  Остановлено пользователем")
    finally:
        try:
            os.close(master_fd)
        except Exception:
            pass
        try:
            os.close(slave_fd)
        except Exception:
            pass
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Modbus RTU VFD simulator over PTY")
    ap.add_argument("--slave-id", type=int, default=1, help="Modbus slave ID (default: 1)")
    args = ap.parse_args(argv)
    return run(args.slave_id)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

