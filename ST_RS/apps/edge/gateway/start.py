#!/usr/bin/env python3
"""
Apps Gateway entrypoint: runs edge starter from project root.
"""
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    cmd = [sys.executable, str(project_root / "start_edge.py")]
    print(f"🚀 Launching Edge from apps/gateway: {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(project_root))


if __name__ == "__main__":
    sys.exit(main())

