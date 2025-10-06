#!/usr/bin/env python3
"""
SERVER: Скрипт для безопасной остановки всех сервисов CUBE_RS SERVER
"""

import time
import psutil


def find_processes_by_name(name_patterns):
    """Поиск процессов по шаблонам имен"""
    processes = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"]) if proc.info["cmdline"] else ""
            for pattern in name_patterns:
                if pattern in cmdline:
                    processes.append(proc)
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes


def stop_process_safely(proc, name, timeout=10):
    """Безопасная остановка процесса"""
    try:
        print(f"🛑 Остановка {name} (PID: {proc.pid})...")

        # Сначала пробуем graceful shutdown
        proc.terminate()

        # Ждем завершения
        try:
            proc.wait(timeout=timeout)
            print(f"✅ {name} остановлен gracefully")
            return True
        except psutil.TimeoutExpired:
            print(f"⚠️ {name} не остановился за {timeout}с, принудительно завершаем...")
            proc.kill()
            try:
                proc.wait(timeout=5)
                print(f"💀 {name} принудительно остановлен")
                return True
            except psutil.TimeoutExpired:
                print(f"❌ Не удалось остановить {name}")
                return False

    except psutil.NoSuchProcess:
        print(f"✅ {name} уже остановлен")
        return True
    except Exception as e:
        print(f"❌ Ошибка остановки {name}: {e}")
        return False


def main():
    print("🛑 Безопасная остановка всех сервисов CUBE_RS SERVER...")
    print("=" * 60)

    # Список SERVER сервисов для остановки (в порядке остановки)
    services = [
        {
            "name": "Network Security Monitor",
            "patterns": [
                "network_security_monitor.py",
                "monitoring/network_security_monitor.py"
            ]
        },
        {
            "name": "Security Monitor",
            "patterns": [
                "security_monitor.py",
                "monitoring/security_monitor.py"
            ]
        },
        {
            "name": "Web Application",
            "patterns": [
                "web_app/app.py",
                "flask",
                "gunicorn"
            ]
        },
        {
            "name": "Resilient Tunnel Broker",
            "patterns": [
                "resilient_tunnel_broker.py",
                "tunnel_broker.py"
            ]
        },
        {
            "name": "Nginx (if running)",
            "patterns": [
                "nginx",
                "nginx: master process",
                "nginx: worker process"
            ]
        }
    ]

    stopped_count = 0
    total_found = 0

    for service in services:
        processes = find_processes_by_name(service["patterns"])

        if not processes:
            print(f"ℹ️ {service['name']}: не найден")
            continue

        for proc in processes:
            total_found += 1
            if stop_process_safely(proc, service["name"]):
                stopped_count += 1
            time.sleep(1)  # Пауза между остановками

    print("=" * 60)
    print(f"📊 Результат остановки: {stopped_count}/{total_found} процессов")

    # Проверяем, остались ли процессы
    remaining = []
    for service in services:
        processes = find_processes_by_name(service["patterns"])
        if processes:
            remaining.extend([f"{service['name']} (PID: {p.pid})" for p in processes])

    if remaining:
        print("⚠️ Оставшиеся процессы:")
        for proc in remaining:
            print(f"   - {proc}")
    else:
        print("✅ Все SERVER сервисы успешно остановлены!")

    print("=" * 60)


if __name__ == "__main__":
    main()