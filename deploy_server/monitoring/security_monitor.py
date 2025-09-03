#!/usr/bin/env python3
"""
Security Monitor - Мониторинг безопасности и алерты для CUBE_RS
Отслеживание подозрительной активности, неудачных попыток регистрации, нарушений безопасности
"""

import json
import logging
import os
import sqlite3
import smtplib
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import threading
import hashlib
from queue import Queue
import requests

logger = logging.getLogger(__name__)

@dataclass
class SecurityEvent:
    """Событие безопасности"""
    event_id: str
    event_type: str
    severity: str  # 'low', 'medium', 'high', 'critical'
    source_ip: str
    user_agent: str
    timestamp: str
    description: str
    details: Dict[str, Any]
    device_id: str = ""
    username: str = ""

@dataclass
class SecurityAlert:
    """Алерт безопасности"""
    alert_id: str
    alert_type: str
    severity: str
    title: str
    description: str
    events_count: int
    first_seen: str
    last_seen: str
    status: str = "active"  # active, acknowledged, resolved
    acknowledged_by: str = ""
    resolved_by: str = ""

class SecurityMonitor:
    """Монитор безопасности системы"""
    
    def __init__(self, db_path: str = "security_events.db", config: Dict[str, Any] = None):
        self.db_path = db_path
        self.config = config or self.load_default_config()
        self.event_queue = Queue()
        self.rate_limiters = defaultdict(lambda: deque())
        self.failed_attempts = defaultdict(lambda: deque())
        self.suspicious_ips = set()
        self.monitoring_active = False
        
        self.init_database()
        self.setup_logging()
        self.load_security_rules()
    
    def load_default_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации по умолчанию"""
        return {
            "monitoring": {
                "enabled": True,
                "check_interval": 60,  # секунды
                "max_events_per_minute": 100,
                "failed_login_threshold": 5,
                "failed_login_window": 300,  # секунды
                "suspicious_ip_threshold": 10,
                "rate_limit_window": 60
            },
            "alerts": {
                "email_enabled": False,
                "email_smtp_server": "localhost",
                "email_smtp_port": 587,
                "email_username": "",
                "email_password": "",
                "email_recipients": [],
                "webhook_enabled": False,
                "webhook_url": "",
                "telegram_enabled": False,
                "telegram_bot_token": "",
                "telegram_chat_id": ""
            },
            "rules": {
                "brute_force_detection": True,
                "geo_anomaly_detection": False,
                "device_fingerprint_tracking": True,
                "suspicious_user_agent_detection": True,
                "rate_limiting": True
            },
            "logging": {
                "level": "INFO",
                "file": "logs/security.log"
            }
        }
    
    def setup_logging(self):
        """Настройка логирования"""
        log_config = self.config.get('logging', {})
        log_level = log_config.get('level', 'INFO')
        log_file = log_config.get('file', 'logs/security.log')
        
        # Создаем директорию для логов
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
    
    def init_database(self):
        """Инициализация базы данных событий безопасности"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS security_events (
                        event_id TEXT PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        source_ip TEXT,
                        user_agent TEXT,
                        timestamp TEXT NOT NULL,
                        description TEXT NOT NULL,
                        details TEXT,
                        device_id TEXT DEFAULT '',
                        username TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS security_alerts (
                        alert_id TEXT PRIMARY KEY,
                        alert_type TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        events_count INTEGER NOT NULL,
                        first_seen TEXT NOT NULL,
                        last_seen TEXT NOT NULL,
                        status TEXT DEFAULT 'active',
                        acknowledged_by TEXT DEFAULT '',
                        resolved_by TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Индексы для производительности
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON security_events(timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON security_events(event_type)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_severity ON security_events(severity)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ip ON security_events(source_ip)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON security_alerts(status)")
                
                conn.commit()
                logger.info("База данных событий безопасности инициализирована")
                
        except Exception as e:
            logger.error(f"Ошибка инициализации БД безопасности: {e}")
            raise
    
    def load_security_rules(self):
        """Загрузка правил безопасности"""
        self.security_rules = {
            "suspicious_user_agents": [
                r"sqlmap", r"nikto", r"nmap", r"masscan", r"gobuster",
                r"dirb", r"dirbuster", r"burpsuite", r"owasp"
            ],
            "blocked_ips": set(),
            "whitelisted_ips": {"127.0.0.1", "::1"},
            "max_registration_attempts_per_hour": 10,
            "max_failed_logins_per_ip": 5
        }
    
    def log_security_event(self, 
                          event_type: str,
                          severity: str,
                          description: str,
                          source_ip: str = "",
                          user_agent: str = "",
                          details: Dict[str, Any] = None,
                          device_id: str = "",
                          username: str = ""):
        """Логирование события безопасности"""
        if details is None:
            details = {}
        
        event_id = hashlib.sha256(
            f"{event_type}_{source_ip}_{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]
        
        event = SecurityEvent(
            event_id=event_id,
            event_type=event_type,
            severity=severity,
            source_ip=source_ip,
            user_agent=user_agent,
            timestamp=datetime.now().isoformat(),
            description=description,
            details=details,
            device_id=device_id,
            username=username
        )
        
        # Добавляем в очередь для обработки
        self.event_queue.put(event)
        
        # Логируем событие
        log_message = f"[{severity.upper()}] {event_type}: {description}"
        if source_ip:
            log_message += f" | IP: {source_ip}"
        if username:
            log_message += f" | User: {username}"
        
        if severity == "critical":
            logger.critical(log_message)
        elif severity == "high":
            logger.error(log_message)
        elif severity == "medium":
            logger.warning(log_message)
        else:
            logger.info(log_message)
    
    def save_event_to_db(self, event: SecurityEvent):
        """Сохранение события в базу данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO security_events 
                    (event_id, event_type, severity, source_ip, user_agent, 
                     timestamp, description, details, device_id, username)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.event_id,
                    event.event_type,
                    event.severity,
                    event.source_ip,
                    event.user_agent,
                    event.timestamp,
                    event.description,
                    json.dumps(event.details),
                    event.device_id,
                    event.username
                ))
                conn.commit()
                
        except Exception as e:
            logger.error(f"Ошибка сохранения события безопасности: {e}")
    
    def detect_brute_force_attack(self, source_ip: str, username: str) -> bool:
        """Обнаружение атак брутфорса"""
        if not self.config.get('rules', {}).get('brute_force_detection', True):
            return False
        
        now = datetime.now()
        window = self.config.get('monitoring', {}).get('failed_login_window', 300)
        threshold = self.config.get('monitoring', {}).get('failed_login_threshold', 5)
        
        # Очищаем старые записи
        cutoff_time = now - timedelta(seconds=window)
        key = f"{source_ip}:{username}"
        
        # Удаляем старые попытки
        while (self.failed_attempts[key] and 
               datetime.fromisoformat(self.failed_attempts[key][0]) < cutoff_time):
            self.failed_attempts[key].popleft()
        
        # Добавляем текущую попытку
        self.failed_attempts[key].append(now.isoformat())
        
        # Проверяем превышение лимита
        if len(self.failed_attempts[key]) >= threshold:
            return True
        
        return False
    
    def detect_suspicious_user_agent(self, user_agent: str) -> bool:
        """Обнаружение подозрительных User-Agent строк"""
        if not self.config.get('rules', {}).get('suspicious_user_agent_detection', True):
            return False
        
        user_agent_lower = user_agent.lower()
        
        for pattern in self.security_rules['suspicious_user_agents']:
            if pattern in user_agent_lower:
                return True
        
        return False
    
    def detect_rate_limit_violation(self, source_ip: str) -> bool:
        """Обнаружение превышения лимитов частоты запросов"""
        if not self.config.get('rules', {}).get('rate_limiting', True):
            return False
        
        now = datetime.now()
        window = self.config.get('monitoring', {}).get('rate_limit_window', 60)
        max_requests = self.config.get('monitoring', {}).get('max_events_per_minute', 100)
        
        # Очищаем старые записи
        cutoff_time = now - timedelta(seconds=window)
        while (self.rate_limiters[source_ip] and 
               datetime.fromisoformat(self.rate_limiters[source_ip][0]) < cutoff_time):
            self.rate_limiters[source_ip].popleft()
        
        # Добавляем текущий запрос
        self.rate_limiters[source_ip].append(now.isoformat())
        
        # Проверяем превышение лимита
        if len(self.rate_limiters[source_ip]) > max_requests:
            return True
        
        return False
    
    def analyze_device_registration_patterns(self):
        """Анализ паттернов регистрации устройств"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Ищем множественные регистрации с одного IP
                cursor = conn.execute("""
                    SELECT source_ip, COUNT(*) as attempts
                    FROM security_events 
                    WHERE event_type = 'device_registration_attempt' 
                        AND timestamp > datetime('now', '-1 hour')
                    GROUP BY source_ip
                    HAVING attempts > ?
                """, (self.security_rules['max_registration_attempts_per_hour'],))
                
                for row in cursor.fetchall():
                    source_ip, attempts = row
                    
                    if source_ip not in self.security_rules['whitelisted_ips']:
                        self.log_security_event(
                            event_type="suspicious_registration_pattern",
                            severity="high",
                            description=f"Множественные попытки регистрации с IP {source_ip}",
                            source_ip=source_ip,
                            details={
                                "attempts_count": attempts,
                                "time_window": "1 hour",
                                "threshold": self.security_rules['max_registration_attempts_per_hour']
                            }
                        )
                        
                        # Добавляем IP в подозрительные
                        self.suspicious_ips.add(source_ip)
                
        except Exception as e:
            logger.error(f"Ошибка анализа паттернов регистрации: {e}")
    
    def create_security_alert(self, 
                            alert_type: str,
                            severity: str,
                            title: str,
                            description: str,
                            events_count: int = 1,
                            related_events: List[SecurityEvent] = None):
        """Создание алерта безопасности"""
        if related_events is None:
            related_events = []
        
        alert_id = hashlib.sha256(
            f"{alert_type}_{title}_{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]
        
        first_seen = last_seen = datetime.now().isoformat()
        if related_events:
            timestamps = [event.timestamp for event in related_events]
            first_seen = min(timestamps)
            last_seen = max(timestamps)
        
        alert = SecurityAlert(
            alert_id=alert_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            description=description,
            events_count=events_count,
            first_seen=first_seen,
            last_seen=last_seen
        )
        
        # Сохраняем алерт в БД
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO security_alerts
                    (alert_id, alert_type, severity, title, description, 
                     events_count, first_seen, last_seen, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    alert.alert_id,
                    alert.alert_type,
                    alert.severity,
                    alert.title,
                    alert.description,
                    alert.events_count,
                    alert.first_seen,
                    alert.last_seen,
                    alert.status
                ))
                conn.commit()
                
        except Exception as e:
            logger.error(f"Ошибка сохранения алерта: {e}")
        
        # Отправляем уведомления
        self.send_security_alert(alert)
        
        return alert
    
    def send_security_alert(self, alert: SecurityAlert):
        """Отправка уведомлений о событиях безопасности"""
        alert_config = self.config.get('alerts', {})
        
        # Email уведомления
        if alert_config.get('email_enabled', False):
            self.send_email_alert(alert, alert_config)
        
        # Webhook уведомления
        if alert_config.get('webhook_enabled', False):
            self.send_webhook_alert(alert, alert_config)
        
        # Telegram уведомления
        if alert_config.get('telegram_enabled', False):
            self.send_telegram_alert(alert, alert_config)
    
    def send_email_alert(self, alert: SecurityAlert, config: Dict[str, Any]):
        """Отправка email уведомления"""
        try:
            smtp_server = config.get('email_smtp_server', 'localhost')
            smtp_port = config.get('email_smtp_port', 587)
            username = config.get('email_username', '')
            password = config.get('email_password', '')
            recipients = config.get('email_recipients', [])
            
            if not recipients:
                return
            
            # Создаем сообщение
            msg = MIMEMultipart()
            msg['From'] = username
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = f"🚨 CUBE_RS Security Alert: {alert.title}"
            
            # Тело письма
            body = f"""
🚨 Security Alert - {alert.severity.upper()}

Alert ID: {alert.alert_id}
Type: {alert.alert_type}
Title: {alert.title}

Description:
{alert.description}

Events Count: {alert.events_count}
First Seen: {alert.first_seen}
Last Seen: {alert.last_seen}
Status: {alert.status}

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

This is an automated security alert from CUBE_RS monitoring system.
"""
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Отправляем
            server = smtplib.SMTP(smtp_server, smtp_port)
            if username and password:
                server.starttls()
                server.login(username, password)
            
            text = msg.as_string()
            server.sendmail(username, recipients, text)
            server.quit()
            
            logger.info(f"Email алерт отправлен: {alert.alert_id}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки email алерта: {e}")
    
    def send_webhook_alert(self, alert: SecurityAlert, config: Dict[str, Any]):
        """Отправка webhook уведомления"""
        try:
            webhook_url = config.get('webhook_url', '')
            if not webhook_url:
                return
            
            payload = {
                "alert_id": alert.alert_id,
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "title": alert.title,
                "description": alert.description,
                "events_count": alert.events_count,
                "first_seen": alert.first_seen,
                "last_seen": alert.last_seen,
                "status": alert.status,
                "timestamp": datetime.now().isoformat(),
                "system": "CUBE_RS"
            }
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            
            logger.info(f"Webhook алерт отправлен: {alert.alert_id}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки webhook алерта: {e}")
    
    def send_telegram_alert(self, alert: SecurityAlert, config: Dict[str, Any]):
        """Отправка Telegram уведомления"""
        try:
            bot_token = config.get('telegram_bot_token', '')
            chat_id = config.get('telegram_chat_id', '')
            
            if not bot_token or not chat_id:
                return
            
            # Эмодзи для разных уровней
            severity_emoji = {
                'low': '🟡',
                'medium': '🟠', 
                'high': '🔴',
                'critical': '🚨'
            }
            
            emoji = severity_emoji.get(alert.severity, '⚠️')
            
            message = f"""
{emoji} *CUBE_RS Security Alert*

*{alert.title}*

*Severity:* {alert.severity.upper()}
*Type:* {alert.alert_type}
*Events:* {alert.events_count}

*Description:*
{alert.description}

*Time:* {alert.last_seen}
*Alert ID:* `{alert.alert_id}`
"""
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            logger.info(f"Telegram алерт отправлен: {alert.alert_id}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки Telegram алерта: {e}")
    
    def process_event_queue(self):
        """Обработка очереди событий"""
        while self.monitoring_active:
            try:
                # Получаем события из очереди (с таймаутом)
                try:
                    event = self.event_queue.get(timeout=5)
                except:
                    continue
                
                # Сохраняем в БД
                self.save_event_to_db(event)
                
                # Анализируем на предмет создания алертов
                self.analyze_event_for_alerts(event)
                
                self.event_queue.task_done()
                
            except Exception as e:
                logger.error(f"Ошибка обработки событий: {e}")
                time.sleep(1)
    
    def analyze_event_for_alerts(self, event: SecurityEvent):
        """Анализ события для создания алертов"""
        # Проверка на брутфорс атаки
        if event.event_type == "failed_login":
            if self.detect_brute_force_attack(event.source_ip, event.username):
                self.create_security_alert(
                    alert_type="brute_force_attack",
                    severity="high",
                    title=f"Brute Force Attack from {event.source_ip}",
                    description=f"Detected brute force attack from IP {event.source_ip} "
                               f"targeting user {event.username}"
                )
        
        # Проверка подозрительных User-Agent
        if self.detect_suspicious_user_agent(event.user_agent):
            self.create_security_alert(
                alert_type="suspicious_user_agent",
                severity="medium",
                title="Suspicious User Agent Detected",
                description=f"Suspicious user agent detected: {event.user_agent} from {event.source_ip}"
            )
        
        # Проверка превышения лимитов
        if self.detect_rate_limit_violation(event.source_ip):
            self.create_security_alert(
                alert_type="rate_limit_violation",
                severity="medium",
                title=f"Rate Limit Violation from {event.source_ip}",
                description=f"IP {event.source_ip} exceeded rate limits"
            )
    
    def start_monitoring(self):
        """Запуск мониторинга безопасности"""
        if not self.config.get('monitoring', {}).get('enabled', True):
            logger.info("Мониторинг безопасности отключен в конфигурации")
            return
        
        logger.info("Запуск мониторинга безопасности")
        self.monitoring_active = True
        
        # Запускаем поток обработки событий
        event_processor_thread = threading.Thread(target=self.process_event_queue)
        event_processor_thread.daemon = True
        event_processor_thread.start()
        
        # Основной цикл мониторинга
        check_interval = self.config.get('monitoring', {}).get('check_interval', 60)
        
        while self.monitoring_active:
            try:
                # Анализ паттернов регистрации
                self.analyze_device_registration_patterns()
                
                # Очистка старых данных
                self.cleanup_old_data()
                
                time.sleep(check_interval)
                
            except KeyboardInterrupt:
                logger.info("Получен сигнал завершения мониторинга")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                time.sleep(10)
        
        self.stop_monitoring()
    
    def stop_monitoring(self):
        """Остановка мониторинга"""
        logger.info("Остановка мониторинга безопасности")
        self.monitoring_active = False
    
    def cleanup_old_data(self):
        """Очистка старых данных"""
        try:
            # Удаляем события старше 30 дней
            cutoff_date = (datetime.now() - timedelta(days=30)).isoformat()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    DELETE FROM security_events WHERE timestamp < ?
                """, (cutoff_date,))
                
                deleted_events = cursor.rowcount
                
                # Удаляем закрытые алерты старше 7 дней
                alert_cutoff = (datetime.now() - timedelta(days=7)).isoformat()
                cursor = conn.execute("""
                    DELETE FROM security_alerts 
                    WHERE status IN ('resolved', 'acknowledged') AND updated_at < ?
                """, (alert_cutoff,))
                
                deleted_alerts = cursor.rowcount
                conn.commit()
                
                if deleted_events > 0 or deleted_alerts > 0:
                    logger.info(f"Очищено {deleted_events} старых событий и {deleted_alerts} алертов")
                
        except Exception as e:
            logger.error(f"Ошибка очистки старых данных: {e}")
    
    def get_security_stats(self) -> Dict[str, Any]:
        """Получение статистики безопасности"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                stats = {}
                
                # Общая статистика событий
                cursor = conn.execute("SELECT COUNT(*) FROM security_events")
                stats['total_events'] = cursor.fetchone()[0]
                
                # События за последний час
                hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM security_events WHERE timestamp > ?
                """, (hour_ago,))
                stats['events_last_hour'] = cursor.fetchone()[0]
                
                # События по типам
                cursor = conn.execute("""
                    SELECT event_type, COUNT(*) 
                    FROM security_events 
                    WHERE timestamp > datetime('now', '-24 hours')
                    GROUP BY event_type
                """)
                stats['events_by_type_24h'] = dict(cursor.fetchall())
                
                # Активные алерты
                cursor = conn.execute("""
                    SELECT severity, COUNT(*) 
                    FROM security_alerts 
                    WHERE status = 'active'
                    GROUP BY severity
                """)
                stats['active_alerts_by_severity'] = dict(cursor.fetchall())
                
                # Топ подозрительных IP
                cursor = conn.execute("""
                    SELECT source_ip, COUNT(*) as events_count
                    FROM security_events 
                    WHERE severity IN ('high', 'critical') 
                        AND timestamp > datetime('now', '-24 hours')
                        AND source_ip != ''
                    GROUP BY source_ip
                    ORDER BY events_count DESC
                    LIMIT 10
                """)
                stats['top_suspicious_ips'] = dict(cursor.fetchall())
                
                stats['timestamp'] = datetime.now().isoformat()
                
                return stats
                
        except Exception as e:
            logger.error(f"Ошибка получения статистики безопасности: {e}")
            return {}

# Глобальный экземпляр монитора
_security_monitor: Optional[SecurityMonitor] = None

def get_security_monitor() -> SecurityMonitor:
    """Получение глобального экземпляра монитора безопасности"""
    global _security_monitor
    if not _security_monitor:
        db_path = os.path.join(os.path.dirname(__file__), "security_events.db")
        _security_monitor = SecurityMonitor(db_path)
    return _security_monitor

def main():
    """Главная функция для запуска монитора"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Security Monitor для CUBE_RS")
    parser.add_argument('--config', help='Путь к конфигурационному файлу')
    parser.add_argument('--daemon', action='store_true', help='Запуск в режиме демона')
    parser.add_argument('--stats', action='store_true', help='Показать статистику безопасности')
    parser.add_argument('--test-alert', help='Отправить тестовый алерт указанного типа')
    
    args = parser.parse_args()
    
    # Загружаем конфигурацию
    config = None
    if args.config and os.path.exists(args.config):
        with open(args.config, 'r', encoding='utf-8') as f:
            config = json.load(f)
    
    monitor = SecurityMonitor(config=config)
    
    if args.stats:
        stats = monitor.get_security_stats()
        print("📊 Статистика безопасности CUBE_RS:")
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return
    
    if args.test_alert:
        monitor.create_security_alert(
            alert_type="test",
            severity="medium",
            title=f"Test Alert - {args.test_alert}",
            description="Это тестовый алерт для проверки системы уведомлений"
        )
        print(f"✅ Тестовый алерт '{args.test_alert}' отправлен")
        return
    
    if args.daemon:
        try:
            monitor.start_monitoring()
        except KeyboardInterrupt:
            logger.info("Получен сигнал завершения")
        finally:
            monitor.stop_monitoring()
    else:
        print("🔒 CUBE_RS Security Monitor")
        print("Используйте --daemon для запуска мониторинга")
        print("Используйте --stats для просмотра статистики")

if __name__ == "__main__":
    main()