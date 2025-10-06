#!/usr/bin/env python3
"""
Prometheus метрики для EDGE узла
Простая система мониторинга без внешних зависимостей
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class SimpleMetrics:
    """Простая система метрик для PET проекта"""
    
    def __init__(self, metrics_file: str = "/var/lib/cube_edge/metrics.json"):
        self.metrics_file = Path(metrics_file)
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
        self.metrics: Dict = {}
        self.load_metrics()
        
    def load_metrics(self):
        """Загрузка метрик из файла"""
        try:
            if self.metrics_file.exists():
                with open(self.metrics_file) as f:
                    self.metrics = json.load(f)
            else:
                self.metrics = {
                    "system": {},
                    "edge": {},
                    "devices": {},
                    "alerts": [],
                    "last_update": time.time()
                }
        except Exception as e:
            logger.error(f"Ошибка загрузки метрик: {e}")
            self.metrics = {}
    
    def save_metrics(self):
        """Сохранение метрик в файл"""
        try:
            self.metrics["last_update"] = time.time()
            with open(self.metrics_file, 'w') as f:
                json.dump(self.metrics, f, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения метрик: {e}")
    
    def set_metric(self, category: str, name: str, value, labels: Dict = None):
        """Установка значения метрики"""
        if category not in self.metrics:
            self.metrics[category] = {}
        
        metric_data = {
            "value": value,
            "timestamp": time.time(),
            "labels": labels or {}
        }
        
        self.metrics[category][name] = metric_data
        self.save_metrics()
    
    def get_metric(self, category: str, name: str):
        """Получение значения метрики"""
        return self.metrics.get(category, {}).get(name)
    
    def increment_counter(self, category: str, name: str, labels: Dict = None):
        """Увеличение счетчика на 1"""
        current = self.get_metric(category, name)
        current_value = current.get("value", 0) if current else 0
        self.set_metric(category, name, current_value + 1, labels)
    
    def add_alert(self, level: str, message: str, source: str):
        """Добавление алерта"""
        alert = {
            "level": level,
            "message": message,
            "source": source,
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat()
        }
        
        if "alerts" not in self.metrics:
            self.metrics["alerts"] = []
        
        self.metrics["alerts"].append(alert)
        
        # Оставляем только последние 100 алертов
        self.metrics["alerts"] = self.metrics["alerts"][-100:]
        self.save_metrics()
        
        logger.info(f"Alert [{level}] {source}: {message}")
    
    def get_alerts(self, hours: int = 24) -> List[Dict]:
        """Получение алертов за последние N часов"""
        cutoff_time = time.time() - (hours * 3600)
        alerts = self.metrics.get("alerts", [])
        return [alert for alert in alerts if alert["timestamp"] > cutoff_time]
    
    def cleanup_old_data(self, days: int = 7):
        """Очистка старых данных"""
        cutoff_time = time.time() - (days * 24 * 3600)
        
        # Очищаем старые алерты
        alerts = self.metrics.get("alerts", [])
        self.metrics["alerts"] = [
            alert for alert in alerts 
            if alert["timestamp"] > cutoff_time
        ]
        
        self.save_metrics()

class EDGEMonitoring:
    """Система мониторинга EDGE узла"""
    
    def __init__(self, config=None):
        self.config = config
        self.metrics = SimpleMetrics()
        self.thresholds = self._load_thresholds()
        
    def _load_thresholds(self) -> Dict:
        """Загрузка пороговых значений"""
        default_thresholds = {
            "cpu_percent": 80,
            "memory_percent": 85,
            "disk_percent": 90,
            "temperature_min": -10,
            "temperature_max": 40,
            "humidity_max": 95,
            "co2_max": 5000,
            "response_time_ms": 5000,
            "error_rate_percent": 10
        }
        
        if self.config and hasattr(self.config, "monitoring"):
            monitoring_config = getattr(self.config.monitoring, "alert_thresholds", {})
            default_thresholds.update(monitoring_config)
        
        return default_thresholds
    
    def record_system_metrics(self, cpu_percent: float, memory_percent: float, 
                            disk_percent: float, uptime: float):
        """Запись системных метрик"""
        self.metrics.set_metric("system", "cpu_percent", cpu_percent)
        self.metrics.set_metric("system", "memory_percent", memory_percent)
        self.metrics.set_metric("system", "disk_percent", disk_percent)
        self.metrics.set_metric("system", "uptime", uptime)
        
        # Проверка пороговых значений
        if cpu_percent > self.thresholds["cpu_percent"]:
            self.metrics.add_alert("WARNING", 
                f"Высокая загрузка CPU: {cpu_percent:.1f}%", "system")
        
        if memory_percent > self.thresholds["memory_percent"]:
            self.metrics.add_alert("WARNING", 
                f"Высокое использование памяти: {memory_percent:.1f}%", "system")
        
        if disk_percent > self.thresholds["disk_percent"]:
            self.metrics.add_alert("CRITICAL", 
                f"Заканчивается место на диске: {disk_percent:.1f}%", "system")
    
    def record_device_metrics(self, device_id: str, temperature: Optional[float] = None,
                            humidity: Optional[float] = None, co2: Optional[int] = None,
                            response_time_ms: Optional[float] = None, 
                            connection_status: str = "unknown"):
        """Запись метрик устройства"""
        labels = {"device_id": device_id}
        
        if temperature is not None:
            self.metrics.set_metric("devices", f"{device_id}_temperature", temperature, labels)
            
            if temperature < self.thresholds["temperature_min"]:
                self.metrics.add_alert("WARNING", 
                    f"Низкая температура на {device_id}: {temperature}°C", "device")
            elif temperature > self.thresholds["temperature_max"]:
                self.metrics.add_alert("CRITICAL", 
                    f"Высокая температура на {device_id}: {temperature}°C", "device")
        
        if humidity is not None:
            self.metrics.set_metric("devices", f"{device_id}_humidity", humidity, labels)
            
            if humidity > self.thresholds["humidity_max"]:
                self.metrics.add_alert("WARNING", 
                    f"Высокая влажность на {device_id}: {humidity}%", "device")
        
        if co2 is not None:
            self.metrics.set_metric("devices", f"{device_id}_co2", co2, labels)
            
            if co2 > self.thresholds["co2_max"]:
                self.metrics.add_alert("WARNING", 
                    f"Высокий CO2 на {device_id}: {co2} ppm", "device")
        
        if response_time_ms is not None:
            self.metrics.set_metric("devices", f"{device_id}_response_time", response_time_ms, labels)
            
            if response_time_ms > self.thresholds["response_time_ms"]:
                self.metrics.add_alert("WARNING", 
                    f"Медленный ответ от {device_id}: {response_time_ms}ms", "device")
        
        self.metrics.set_metric("devices", f"{device_id}_status", connection_status, labels)
        
        if connection_status == "disconnected":
            self.metrics.add_alert("CRITICAL", 
                f"Устройство {device_id} отключено", "device")
    
    def record_edge_metrics(self, service_name: str, status: str, 
                          error_count: int = 0, last_error: str = None):
        """Запись метрик EDGE сервисов"""
        labels = {"service": service_name}
        
        self.metrics.set_metric("edge", f"{service_name}_status", status, labels)
        self.metrics.set_metric("edge", f"{service_name}_errors", error_count, labels)
        
        if status == "failed":
            self.metrics.add_alert("CRITICAL", 
                f"Сервис {service_name} упал", "edge")
        
        if last_error:
            self.metrics.add_alert("ERROR", 
                f"Ошибка в {service_name}: {last_error}", "edge")
    
    def get_dashboard_data(self) -> Dict:
        """Данные для дашборда"""
        recent_alerts = self.get_recent_alerts(hours=24)
        
        dashboard = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_alerts_24h": len(recent_alerts),
                "critical_alerts": len([a for a in recent_alerts if a["level"] == "CRITICAL"]),
                "warning_alerts": len([a for a in recent_alerts if a["level"] == "WARNING"]),
                "system_status": self._get_overall_status(),
            },
            "system_metrics": self.metrics.metrics.get("system", {}),
            "device_metrics": self.metrics.metrics.get("devices", {}),
            "edge_metrics": self.metrics.metrics.get("edge", {}),
            "recent_alerts": recent_alerts[-10:],  # Последние 10 алертов
        }
        
        return dashboard
    
    def _get_overall_status(self) -> str:
        """Определение общего статуса системы"""
        recent_alerts = self.get_recent_alerts(hours=1)
        
        critical_alerts = [a for a in recent_alerts if a["level"] == "CRITICAL"]
        if critical_alerts:
            return "CRITICAL"
        
        warning_alerts = [a for a in recent_alerts if a["level"] == "WARNING"]
        if warning_alerts:
            return "WARNING"
        
        return "OK"
    
    def get_recent_alerts(self, hours: int = 24) -> List[Dict]:
        """Получение недавних алертов"""
        return self.metrics.get_alerts(hours)
    
    def export_prometheus_format(self) -> str:
        """Экспорт в формате Prometheus (простой)"""
        lines = []
        timestamp = int(time.time() * 1000)
        
        # Системные метрики
        system_metrics = self.metrics.metrics.get("system", {})
        for metric_name, metric_data in system_metrics.items():
            if isinstance(metric_data.get("value"), (int, float)):
                lines.append(f'cube_edge_system_{metric_name} {metric_data["value"]} {timestamp}')
        
        # Метрики устройств
        device_metrics = self.metrics.metrics.get("devices", {})
        for metric_name, metric_data in device_metrics.items():
            if isinstance(metric_data.get("value"), (int, float)):
                labels = metric_data.get("labels", {})
                label_str = ",".join([f'{k}="{v}"' for k, v in labels.items()])
                lines.append(f'cube_edge_device_{metric_name}{{{label_str}}} {metric_data["value"]} {timestamp}')
        
        # Алерты
        recent_alerts = self.get_recent_alerts(hours=1)
        lines.append(f'cube_edge_alerts_total {len(recent_alerts)} {timestamp}')
        
        return "\n".join(lines) + "\n"

# Глобальный экземпляр мониторинга
_monitoring = None

def get_monitoring(config=None) -> EDGEMonitoring:
    """Получение глобального экземпляра мониторинга"""
    global _monitoring
    if _monitoring is None:
        _monitoring = EDGEMonitoring(config)
    return _monitoring

def record_system_health(cpu_percent: float, memory_percent: float, 
                        disk_percent: float, uptime: float):
    """Shortcut для записи системных метрик"""
    get_monitoring().record_system_metrics(cpu_percent, memory_percent, disk_percent, uptime)

def record_device_data(device_id: str, **kwargs):
    """Shortcut для записи данных устройства"""
    get_monitoring().record_device_metrics(device_id, **kwargs)

def add_alert(level: str, message: str, source: str):
    """Shortcut для добавления алерта"""
    get_monitoring().metrics.add_alert(level, message, source)

if __name__ == "__main__":
    # Тестирование системы мониторинга
    monitoring = EDGEMonitoring()
    
    # Тестовые метрики
    monitoring.record_system_metrics(75.5, 60.2, 45.0, 86400)
    monitoring.record_device_metrics("kub-001", temperature=22.5, humidity=65, co2=800)
    monitoring.record_edge_metrics("telegram_bot", "running", error_count=0)
    
    # Тестовые алерты
    monitoring.metrics.add_alert("INFO", "Система запущена", "system")
    monitoring.metrics.add_alert("WARNING", "Высокая загрузка CPU", "system")
    
    print("=== Dashboard Data ===")
    dashboard = monitoring.get_dashboard_data()
    print(json.dumps(dashboard, indent=2, ensure_ascii=False))
    
    print("\n=== Prometheus Format ===")
    print(monitoring.export_prometheus_format())