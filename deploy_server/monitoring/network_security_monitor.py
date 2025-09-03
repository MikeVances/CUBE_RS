#!/usr/bin/env python3
"""
Network Security Monitor - Мониторинг сетевой безопасности
Обнаружение MITM атак, подозрительного трафика, аномалий сети
"""

import json
import logging
import os
import socket
import sqlite3
import subprocess
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass
import hashlib
import ssl
import requests
from scapy import all as scapy
from scapy.layers.inet import IP, TCP, UDP, ICMP
from scapy.layers.dns import DNS
from scapy.layers.http import HTTP
import ipaddress
import geoip2.database
import geoip2.errors

logger = logging.getLogger(__name__)

@dataclass
class NetworkEvent:
    """Событие сетевой безопасности"""
    event_id: str
    event_type: str  # 'dns_anomaly', 'cert_change', 'suspicious_connection', etc.
    severity: str
    source_ip: str
    dest_ip: str
    protocol: str
    timestamp: str
    description: str
    details: Dict[str, Any]
    
@dataclass
class CertificateChange:
    """Изменение сертификата"""
    hostname: str
    old_fingerprint: str
    new_fingerprint: str
    timestamp: str
    is_suspicious: bool

@dataclass
class DNSEvent:
    """DNS событие"""
    domain: str
    resolved_ip: str
    query_type: str
    source_ip: str
    timestamp: str
    is_suspicious: bool

class NetworkSecurityMonitor:
    """Монитор сетевой безопасности"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or self.load_default_config()
        self.db_path = self.config.get('database', {}).get('path', 'network_security.db')
        
        # Кэши для обнаружения аномалий
        self.known_certificates = {}
        self.dns_cache = defaultdict(set)
        self.connection_history = defaultdict(deque)
        self.suspicious_ips = set()
        self.trusted_certificates = set()
        
        # Статистика
        self.packet_stats = defaultdict(int)
        
        # Флаг активности
        self.monitoring_active = False
        
        self.init_database()
        self.load_trusted_data()
        
        # GeoIP база (опционально)
        self.geoip_reader = self.init_geoip()
    
    def load_default_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации по умолчанию"""
        return {
            "monitoring": {
                "enabled": True,
                "interface": "any",  # Сетевой интерфейс для мониторинга
                "packet_capture": True,
                "dns_monitoring": True,
                "certificate_monitoring": True,
                "geo_analysis": False
            },
            "detection": {
                "dns_spoofing_threshold": 3,  # Количество разных IP для одного домена
                "certificate_change_alert": True,
                "suspicious_country_codes": ["CN", "RU", "KP", "IR"],  # Список подозрительных стран
                "private_ip_resolution_alert": True,
                "connection_anomaly_threshold": 100,
                "packet_analysis_depth": 1000  # Количество пакетов для анализа
            },
            "database": {
                "path": "network_security.db",
                "retention_days": 30
            },
            "alerts": {
                "mitm_detection": True,
                "dns_anomaly": True,
                "certificate_pinning_failure": True
            },
            "trusted": {
                "domains_file": "/etc/cube_gateway/trusted_domains.txt",
                "certificates_file": "/etc/cube_gateway/trusted_certificates.json",
                "ip_whitelist_file": "/etc/cube_gateway/trusted_ips.txt"
            },
            "geoip": {
                "enabled": False,
                "database_path": "/usr/share/GeoIP/GeoLite2-Country.mmdb"
            }
        }
    
    def init_database(self):
        """Инициализация базы данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS network_events (
                        event_id TEXT PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        source_ip TEXT,
                        dest_ip TEXT,
                        protocol TEXT,
                        timestamp TEXT NOT NULL,
                        description TEXT NOT NULL,
                        details TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS certificate_changes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        hostname TEXT NOT NULL,
                        old_fingerprint TEXT,
                        new_fingerprint TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        is_suspicious BOOLEAN DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS dns_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        domain TEXT NOT NULL,
                        resolved_ip TEXT NOT NULL,
                        query_type TEXT,
                        source_ip TEXT,
                        timestamp TEXT NOT NULL,
                        is_suspicious BOOLEAN DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Индексы
                conn.execute("CREATE INDEX IF NOT EXISTS idx_network_events_timestamp ON network_events(timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_network_events_type ON network_events(event_type)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cert_changes_hostname ON certificate_changes(hostname)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_dns_events_domain ON dns_events(domain)")
                
                conn.commit()
                logger.info("База данных сетевой безопасности инициализирована")
                
        except Exception as e:
            logger.error(f"Ошибка инициализации БД сетевой безопасности: {e}")
            raise
    
    def init_geoip(self) -> Optional[Any]:
        """Инициализация GeoIP базы"""
        if not self.config.get('geoip', {}).get('enabled', False):
            return None
        
        try:
            geoip_path = self.config.get('geoip', {}).get('database_path')
            if geoip_path and os.path.exists(geoip_path):
                return geoip2.database.Reader(geoip_path)
            else:
                logger.warning("GeoIP база данных не найдена")
                return None
        except Exception as e:
            logger.warning(f"Не удалось инициализировать GeoIP: {e}")
            return None
    
    def load_trusted_data(self):
        """Загрузка доверенных данных"""
        try:
            # Загрузка доверенных сертификатов
            trusted_certs_file = self.config.get('trusted', {}).get('certificates_file')
            if trusted_certs_file and os.path.exists(trusted_certs_file):
                with open(trusted_certs_file, 'r', encoding='utf-8') as f:
                    cert_data = json.load(f)
                    self.trusted_certificates = set(cert_data.get('fingerprints', []))
                    logger.info(f"Загружено {len(self.trusted_certificates)} доверенных сертификатов")
        
        except Exception as e:
            logger.warning(f"Не удалось загрузить доверенные данные: {e}")
    
    def log_network_event(self, event_type: str, severity: str, description: str,
                         source_ip: str = "", dest_ip: str = "", protocol: str = "",
                         details: Dict[str, Any] = None):
        """Логирование события сетевой безопасности"""
        if details is None:
            details = {}
        
        event_id = hashlib.sha256(
            f"{event_type}_{source_ip}_{dest_ip}_{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]
        
        event = NetworkEvent(
            event_id=event_id,
            event_type=event_type,
            severity=severity,
            source_ip=source_ip,
            dest_ip=dest_ip,
            protocol=protocol,
            timestamp=datetime.now().isoformat(),
            description=description,
            details=details
        )
        
        # Сохраняем в БД
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO network_events
                    (event_id, event_type, severity, source_ip, dest_ip, protocol,
                     timestamp, description, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.event_id,
                    event.event_type,
                    event.severity,
                    event.source_ip,
                    event.dest_ip,
                    event.protocol,
                    event.timestamp,
                    event.description,
                    json.dumps(event.details)
                ))
                conn.commit()
                
        except Exception as e:
            logger.error(f"Ошибка сохранения сетевого события: {e}")
        
        # Логируем
        log_message = f"[{severity.upper()}] {event_type}: {description}"
        if source_ip:
            log_message += f" | Src: {source_ip}"
        if dest_ip:
            log_message += f" | Dst: {dest_ip}"
        
        if severity == "critical":
            logger.critical(log_message)
        elif severity == "high":
            logger.error(log_message)
        elif severity == "medium":
            logger.warning(log_message)
        else:
            logger.info(log_message)
    
    def check_certificate_change(self, hostname: str, cert_fingerprint: str) -> bool:
        """Проверка изменения сертификата"""
        if hostname in self.known_certificates:
            old_fingerprint = self.known_certificates[hostname]
            
            if old_fingerprint != cert_fingerprint:
                # Обнаружена смена сертификата
                is_suspicious = cert_fingerprint not in self.trusted_certificates
                
                # Сохраняем в БД
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        conn.execute("""
                            INSERT INTO certificate_changes
                            (hostname, old_fingerprint, new_fingerprint, timestamp, is_suspicious)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            hostname,
                            old_fingerprint,
                            cert_fingerprint,
                            datetime.now().isoformat(),
                            is_suspicious
                        ))
                        conn.commit()
                        
                except Exception as e:
                    logger.error(f"Ошибка сохранения смены сертификата: {e}")
                
                # Логируем событие
                severity = "critical" if is_suspicious else "medium"
                self.log_network_event(
                    event_type="certificate_change",
                    severity=severity,
                    description=f"Certificate change detected for {hostname}",
                    details={
                        "hostname": hostname,
                        "old_fingerprint": old_fingerprint,
                        "new_fingerprint": cert_fingerprint,
                        "is_suspicious": is_suspicious
                    }
                )
                
                return False  # Возможная MITM атака
        
        # Сохраняем новый сертификат
        self.known_certificates[hostname] = cert_fingerprint
        return True
    
    def analyze_dns_response(self, packet):
        """Анализ DNS ответа"""
        if not packet.haslayer(DNS):
            return
        
        dns_layer = packet[DNS]
        if dns_layer.qr == 1:  # Это ответ
            try:
                # Извлекаем информацию
                domain = dns_layer.qd.qname.decode('utf-8').rstrip('.')
                
                # Анализируем ответы
                for i in range(dns_layer.ancount):
                    answer = dns_layer.an[i]
                    if answer.type == 1:  # A запись
                        resolved_ip = answer.rdata
                        self.analyze_dns_resolution(domain, resolved_ip, packet[IP].src)
                        
            except Exception as e:
                logger.debug(f"Ошибка анализа DNS пакета: {e}")
    
    def analyze_dns_resolution(self, domain: str, resolved_ip: str, source_ip: str):
        """Анализ DNS резолюции на предмет аномалий"""
        try:
            # Проверяем на DNS спуфинг
            self.dns_cache[domain].add(resolved_ip)
            
            # Если у одного домена много разных IP
            ip_count = len(self.dns_cache[domain])
            threshold = self.config.get('detection', {}).get('dns_spoofing_threshold', 3)
            
            if ip_count > threshold:
                self.log_network_event(
                    event_type="dns_anomaly",
                    severity="high",
                    description=f"DNS spoofing suspected for domain {domain}",
                    source_ip=source_ip,
                    details={
                        "domain": domain,
                        "resolved_ips": list(self.dns_cache[domain]),
                        "ip_count": ip_count
                    }
                )
            
            # Проверяем резолюцию публичных доменов в приватные IP
            if self.config.get('detection', {}).get('private_ip_resolution_alert', True):
                try:
                    ip_obj = ipaddress.ip_address(resolved_ip)
                    if ip_obj.is_private and not domain.endswith('.local'):
                        self.log_network_event(
                            event_type="private_ip_resolution",
                            severity="medium",
                            description=f"Public domain {domain} resolves to private IP",
                            source_ip=source_ip,
                            dest_ip=resolved_ip,
                            details={
                                "domain": domain,
                                "resolved_ip": resolved_ip
                            }
                        )
                except ValueError:
                    pass
            
            # Сохраняем в БД
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT INTO dns_events
                        (domain, resolved_ip, query_type, source_ip, timestamp, is_suspicious)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        domain,
                        resolved_ip,
                        "A",
                        source_ip,
                        datetime.now().isoformat(),
                        ip_count > threshold
                    ))
                    conn.commit()
                    
            except Exception as e:
                logger.debug(f"Ошибка сохранения DNS события: {e}")
                
        except Exception as e:
            logger.error(f"Ошибка анализа DNS резолюции: {e}")
    
    def analyze_tls_handshake(self, packet):
        """Анализ TLS handshake на предмет аномалий"""
        try:
            if packet.haslayer(TCP) and packet[TCP].dport in [443, 8443]:
                # Это может быть HTTPS трафик
                dest_ip = packet[IP].dst
                source_ip = packet[IP].src
                
                # Проверяем географическое расположение (если включено)
                if self.geoip_reader:
                    try:
                        response = self.geoip_reader.country(dest_ip)
                        country_code = response.country.iso_code
                        
                        suspicious_countries = self.config.get('detection', {}).get('suspicious_country_codes', [])
                        if country_code in suspicious_countries:
                            self.log_network_event(
                                event_type="suspicious_geo_connection",
                                severity="medium",
                                description=f"Connection to suspicious country: {country_code}",
                                source_ip=source_ip,
                                dest_ip=dest_ip,
                                protocol="TCP/HTTPS",
                                details={
                                    "country_code": country_code,
                                    "port": packet[TCP].dport
                                }
                            )
                    except geoip2.errors.AddressNotFoundError:
                        pass
                    except Exception as e:
                        logger.debug(f"GeoIP lookup error: {e}")
                
        except Exception as e:
            logger.debug(f"Ошибка анализа TLS handshake: {e}")
    
    def packet_callback(self, packet):
        """Callback для обработки пакетов"""
        try:
            self.packet_stats['total'] += 1
            
            # DNS анализ
            if packet.haslayer(DNS):
                self.packet_stats['dns'] += 1
                self.analyze_dns_response(packet)
            
            # TCP анализ
            if packet.haslayer(TCP):
                self.packet_stats['tcp'] += 1
                self.analyze_tls_handshake(packet)
            
            # HTTP анализ
            if packet.haslayer(HTTP):
                self.packet_stats['http'] += 1
                # Можно добавить анализ HTTP трафика
            
            # Статистика по 1000 пакетов
            if self.packet_stats['total'] % 1000 == 0:
                logger.info(f"Проанализировано {self.packet_stats['total']} пакетов")
                
        except Exception as e:
            logger.debug(f"Ошибка в packet_callback: {e}")
    
    def start_packet_capture(self):
        """Запуск захвата пакетов"""
        if not self.config.get('monitoring', {}).get('packet_capture', True):
            return
        
        try:
            interface = self.config.get('monitoring', {}).get('interface', 'any')
            
            logger.info(f"Запуск захвата пакетов на интерфейсе: {interface}")
            
            # Фильтр для интересующего трафика
            packet_filter = "tcp port 443 or tcp port 80 or udp port 53"
            
            scapy.sniff(
                iface=interface,
                prn=self.packet_callback,
                filter=packet_filter,
                store=0,  # Не сохраняем пакеты в памяти
                stop_filter=lambda x: not self.monitoring_active
            )
            
        except Exception as e:
            logger.error(f"Ошибка захвата пакетов: {e}")
            # В случае ошибки продолжаем работать без захвата пакетов
    
    def monitor_active_connections(self):
        """Мониторинг активных сетевых соединений"""
        try:
            # Получаем список активных соединений
            if os.name == 'nt':  # Windows
                cmd = ['netstat', '-an']
            else:  # Unix-like
                cmd = ['netstat', '-tn']
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                connections = self.parse_netstat_output(result.stdout)
                self.analyze_connections(connections)
            
        except Exception as e:
            logger.error(f"Ошибка мониторинга соединений: {e}")
    
    def parse_netstat_output(self, output: str) -> List[Dict[str, str]]:
        """Парсинг вывода netstat"""
        connections = []
        
        for line in output.split('\n'):
            if 'ESTABLISHED' in line:
                parts = line.split()
                if len(parts) >= 4:
                    local_addr = parts[3]
                    foreign_addr = parts[4]
                    
                    # Извлекаем IP и порт
                    if ':' in foreign_addr:
                        foreign_ip = foreign_addr.rsplit(':', 1)[0]
                        foreign_port = foreign_addr.rsplit(':', 1)[1]
                        
                        connections.append({
                            'local_addr': local_addr,
                            'foreign_ip': foreign_ip,
                            'foreign_port': foreign_port,
                            'state': 'ESTABLISHED'
                        })
        
        return connections
    
    def analyze_connections(self, connections: List[Dict[str, str]]):
        """Анализ активных соединений"""
        for conn in connections:
            foreign_ip = conn['foreign_ip']
            
            # Проверяем на подозрительные IP
            if foreign_ip in self.suspicious_ips:
                self.log_network_event(
                    event_type="suspicious_connection",
                    severity="high",
                    description=f"Connection to suspicious IP {foreign_ip}",
                    dest_ip=foreign_ip,
                    protocol="TCP",
                    details=conn
                )
    
    def start_monitoring(self):
        """Запуск мониторинга сетевой безопасности"""
        if not self.config.get('monitoring', {}).get('enabled', True):
            logger.info("Мониторинг сетевой безопасности отключен")
            return
        
        logger.info("Запуск мониторинга сетевой безопасности")
        self.monitoring_active = True
        
        # Запускаем захват пакетов в отдельном потоке
        if self.config.get('monitoring', {}).get('packet_capture', True):
            packet_thread = threading.Thread(target=self.start_packet_capture)
            packet_thread.daemon = True
            packet_thread.start()
        
        # Основной цикл мониторинга
        while self.monitoring_active:
            try:
                # Мониторим активные соединения
                self.monitor_active_connections()
                
                # Очистка старых данных
                self.cleanup_old_data()
                
                time.sleep(60)  # Проверяем каждую минуту
                
            except KeyboardInterrupt:
                logger.info("Получен сигнал завершения мониторинга")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                time.sleep(10)
        
        self.stop_monitoring()
    
    def stop_monitoring(self):
        """Остановка мониторинга"""
        logger.info("Остановка мониторинга сетевой безопасности")
        self.monitoring_active = False
    
    def cleanup_old_data(self):
        """Очистка старых данных"""
        try:
            retention_days = self.config.get('database', {}).get('retention_days', 30)
            cutoff_date = (datetime.now() - timedelta(days=retention_days)).isoformat()
            
            with sqlite3.connect(self.db_path) as conn:
                # Очищаем старые события
                cursor = conn.execute("""
                    DELETE FROM network_events WHERE timestamp < ?
                """, (cutoff_date,))
                deleted_events = cursor.rowcount
                
                cursor = conn.execute("""
                    DELETE FROM certificate_changes WHERE timestamp < ?
                """, (cutoff_date,))
                deleted_certs = cursor.rowcount
                
                cursor = conn.execute("""
                    DELETE FROM dns_events WHERE timestamp < ?
                """, (cutoff_date,))
                deleted_dns = cursor.rowcount
                
                conn.commit()
                
                if deleted_events > 0 or deleted_certs > 0 or deleted_dns > 0:
                    logger.info(f"Очищено: {deleted_events} событий, {deleted_certs} смен сертификатов, {deleted_dns} DNS событий")
                
        except Exception as e:
            logger.error(f"Ошибка очистки старых данных: {e}")
    
    def get_security_stats(self) -> Dict[str, Any]:
        """Получение статистики сетевой безопасности"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                stats = {}
                
                # Общая статистика событий
                cursor = conn.execute("SELECT COUNT(*) FROM network_events")
                stats['total_network_events'] = cursor.fetchone()[0]
                
                # События за последний час
                hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM network_events WHERE timestamp > ?
                """, (hour_ago,))
                stats['events_last_hour'] = cursor.fetchone()[0]
                
                # События по типам
                cursor = conn.execute("""
                    SELECT event_type, COUNT(*) 
                    FROM network_events 
                    WHERE timestamp > datetime('now', '-24 hours')
                    GROUP BY event_type
                """)
                stats['events_by_type_24h'] = dict(cursor.fetchall())
                
                # Смены сертификатов
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM certificate_changes 
                    WHERE timestamp > datetime('now', '-24 hours')
                """)
                stats['cert_changes_24h'] = cursor.fetchone()[0]
                
                # Подозрительные смены сертификатов
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM certificate_changes 
                    WHERE is_suspicious = 1 AND timestamp > datetime('now', '-24 hours')
                """)
                stats['suspicious_cert_changes_24h'] = cursor.fetchone()[0]
                
                # DNS аномалии
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM dns_events 
                    WHERE is_suspicious = 1 AND timestamp > datetime('now', '-24 hours')
                """)
                stats['suspicious_dns_events_24h'] = cursor.fetchone()[0]
                
                # Статистика пакетов
                stats['packet_stats'] = dict(self.packet_stats)
                
                stats['timestamp'] = datetime.now().isoformat()
                
                return stats
                
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {}

# Глобальный экземпляр монитора
_network_monitor: Optional[NetworkSecurityMonitor] = None

def get_network_monitor() -> NetworkSecurityMonitor:
    """Получение глобального экземпляра сетевого монитора"""
    global _network_monitor
    if not _network_monitor:
        _network_monitor = NetworkSecurityMonitor()
    return _network_monitor

def main():
    """Главная функция для запуска сетевого монитора"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Network Security Monitor для CUBE_RS")
    parser.add_argument('--config', help='Путь к конфигурационному файлу')
    parser.add_argument('--daemon', action='store_true', help='Запуск в режиме демона')
    parser.add_argument('--stats', action='store_true', help='Показать статистику')
    parser.add_argument('--interface', help='Сетевой интерфейс для мониторинга')
    parser.add_argument('--no-packet-capture', action='store_true', help='Отключить захват пакетов')
    
    args = parser.parse_args()
    
    # Загружаем конфигурацию
    config = None
    if args.config and os.path.exists(args.config):
        with open(args.config, 'r', encoding='utf-8') as f:
            config = json.load(f)
    
    # Применяем аргументы командной строки
    if not config:
        config = {}
    
    if args.interface:
        config.setdefault('monitoring', {})['interface'] = args.interface
    
    if args.no_packet_capture:
        config.setdefault('monitoring', {})['packet_capture'] = False
    
    monitor = NetworkSecurityMonitor(config=config)
    
    if args.stats:
        stats = monitor.get_security_stats()
        print("📊 Статистика сетевой безопасности:")
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return
    
    if args.daemon:
        try:
            monitor.start_monitoring()
        except KeyboardInterrupt:
            logger.info("Получен сигнал завершения")
        finally:
            monitor.stop_monitoring()
    else:
        print("🔒 Network Security Monitor")
        print("Используйте --daemon для запуска мониторинга")
        print("Используйте --stats для просмотра статистики")

if __name__ == "__main__":
    main()