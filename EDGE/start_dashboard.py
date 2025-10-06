#!/usr/bin/env python3
"""
EDGE Streamlit Dashboard Launcher
Запускает веб-интерфейс мониторинга для CUBE_RS EDGE устройств
"""

import sys
import os
import subprocess
from pathlib import Path

def main():
    # Находим путь к dashboard приложению
    dashboard_path = Path(__file__).parent / "web_dashboard" / "app.py"
    
    if not dashboard_path.exists():
        print(f"❌ Dashboard app не найден: {dashboard_path}")
        return 1
    
    print("🚀 Запуск CUBE_RS EDGE Dashboard...")
    print(f"   Dashboard: {dashboard_path}")
    print("   URL: http://localhost:8501")
    print("   Ctrl+C для остановки")
    
    # Запускаем Streamlit
    cmd = [
        sys.executable, "-m", "streamlit", "run", 
        str(dashboard_path),
        "--server.port", "8501",
        "--server.address", "0.0.0.0",
        "--theme.base", "dark"
    ]
    
    try:
        return subprocess.run(cmd).returncode
    except KeyboardInterrupt:
        print("\n🛑 Dashboard остановлен")
        return 0
    except Exception as e:
        print(f"❌ Ошибка запуска dashboard: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())