#!/usr/bin/env bash
# Unified launcher for EDGE Modbus RTU testnet (single serial port, multi‑slave).
#
# Starts the RTU bus simulator so EDGE can talk to many devices on one port.
# If `socat` is available, binds the simulator to the exact path
#   /dev/cu.usbserial-2130 (default) so you don't need to change configs.
# Otherwise, runs the simulator on a PTY and exports VFD_SERIAL_PORT accordingly.
#
# Usage:
#   ./start_testnet.sh           # start with defaults (KUB 1-6, VFD 10-33)
#   ./start_testnet.sh stop      # stop previously started background processes
#   ./start_testnet.sh --kub 1-6 --vfd 10-33 --port /dev/cu.usbserial-2130
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
SIM_PY="$REPO_ROOT/EDGE/tools/simulators/rtu_bus_sim.py"
LOG_DIR="$REPO_ROOT/logs"
PID_DIR="$REPO_ROOT/logs"
SOCAT_PID_FILE="$PID_DIR/testnet_socat.pid"
SIM_PID_FILE="$PID_DIR/testnet_sim.pid"
SIM_LOG_FILE="$LOG_DIR/testnet_sim.log"

mkdir -p "$LOG_DIR"

KUB_IDS="1-6"
VFD_IDS="10-33"
PORT_PATH="/dev/cu.usbserial-2130"

if [[ ${1:-} == "stop" ]]; then
  echo "⏹️  Stopping testnet..."
  if [[ -f "$SOCAT_PID_FILE" ]]; then
    SOCAT_PID=$(cat "$SOCAT_PID_FILE" || true)
    if [[ -n "${SOCAT_PID:-}" ]]; then
      kill "$SOCAT_PID" 2>/dev/null || true
    fi
    rm -f "$SOCAT_PID_FILE"
  fi
  if [[ -f "$SIM_PID_FILE" ]]; then
    SIM_PID=$(cat "$SIM_PID_FILE" || true)
    if [[ -n "${SIM_PID:-}" ]]; then
      kill "$SIM_PID" 2>/dev/null || true
    fi
    rm -f "$SIM_PID_FILE"
  fi
  echo "✅ Testnet stopped"
  exit 0
fi

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --kub) KUB_IDS="$2"; shift 2;;
    --vfd) VFD_IDS="$2"; shift 2;;
    --port) PORT_PATH="$2"; shift 2;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

command -v python >/dev/null 2>&1 || { echo "python not found"; exit 1; }

if command -v socat >/dev/null 2>&1; then
  echo "🚀 Starting RTU bus via socat at $PORT_PATH ..."
  # Kill previous socat if still running
  if [[ -f "$SOCAT_PID_FILE" ]]; then
    OLD=$(cat "$SOCAT_PID_FILE" || true)
    [[ -n "${OLD:-}" ]] && kill "$OLD" 2>/dev/null || true
    rm -f "$SOCAT_PID_FILE"
  fi
  # Ensure no stale symlink
  if [[ -L "$PORT_PATH" ]]; then
    sudo rm -f "$PORT_PATH"
  fi
  # Run socat + simulator (stdio) in background
  set -m
  sudo socat -d -d \
    pty,link="$PORT_PATH",mode=666,raw,echo=0 \
    exec:"python \"$SIM_PY\" --stdio --kub \"$KUB_IDS\" --vfd \"$VFD_IDS\"",pty,raw,echo=0 \
    > "$SIM_LOG_FILE" 2>&1 &
  SOCAT_PID=$!
  echo "$SOCAT_PID" > "$SOCAT_PID_FILE"
  set +m
  echo "📎 Port bound at: $PORT_PATH"
  echo "Exporting environment for this shell session:"
  echo "  export VFD_ENABLE_LIVE_TEST=true"
  echo "  export VFD_SERIAL_PORT=$PORT_PATH"
  export VFD_ENABLE_LIVE_TEST=true
  export VFD_SERIAL_PORT="$PORT_PATH"
else
  echo "ℹ️  socat not found — starting simulator on PTY and exporting env"
  # Kill previous sim if still running
  if [[ -f "$SIM_PID_FILE" ]]; then
    OLD=$(cat "$SIM_PID_FILE" || true)
    [[ -n "${OLD:-}" ]] && kill "$OLD" 2>/dev/null || true
    rm -f "$SIM_PID_FILE"
  fi
  # Start simulator in background, capture log
  nohup python "$SIM_PY" --kub "$KUB_IDS" --vfd "$VFD_IDS" > "$SIM_LOG_FILE" 2>&1 &
  SIM_PID=$!
  echo "$SIM_PID" > "$SIM_PID_FILE"
  # Wait for port line
  echo -n "⏳ Waiting for PTY port ... "
  for i in {1..50}; do
    if grep -q "Порт:" "$SIM_LOG_FILE"; then
      break
    fi
    sleep 0.1
  done
  echo "done"
  PORT_DETECTED=$(grep -m1 "Порт:" "$SIM_LOG_FILE" | sed -E 's/.*Порт:\s*(\S+).*/\1/')
  if [[ -z "$PORT_DETECTED" ]]; then
    echo "❌ Could not detect PTY port; see $SIM_LOG_FILE"
    exit 1
  fi
  echo "📎 Port: $PORT_DETECTED"
  echo "Exporting environment for this shell session:"
  echo "  export VFD_ENABLE_LIVE_TEST=true"
  echo "  export VFD_SERIAL_PORT=$PORT_DETECTED"
  export VFD_ENABLE_LIVE_TEST=true
  export VFD_SERIAL_PORT="$PORT_DETECTED"
fi

echo "\n🎯 Targets on the bus:"
echo "  KUB IDs: $KUB_IDS"
echo "  VFD IDs: $VFD_IDS"
echo "\n👉 Now you can run, for example:"
echo "  python EDGE/tests/test_vfd_inverter.py"
echo "  # Or scan different IDs by changing VFD_SLAVE_ID"

exit 0

