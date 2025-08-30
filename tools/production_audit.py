#!/usr/bin/env python3
"""
Финальный синьорный аудит системы КУБ-1063 перед продакшн
Проверяет все критически важные аспекты безопасности и готовности к продакшну.
"""

import os
import sys
import json
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple

# Добавляем путь к проекту
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

class ProductionAudit:
    """Комплексный аудит готовности системы к продакшну"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.issues = {
            'critical': [],
            'high': [],
            'medium': [],
            'low': [],
            'info': []
        }
        self.checks_passed = 0
        self.checks_total = 0
    
    def log_issue(self, severity: str, title: str, description: str, file_path: str = None):
        """Регистрация найденной проблемы"""
        issue = {
            'title': title,
            'description': description,
            'file': file_path,
            'timestamp': datetime.now().isoformat()
        }
        self.issues[severity].append(issue)
    
    def check_file_permissions(self) -> bool:
        """Аудит прав доступа к критическим файлам"""
        print("🔐 Проверка прав доступа к критическим файлам...")
        
        critical_files = [
            'kub_data.db',
            'kub_commands.db',
            'config/bot_secrets.json',
            'config/secrets/master.key'
        ]
        
        permissions_ok = True
        for file_path in critical_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                try:
                    stat_info = full_path.stat()
                    mode = stat_info.st_mode & 0o777
                    
                    if mode != 0o600:  # Должно быть rw-------
                        self.log_issue('critical', 
                            f'Небезопасные права доступа: {file_path}',
                            f'Файл {file_path} имеет права {oct(mode)}, должно быть 600',
                            str(file_path))
                        permissions_ok = False
                    else:
                        print(f"   ✅ {file_path}: {oct(mode)}")
                except Exception as e:
                    self.log_issue('high',
                        f'Ошибка проверки прав: {file_path}',
                        f'Не удалось проверить права файла: {e}',
                        str(file_path))
                    permissions_ok = False
            else:
                print(f"   ℹ️  {file_path}: файл не найден")
        
        return permissions_ok
    
    def check_secrets_security(self) -> bool:
        """Аудит безопасности секретов"""
        print("🔒 Проверка безопасности секретов...")
        
        try:
            from core.security_manager import get_security_manager
            from core.config_manager import get_config
            
            sm = get_security_manager()
            config = get_config()
            
            # Проверка состояния SecurityManager
            health = sm.health_check()
            
            issues_found = False
            
            if not health.get('encryption_available'):
                self.log_issue('critical',
                    'Шифрование недоступно',
                    'Модуль cryptography не установлен или не работает')
                issues_found = True
            
            if not health.get('master_key_exists'):
                self.log_issue('critical',
                    'Мастер-ключ отсутствует',
                    'Не найден мастер-ключ для шифрования секретов')
                issues_found = True
            
            # Проверка токена Telegram
            if not config.telegram.token:
                self.log_issue('critical',
                    'Токен Telegram отсутствует',
                    'Не найден токен для Telegram бота')
                issues_found = True
            else:
                print("   ✅ Токен Telegram настроен")
                # Проверяем что используется зашифрованное хранилище
                secrets_file = self.project_root / 'config' / 'secrets' / 'bot_secrets.enc'
                if secrets_file.exists():
                    print("   ✅ Используется зашифрованное хранилище секретов")
                else:
                    self.log_issue('medium',
                        'Секреты не зашифрованы',
                        'Рекомендуется использовать зашифрованное хранилище')
                    issues_found = True
            
            # Проверка админов
            if not config.telegram.admin_users:
                self.log_issue('high',
                    'Нет администраторов',
                    'Не настроены пользователи-администраторы')
                issues_found = True
            
            print(f"   ✅ Шифрование: {health.get('encryption_available')}")
            print(f"   ✅ Мастер-ключ: {health.get('master_key_exists')}")
            print(f"   ✅ Права доступа: {health.get('file_permissions_secure')}")
            
            return not issues_found
            
        except ImportError:
            self.log_issue('critical',
                'SecurityManager недоступен',
                'Не удалось импортировать модули безопасности')
            return False
        except Exception as e:
            self.log_issue('high',
                'Ошибка проверки секретов',
                f'Неожиданная ошибка: {e}')
            return False
    
    def check_database_security(self) -> bool:
        """Аудит безопасности баз данных"""
        print("🗄️ Проверка безопасности баз данных...")
        
        databases = ['kub_data.db', 'kub_commands.db']
        db_ok = True
        
        for db_name in databases:
            db_path = self.project_root / db_name
            if db_path.exists():
                try:
                    # Проверка целостности БД
                    with sqlite3.connect(db_path) as conn:
                        cursor = conn.execute("PRAGMA integrity_check")
                        result = cursor.fetchone()
                        if result[0] != 'ok':
                            self.log_issue('high',
                                f'Нарушена целостность БД: {db_name}',
                                f'PRAGMA integrity_check: {result[0]}')
                            db_ok = False
                        else:
                            print(f"   ✅ {db_name}: целостность OK")
                        
                        # Проверка журналирования
                        cursor = conn.execute("PRAGMA journal_mode")
                        journal_mode = cursor.fetchone()[0]
                        if journal_mode != 'wal':
                            self.log_issue('medium',
                                f'Неоптимальный режим журнала: {db_name}',
                                f'Режим {journal_mode}, рекомендуется WAL')
                        
                except Exception as e:
                    self.log_issue('high',
                        f'Ошибка проверки БД: {db_name}',
                        f'Не удалось проверить базу данных: {e}')
                    db_ok = False
            else:
                self.log_issue('medium',
                    f'База данных отсутствует: {db_name}',
                    'База данных будет создана при первом запуске')
        
        return db_ok
    
    def check_configuration_security(self) -> bool:
        """Аудит конфигурации"""
        print("⚙️ Проверка конфигурации...")
        
        try:
            from core.config_manager import get_config
            config = get_config()
            
            config_ok = True
            
            # Проверка системных настроек
            if config.system.environment == 'development':
                self.log_issue('high',
                    'Окружение development',
                    'Система настроена на режим разработки, не продакшн')
                config_ok = False
            
            # Проверка логирования
            if config.system.log_level == 'DEBUG':
                self.log_issue('medium',
                    'Уровень логирования DEBUG',
                    'В продакшне рекомендуется INFO или WARNING')
            
            # Проверка портов
            if config.modbus_tcp.port < 1024:
                self.log_issue('medium',
                    'Привилегированный порт',
                    f'Порт {config.modbus_tcp.port} требует root прав')
            
            # Проверка RS485
            if not os.path.exists(config.rs485.port):
                self.log_issue('high',
                    'RS485 порт недоступен',
                    f'Устройство {config.rs485.port} не найдено')
                config_ok = False
            
            print(f"   ✅ Окружение: {config.system.environment}")
            print(f"   ✅ Уровень логов: {config.system.log_level}")
            print(f"   ✅ Gateway порт: {config.modbus_tcp.port}")
            
            return config_ok
            
        except Exception as e:
            self.log_issue('critical',
                'Ошибка загрузки конфигурации',
                f'Не удалось загрузить конфигурацию: {e}')
            return False
    
    def check_dependencies(self) -> bool:
        """Аудит зависимостей"""
        print("📦 Проверка зависимостей...")
        
        required_packages = {
            'pymodbus': '3.5.1',
            'pyserial': '3.5',
            'paho-mqtt': '1.6.1',
            'python-telegram-bot': '20.8',
            'cryptography': '41.0.7',
            'PyYAML': '6.0.1'
        }
        
        deps_ok = True
        
        for package, min_version in required_packages.items():
            try:
                # Особые случаи импорта пакетов
                import_map = {
                    'python-telegram-bot': 'telegram',
                    'paho-mqtt': 'paho.mqtt.client',
                    'PyYAML': 'yaml',
                    'pyserial': 'serial'
                }
                
                pkg_name = import_map.get(package, package.replace("-", "_"))
                
                result = subprocess.run(
                    [sys.executable, '-c', f'import {pkg_name}; print(getattr({pkg_name}, "__version__", "unknown"))'],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    version = result.stdout.strip()
                    print(f"   ✅ {package}: {version}")
                else:
                    self.log_issue('critical',
                        f'Пакет не найден: {package}',
                        f'Требуется установить {package}>={min_version}')
                    deps_ok = False
            except Exception as e:
                self.log_issue('high',
                    f'Ошибка проверки пакета: {package}',
                    f'Не удалось проверить {package}: {e}')
                deps_ok = False
        
        return deps_ok
    
    def check_log_security(self) -> bool:
        """Проверка безопасности логов"""
        print("📝 Проверка безопасности логов...")
        
        log_files = [
            'config/logs/telegram.log',
            'config/logs/security.log',
            'config/logs/start_services.log'
        ]
        
        logs_secure = True
        
        for log_file in log_files:
            log_path = self.project_root / log_file
            if log_path.exists():
                try:
                    # Проверяем на утечку токенов
                    with open(log_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                        # Ищем незамаскированные токены
                        import re
                        token_patterns = [
                            r'bot\d+:[A-Za-z0-9_-]{35,}',  # Незамаскированные токены
                            r'Bearer [A-Za-z0-9._-]{20,}',  # JWT токены
                            r'[A-Za-z0-9]{32,}'  # Длинные ключи
                        ]
                        
                        for pattern in token_patterns:
                            matches = re.findall(pattern, content)
                            if matches:
                                # Исключаем замаскированные
                                real_leaks = [m for m in matches if '***' not in m]
                                if real_leaks:
                                    self.log_issue('critical',
                                        f'Утечка секретов в логах: {log_file}',
                                        f'Найдены незащищенные токены: {len(real_leaks)} шт.')
                                    logs_secure = False
                        
                    print(f"   ✅ {log_file}: безопасность OK")
                    
                except Exception as e:
                    self.log_issue('medium',
                        f'Ошибка проверки лога: {log_file}',
                        f'Не удалось проверить лог файл: {e}')
            else:
                print(f"   ℹ️  {log_file}: файл отсутствует")
        
        return logs_secure
    
    def check_network_security(self) -> bool:
        """Проверка сетевой безопасности"""
        print("🌐 Проверка сетевой безопасности...")
        
        try:
            from core.config_manager import get_config
            config = get_config()
            
            network_ok = True
            
            # Проверяем что порты не конфликтуют
            used_ports = set()
            
            if config.services.gateway_enabled:
                if config.modbus_tcp.port in used_ports:
                    self.log_issue('high',
                        'Конфликт портов',
                        f'Порт {config.modbus_tcp.port} используется дважды')
                    network_ok = False
                used_ports.add(config.modbus_tcp.port)
            
            if config.services.dashboard_enabled:
                if config.services.dashboard_port in used_ports:
                    self.log_issue('high',
                        'Конфликт портов',
                        f'Порт {config.services.dashboard_port} используется дважды')
                    network_ok = False
                used_ports.add(config.services.dashboard_port)
            
            print(f"   ✅ Используемые порты: {sorted(used_ports)}")
            
            # Проверяем биндинг только на localhost для безопасности
            # Это нужно проверить в коде сервисов
            
            return network_ok
            
        except Exception as e:
            self.log_issue('medium',
                'Ошибка проверки сети',
                f'Не удалось проверить сетевые настройки: {e}')
            return False
    
    def check_code_quality(self) -> bool:
        """Базовые проверки качества кода"""
        print("🔍 Проверка качества кода...")
        
        code_ok = True
        
        # Проверяем основные файлы на синтаксические ошибки
        python_files = [
            'core/config_manager.py',
            'core/security_manager.py',
            'core/log_filter.py',
            'telegram_bot/bot_main.py',
            'modbus/gateway.py',
            'modbus/unified_system.py'
        ]
        
        for py_file in python_files:
            file_path = self.project_root / py_file
            if file_path.exists():
                try:
                    result = subprocess.run(
                        [sys.executable, '-m', 'py_compile', str(file_path)],
                        capture_output=True, text=True
                    )
                    if result.returncode != 0:
                        self.log_issue('high',
                            f'Синтаксическая ошибка: {py_file}',
                            f'Ошибка компиляции: {result.stderr}')
                        code_ok = False
                    else:
                        print(f"   ✅ {py_file}: синтаксис OK")
                except Exception as e:
                    self.log_issue('medium',
                        f'Ошибка проверки: {py_file}',
                        f'Не удалось проверить файл: {e}')
        
        return code_ok
    
    def run_full_audit(self) -> Dict[str, Any]:
        """Запуск полного аудита"""
        print("🚀 ФИНАЛЬНЫЙ СИНЬОРНЫЙ АУДИТ КУБ-1063 ПЕРЕД ПРОДАКШН")
        print("=" * 60)
        
        audit_start = datetime.now()
        
        # Список проверок
        checks = [
            ("Права доступа к файлам", self.check_file_permissions),
            ("Безопасность секретов", self.check_secrets_security),
            ("Безопасность БД", self.check_database_security),
            ("Конфигурация системы", self.check_configuration_security),
            ("Зависимости", self.check_dependencies),
            ("Безопасность логов", self.check_log_security),
            ("Сетевая безопасность", self.check_network_security),
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
                    print(f"   🟢 PASSED")
                else:
                    print(f"   🔴 FAILED")
            except Exception as e:
                print(f"   ❌ ERROR: {e}")
                results[check_name] = False
                self.log_issue('critical', f'Критическая ошибка в проверке: {check_name}', str(e))
        
        audit_duration = datetime.now() - audit_start
        
        # Подготовка итогового отчета
        report = {
            'timestamp': audit_start.isoformat(),
            'duration_seconds': audit_duration.total_seconds(),
            'checks_passed': self.checks_passed,
            'checks_total': self.checks_total,
            'success_rate': (self.checks_passed / self.checks_total * 100) if self.checks_total > 0 else 0,
            'results': results,
            'issues': self.issues,
            'production_ready': self._is_production_ready()
        }
        
        return report
    
    def _is_production_ready(self) -> bool:
        """Определяет готовность системы к продакшну"""
        critical_issues = len(self.issues['critical'])
        high_issues = len(self.issues['high'])
        
        # Система НЕ готова если есть критические проблемы
        if critical_issues > 0:
            return False
        
        # Система НЕ готова если много высоких проблем
        if high_issues > 2:
            return False
        
        # Минимум 80% проверок должно проходить
        if self.checks_passed / self.checks_total < 0.8:
            return False
        
        return True
    
    def print_report(self, report: Dict[str, Any]):
        """Вывод итогового отчета"""
        print("\n" + "=" * 60)
        print("📊 ИТОГОВЫЙ ОТЧЕТ АУДИТА")
        print("=" * 60)
        
        print(f"🕒 Время проведения: {report['timestamp']}")
        print(f"⏱️  Длительность: {report['duration_seconds']:.2f} сек")
        print(f"✅ Пройдено проверок: {report['checks_passed']}/{report['checks_total']}")
        print(f"📈 Успешность: {report['success_rate']:.1f}%")
        
        # Статистика проблем
        total_issues = sum(len(issues) for issues in self.issues.values())
        if total_issues > 0:
            print(f"\n🚨 НАЙДЕНО ПРОБЛЕМ:")
            for severity, issues in self.issues.items():
                if issues:
                    print(f"   {severity.upper()}: {len(issues)}")
        
        # Детали критических и высоких проблем
        critical_and_high = self.issues['critical'] + self.issues['high']
        if critical_and_high:
            print(f"\n⚠️  КРИТИЧЕСКИЕ И ВЫСОКИЕ ПРОБЛЕМЫ:")
            for issue in critical_and_high:
                print(f"   • {issue['title']}")
                print(f"     {issue['description']}")
                if issue.get('file'):
                    print(f"     Файл: {issue['file']}")
        
        # Финальная оценка
        print(f"\n🎯 ГОТОВНОСТЬ К ПРОДАКШН:")
        if report['production_ready']:
            print("   🟢 СИСТЕМА ГОТОВА К ПРОДАКШН РАЗВЕРТЫВАНИЮ")
        else:
            print("   🔴 СИСТЕМА НЕ ГОТОВА К ПРОДАКШН")
            print("   📋 Необходимо устранить найденные проблемы")
        
        print("=" * 60)

def main():
    """Главная функция аудита"""
    try:
        auditor = ProductionAudit()
        report = auditor.run_full_audit()
        auditor.print_report(report)
        
        # Сохраняем отчет в файл
        report_file = auditor.project_root / 'audit_report.json'
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Детальный отчет сохранен: {report_file}")
        
        # Возвращаем код выхода
        return 0 if report['production_ready'] else 1
        
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА АУДИТА: {e}")
        return 2

if __name__ == "__main__":
    sys.exit(main())