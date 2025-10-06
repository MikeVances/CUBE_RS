#!/usr/bin/env python3
"""
SERVER Production Audit - Финальный аудит системы CUBE_RS перед продакшн
Проверяет все критически важные аспекты безопасности и готовности к продакшну.
Адаптирован для новой SERVER архитектуры CUBE_RS
"""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Добавляем путь к проекту SERVER
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class ServerProductionAudit:
    """Комплексный аудит готовности SERVER к продакшну"""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.issues = {"critical": [], "high": [], "medium": [], "low": [], "info": []}
        self.checks_passed = 0
        self.checks_total = 0

    def log_issue(
        self, severity: str, title: str, description: str, file_path: str = None
    ):
        """Регистрация найденной проблемы"""
        issue = {
            "title": title,
            "description": description,
            "file": file_path,
            "timestamp": datetime.now().isoformat(),
        }
        self.issues[severity].append(issue)

    def check_web_app_security(self) -> bool:
        """Аудит безопасности веб-приложения"""
        print("🔐 Проверка безопасности веб-приложения...")

        security_ok = True
        
        # Проверяем наличие ключевых компонентов
        web_app_files = [
            "web_app/app.py",
            "web_app/api_gateway.py",
            "web_app/rbac_system.py",
            "web_app/device_registry.py"
        ]
        
        for file_path in web_app_files:
            full_path = self.project_root / file_path
            if not full_path.exists():
                self.log_issue(
                    "high",
                    f"Отсутствует компонент: {file_path}",
                    f"Критический компонент веб-приложения не найден",
                    str(file_path)
                )
                security_ok = False
            else:
                print(f"   ✅ {file_path}: найден")

        # Проверяем наличие templates
        templates_dir = self.project_root / "web_app" / "templates"
        if not templates_dir.exists():
            self.log_issue(
                "high",
                "Отсутствуют шаблоны веб-интерфейса",
                "Директория templates не найдена",
                str(templates_dir)
            )
            security_ok = False
        else:
            required_templates = ["base.html", "index.html", "devices.html", "security.html"]
            for template in required_templates:
                template_path = templates_dir / template
                if not template_path.exists():
                    self.log_issue(
                        "medium",
                        f"Отсутствует шаблон: {template}",
                        f"Шаблон веб-интерфейса не найден",
                        str(template_path)
                    )
                else:
                    print(f"   ✅ Template {template}: найден")

        return security_ok

    def check_tunnel_system_security(self) -> bool:
        """Аудит безопасности туннельной системы"""
        print("🔗 Проверка безопасности туннельной системы...")

        tunnel_ok = True
        
        # Проверяем компоненты туннельной системы
        tunnel_files = [
            "tunnel_broker.py",
            "resilient_tunnel_broker.py",
            "security/mitm_protection.py",
            "security/mutual_tls.py"
        ]
        
        for file_path in tunnel_files:
            full_path = self.project_root / file_path
            if not full_path.exists():
                self.log_issue(
                    "medium",
                    f"Отсутствует компонент туннельной системы: {file_path}",
                    f"Компонент туннельной системы не найден",
                    str(file_path)
                )
                tunnel_ok = False
            else:
                print(f"   ✅ {file_path}: найден")

        return tunnel_ok

    def check_monitoring_security(self) -> bool:
        """Аудит системы мониторинга"""
        print("📊 Проверка системы мониторинга...")

        monitoring_ok = True
        
        monitoring_files = [
            "monitoring/security_monitor.py",
            "monitoring/network_security_monitor.py",
            "prometheus.yml"
        ]
        
        for file_path in monitoring_files:
            full_path = self.project_root / file_path
            if not full_path.exists():
                self.log_issue(
                    "medium",
                    f"Отсутствует компонент мониторинга: {file_path}",
                    f"Компонент системы мониторинга не найден",
                    str(file_path)
                )
                monitoring_ok = False
            else:
                print(f"   ✅ {file_path}: найден")

        return monitoring_ok

    def check_docker_configuration(self) -> bool:
        """Аудит Docker конфигурации"""
        print("🐳 Проверка Docker конфигурации...")

        docker_ok = True
        
        docker_files = [
            "docker-compose.yml",
            "Dockerfile.webapp",
            "Dockerfile.broker"
        ]
        
        for file_path in docker_files:
            full_path = self.project_root / file_path
            if not full_path.exists():
                self.log_issue(
                    "high",
                    f"Отсутствует Docker файл: {file_path}",
                    f"Docker конфигурация не найдена",
                    str(file_path)
                )
                docker_ok = False
            else:
                print(f"   ✅ {file_path}: найден")

        # Проверяем nginx конфигурацию
        nginx_dir = self.project_root / "nginx"
        if nginx_dir.exists():
            nginx_files = ["nginx.conf", "tunnel-broker.conf"]
            for nginx_file in nginx_files:
                nginx_path = nginx_dir / nginx_file
                if nginx_path.exists():
                    print(f"   ✅ nginx/{nginx_file}: найден")
                else:
                    self.log_issue(
                        "medium",
                        f"Отсутствует nginx конфигурация: {nginx_file}",
                        f"Nginx конфигурация не найдена",
                        str(nginx_path)
                    )

        return docker_ok

    def check_systemd_services(self) -> bool:
        """Аудит systemd сервисов"""
        print("⚙️ Проверка systemd сервисов...")

        systemd_ok = True
        
        systemd_dir = self.project_root / "systemd"
        if not systemd_dir.exists():
            self.log_issue(
                "medium",
                "Отсутствует директория systemd",
                "Конфигурации systemd сервисов не найдены",
                str(systemd_dir)
            )
            return False
        
        systemd_files = ["tunnel-broker.service", "web-app.service"]
        
        for file_path in systemd_files:
            full_path = systemd_dir / file_path
            if not full_path.exists():
                self.log_issue(
                    "medium",
                    f"Отсутствует systemd сервис: {file_path}",
                    f"Systemd конфигурация не найдена",
                    str(file_path)
                )
                systemd_ok = False
            else:
                print(f"   ✅ systemd/{file_path}: найден")

        return systemd_ok

    def check_dependencies(self) -> bool:
        """Аудит зависимостей SERVER"""
        print("📦 Проверка зависимостей SERVER...")

        required_packages = {
            "flask": "2.3.0",
            "flask-cors": "4.0.0", 
            "gunicorn": "20.1.0",
            "nginx": "nginx",
            "docker": "docker",
            "docker-compose": "docker-compose"
        }

        deps_ok = True

        for package, min_version in required_packages.items():
            try:
                if package in ["nginx", "docker", "docker-compose"]:
                    # Проверяем системные пакеты
                    result = subprocess.run(
                        [package, "--version"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        version = result.stdout.strip()
                        print(f"   ✅ {package}: {version}")
                    else:
                        self.log_issue(
                            "high",
                            f"Системный пакет не найден: {package}",
                            f"Требуется установить {package}",
                        )
                        deps_ok = False
                else:
                    # Проверяем Python пакеты
                    import_map = {
                        "flask": "flask",
                        "flask-cors": "flask_cors",
                        "gunicorn": "gunicorn"
                    }

                    pkg_name = import_map.get(package, package.replace("-", "_"))

                    result = subprocess.run(
                        [
                            sys.executable,
                            "-c",
                            f'import {pkg_name}; print(getattr({pkg_name}, "__version__", "unknown"))',
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        version = result.stdout.strip()
                        print(f"   ✅ {package}: {version}")
                    else:
                        self.log_issue(
                            "critical",
                            f"Python пакет не найден: {package}",
                            f"Требуется установить {package}>={min_version}",
                        )
                        deps_ok = False
            except Exception as e:
                self.log_issue(
                    "high",
                    f"Ошибка проверки пакета: {package}",
                    f"Не удалось проверить {package}: {e}",
                )
                deps_ok = False

        return deps_ok

    def check_file_permissions(self) -> bool:
        """Аудит прав доступа к критическим файлам SERVER"""
        print("🔐 Проверка прав доступа к критическим файлам...")

        critical_files = [
            "config/secrets/server_key.pem",
            "config/secrets/api_keys.json",
            "web_app/device_registry.db",
            "web_app/rbac_system.db"
        ]

        permissions_ok = True
        for file_path in critical_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                try:
                    stat_info = full_path.stat()
                    mode = stat_info.st_mode & 0o777

                    if mode > 0o640:  # Должно быть не более rw-r-----
                        self.log_issue(
                            "high",
                            f"Небезопасные права доступа: {file_path}",
                            f"Файл {file_path} имеет права {oct(mode)}, должно быть 640 или меньше",
                            str(file_path),
                        )
                        permissions_ok = False
                    else:
                        print(f"   ✅ {file_path}: {oct(mode)}")
                except Exception as e:
                    self.log_issue(
                        "high",
                        f"Ошибка проверки прав: {file_path}",
                        f"Не удалось проверить права файла: {e}",
                        str(file_path),
                    )
                    permissions_ok = False
            else:
                print(f"   ℹ️  {file_path}: файл не найден (будет создан)")

        return permissions_ok

    def check_code_quality(self) -> bool:
        """Базовые проверки качества кода SERVER"""
        print("🔍 Проверка качества кода SERVER...")

        code_ok = True

        # Проверяем основные файлы на синтаксические ошибки
        python_files = [
            "web_app/app.py",
            "web_app/api_gateway.py", 
            "web_app/rbac_system.py",
            "web_app/device_registry.py",
            "web_app/tailscale_integration.py",
            "tunnel_broker.py",
            "resilient_tunnel_broker.py",
            "monitoring/security_monitor.py"
        ]

        for py_file in python_files:
            file_path = self.project_root / py_file
            if file_path.exists():
                try:
                    result = subprocess.run(
                        [sys.executable, "-m", "py_compile", str(file_path)],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        self.log_issue(
                            "high",
                            f"Синтаксическая ошибка: {py_file}",
                            f"Ошибка компиляции: {result.stderr}",
                        )
                        code_ok = False
                    else:
                        print(f"   ✅ {py_file}: синтаксис OK")
                except Exception as e:
                    self.log_issue(
                        "medium",
                        f"Ошибка проверки: {py_file}",
                        f"Не удалось проверить файл: {e}",
                    )

        return code_ok

    def run_full_audit(self) -> dict[str, Any]:
        """Запуск полного аудита SERVER"""
        print("🚀 ФИНАЛЬНЫЙ АУДИТ SERVER CUBE_RS ПЕРЕД ПРОДАКШН")
        print("=" * 60)

        audit_start = datetime.now()

        # Список проверок для SERVER
        checks = [
            ("Безопасность веб-приложения", self.check_web_app_security),
            ("Туннельная система", self.check_tunnel_system_security),
            ("Система мониторинга", self.check_monitoring_security),
            ("Docker конфигурация", self.check_docker_configuration),
            ("Systemd сервисы", self.check_systemd_services),
            ("Права доступа к файлам", self.check_file_permissions),
            ("Зависимости", self.check_dependencies),
            ("Качество кода", self.check_code_quality),
        ]

        results = {}

        for check_name, check_func in checks:
            print(f"\n{check_name}:")
            try:
                result = check_func()
                results[check_name] = result
                self.checks_total += 1
                if result:
                    self.checks_passed += 1
                    print("   🟢 PASSED")
                else:
                    print("   🔴 FAILED")
            except Exception as e:
                print(f"   ❌ ERROR: {e}")
                results[check_name] = False
                self.log_issue(
                    "critical", f"Критическая ошибка в проверке: {check_name}", str(e)
                )

        audit_duration = datetime.now() - audit_start

        # Подготовка итогового отчета
        report = {
            "timestamp": audit_start.isoformat(),
            "duration_seconds": audit_duration.total_seconds(),
            "checks_passed": self.checks_passed,
            "checks_total": self.checks_total,
            "success_rate": (self.checks_passed / self.checks_total * 100)
            if self.checks_total > 0
            else 0,
            "results": results,
            "issues": self.issues,
            "production_ready": self._is_production_ready(),
        }

        return report

    def _is_production_ready(self) -> bool:
        """Определяет готовность SERVER к продакшну"""
        critical_issues = len(self.issues["critical"])
        high_issues = len(self.issues["high"])

        # Система НЕ готова если есть критические проблемы
        if critical_issues > 0:
            return False

        # Система НЕ готова если много высоких проблем
        if high_issues > 3:
            return False

        # Минимум 75% проверок должно проходить
        if self.checks_passed / self.checks_total < 0.75:
            return False

        return True

    def print_report(self, report: dict[str, Any]):
        """Вывод итогового отчета"""
        print("\n" + "=" * 60)
        print("📊 ИТОГОВЫЙ ОТЧЕТ АУДИТА SERVER")
        print("=" * 60)

        print(f"🕒 Время проведения: {report['timestamp']}")
        print(f"⏱️  Длительность: {report['duration_seconds']:.2f} сек")
        print(
            f"✅ Пройдено проверок: {report['checks_passed']}/{report['checks_total']}"
        )
        print(f"📈 Успешность: {report['success_rate']:.1f}%")

        # Статистика проблем
        total_issues = sum(len(issues) for issues in self.issues.values())
        if total_issues > 0:
            print("\n🚨 НАЙДЕНО ПРОБЛЕМ:")
            for severity, issues in self.issues.items():
                if issues:
                    print(f"   {severity.upper()}: {len(issues)}")

        # Детали критических и высоких проблем
        critical_and_high = self.issues["critical"] + self.issues["high"]
        if critical_and_high:
            print("\n⚠️  КРИТИЧЕСКИЕ И ВЫСОКИЕ ПРОБЛЕМЫ:")
            for issue in critical_and_high:
                print(f"   • {issue['title']}")
                print(f"     {issue['description']}")
                if issue.get("file"):
                    print(f"     Файл: {issue['file']}")

        # Финальная оценка
        print("\n🎯 ГОТОВНОСТЬ К ПРОДАКШН:")
        if report["production_ready"]:
            print("   🟢 SERVER ГОТОВ К ПРОДАКШН РАЗВЕРТЫВАНИЮ")
        else:
            print("   🔴 SERVER НЕ ГОТОВ К ПРОДАКШН")
            print("   📋 Необходимо устранить найденные проблемы")

        print("=" * 60)


def main():
    """Главная функция аудита SERVER"""
    try:
        auditor = ServerProductionAudit()
        report = auditor.run_full_audit()
        auditor.print_report(report)

        # Сохраняем отчет в файл
        report_file = auditor.project_root / "server_audit_report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"💾 Детальный отчет сохранен: {report_file}")

        # Возвращаем код выхода
        return 0 if report["production_ready"] else 1

    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА АУДИТА SERVER: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())