#!/usr/bin/env python3
"""
SERVER Setup Script - Полная инициализация CUBE_RS SERVER
Автоматизированная настройка всех компонентов SERVER
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SERVER-SETUP] %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ServerSetup:
    """Класс для настройки CUBE_RS SERVER"""
    
    def __init__(self):
        self.server_root = Path(__file__).parent.parent
        self.success_steps = []
        self.failed_steps = []
        
    def log_step(self, step_name: str, success: bool, details: str = ""):
        """Регистрация результата выполнения шага"""
        if success:
            self.success_steps.append(step_name)
            logger.info(f"✅ {step_name}")
            if details:
                logger.info(f"   {details}")
        else:
            self.failed_steps.append((step_name, details))
            logger.error(f"❌ {step_name}")
            if details:
                logger.error(f"   {details}")
    
    def create_directories(self) -> bool:
        """Создание необходимых директорий"""
        directories = [
            "data",
            "logs", 
            "config",
            "config/secrets",
            "web_app/templates",
            "web_app/static",
            "tools"
        ]
        
        try:
            for directory in directories:
                dir_path = self.server_root / directory
                dir_path.mkdir(parents=True, exist_ok=True)
                
            return True
        except Exception as e:
            self.log_step("Создание директорий", False, str(e))
            return False
    
    def check_python_dependencies(self) -> bool:
        """Проверка Python зависимостей"""
        required_packages = [
            "flask",
            "flask-cors", 
            "gunicorn",
            "websockets",
            "psutil",
            "cryptography"
        ]
        
        missing_packages = []
        
        for package in required_packages:
            try:
                import_name = package.replace("-", "_")
                result = subprocess.run(
                    [sys.executable, "-c", f"import {import_name}"],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    missing_packages.append(package)
            except Exception:
                missing_packages.append(package)
        
        if missing_packages:
            self.log_step(
                "Проверка Python зависимостей", 
                False, 
                f"Отсутствуют пакеты: {', '.join(missing_packages)}"
            )
            return False
        
        return True
    
    def setup_databases(self) -> bool:
        """Настройка баз данных SERVER"""
        try:
            # Запускаем скрипт создания баз данных
            setup_script = self.server_root / "tools" / "create_server_db.py"
            
            result = subprocess.run(
                [sys.executable, str(setup_script)],
                cwd=self.server_root,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return True
            else:
                self.log_step("Настройка баз данных", False, result.stderr)
                return False
                
        except Exception as e:
            self.log_step("Настройка баз данных", False, str(e))
            return False
    
    def create_default_config(self) -> bool:
        """Создание конфигурации по умолчанию"""
        try:
            config_dir = self.server_root / "config"
            
            # Создаем основной конфигурационный файл
            config_content = """# CUBE_RS SERVER Configuration
# Environment settings
FLASK_ENV=production
FLASK_DEBUG=0

# Server settings
SERVER_HOST=0.0.0.0
SERVER_PORT=8080
TUNNEL_BROKER_PORT=8081

# Database settings
DATABASE_URL=sqlite:///data/server.db

# Security settings
SECRET_KEY=change-this-in-production
SESSION_TIMEOUT=3600

# Logging settings
LOG_LEVEL=INFO
LOG_DIR=logs
"""
            
            config_file = config_dir / "server.env"
            with open(config_file, "w", encoding="utf-8") as f:
                f.write(config_content)
            
            return True
        except Exception as e:
            self.log_step("Создание конфигурации", False, str(e))
            return False
    
    def setup_systemd_services(self) -> bool:
        """Настройка systemd сервисов (опционально)"""
        try:
            systemd_dir = self.server_root / "systemd"
            if not systemd_dir.exists():
                # Если нет systemd конфигурации, пропускаем этот шаг
                return True
            
            # Проверяем доступность systemctl
            result = subprocess.run(
                ["which", "systemctl"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                # systemd недоступен (например, на macOS или в Docker)
                logger.info("   systemd недоступен, пропускаем настройку сервисов")
                return True
            
            # Копируем service файлы
            services = ["tunnel-broker.service", "web-app.service"]
            for service in services:
                service_file = systemd_dir / service
                if service_file.exists():
                    logger.info(f"   Найден сервис {service}")
            
            return True
        except Exception as e:
            # Не критичная ошибка
            logger.warning(f"Предупреждение при настройке systemd: {e}")
            return True
    
    def run_production_audit(self) -> bool:
        """Запуск производственного аудита"""
        try:
            audit_script = self.server_root / "tools" / "production_audit.py"
            
            if not audit_script.exists():
                logger.warning("Скрипт аудита не найден, пропускаем проверку")
                return True
            
            result = subprocess.run(
                [sys.executable, str(audit_script)],
                cwd=self.server_root,
                capture_output=True,
                text=True
            )
            
            # Аудит может вернуть код 1 если есть предупреждения
            if result.returncode in [0, 1]:
                logger.info("   Аудит завершен, проверьте отчет")
                return True
            else:
                self.log_step("Производственный аудит", False, result.stderr)
                return False
                
        except Exception as e:
            self.log_step("Производственный аудит", False, str(e))
            return False
    
    def run_full_setup(self):
        """Полная настройка SERVER"""
        print("🚀 ПОЛНАЯ НАСТРОЙКА CUBE_RS SERVER")
        print("=" * 60)
        
        setup_steps = [
            ("Создание директорий", self.create_directories),
            ("Проверка Python зависимостей", self.check_python_dependencies),
            ("Создание конфигурации", self.create_default_config),
            ("Настройка баз данных", self.setup_databases),
            ("Настройка systemd сервисов", self.setup_systemd_services),
            ("Производственный аудит", self.run_production_audit)
        ]
        
        for step_name, step_func in setup_steps:
            logger.info(f"▶️ {step_name}...")
            success = step_func()
            self.log_step(step_name, success)
        
        # Выводим итоги
        print("\n" + "=" * 60)
        print("📊 РЕЗУЛЬТАТЫ НАСТРОЙКИ")
        print("=" * 60)
        
        print(f"✅ Успешно: {len(self.success_steps)} шагов")
        print(f"❌ Ошибки: {len(self.failed_steps)} шагов")
        
        if self.failed_steps:
            print("\n🚨 ОБНАРУЖЕННЫЕ ПРОБЛЕМЫ:")
            for step_name, details in self.failed_steps:
                print(f"   • {step_name}")
                if details:
                    print(f"     {details}")
        
        if len(self.failed_steps) == 0:
            print("\n🎉 SERVER УСПЕШНО НАСТРОЕН!")
            print("\n📋 Следующие шаги:")
            print("1️⃣ python tools/start_all_services.py  # Запустить сервисы")
            print("2️⃣ Открыть http://localhost:8080      # Веб-интерфейс")
            print("3️⃣ Проверить логи в директории logs/")
            return True
        else:
            print("\n⚠️ НАСТРОЙКА ЗАВЕРШЕНА С ПРЕДУПРЕЖДЕНИЯМИ")
            print("📋 Необходимо устранить проблемы перед запуском")
            return False


def main():
    """Главная функция"""
    setup = ServerSetup()
    return setup.run_full_setup()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)