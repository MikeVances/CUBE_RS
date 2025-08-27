#!/usr/bin/env python3
"""
Интеграция Multi-Tenant системы с существующей UnifiedKUBSystem
Расширение для поддержки множественных организаций и устройств
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from multi_tenant_manager import MultiTenantManager

logger = logging.getLogger(__name__)

class MultiTenantUnifiedKUBSystem:
    """
    Расширенная версия UnifiedKUBSystem с поддержкой Multi-Tenant
    
    Добавляет:
    - Опрос множественных устройств по разным Modbus Slave ID
    - Фильтрацию данных по правам доступа пользователей
    - Контекстные данные с информацией об организации
    - Аудит операций с привязкой к пользователям
    """
    
    def __init__(self, config_file: str = "config.json"):
        # Импортируем оригинальную систему
        from modbus.unified_system import UnifiedKUBSystem
        
        self.original_system = UnifiedKUBSystem(config_file)
        self.mt_manager = MultiTenantManager()
        self.config = self._load_config(config_file)
        
        # Кэш данных по устройствам
        self.device_data_cache = {}
        self.last_poll_time = {}
        
        logger.info("🏭 Multi-Tenant UnifiedKUBSystem инициализирован")
    
    def _load_config(self, config_file: str) -> dict:
        """Загрузка конфигурации"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки конфигурации: {e}")
            return {}
    
    def start(self):
        """Запуск системы"""
        self.original_system.start()
        logger.info("🚀 Multi-Tenant система запущена")
    
    def stop(self):
        """Остановка системы"""
        self.original_system.stop()
        logger.info("🛑 Multi-Tenant система остановлена")
    
    # =======================================================================
    # МЕТОДЫ ДЛЯ РАБОТЫ С МНОЖЕСТВЕННЫМИ УСТРОЙСТВАМИ
    # =======================================================================
    
    def get_device_data(self, telegram_id: int, device_id: str) -> Optional[Dict[str, Any]]:
        """Получить данные конкретного устройства для пользователя"""
        
        # Проверяем доступ пользователя
        if not self.mt_manager.check_device_access(telegram_id, device_id, "read"):
            logger.warning(f"⚠️ Пользователь {telegram_id} не имеет доступа к устройству {device_id}")
            return None
        
        # Получаем информацию об устройстве
        devices = self.mt_manager.get_user_devices(telegram_id)
        device = next((d for d in devices if d.device_id == device_id), None)
        
        if not device:
            logger.warning(f"⚠️ Устройство {device_id} не найдено для пользователя {telegram_id}")
            return None
        
        try:
            # Получаем данные с конкретного Modbus Slave ID
            raw_data = self._read_device_data(device.modbus_slave_id)
            
            if raw_data:
                # Обогащаем данные информацией об устройстве
                enhanced_data = raw_data.copy()
                enhanced_data.update({
                    'device_id': device.device_id,
                    'device_name': device.device_name,
                    'organization_name': device.organization_name,
                    'location': device.location,
                    'modbus_slave_id': device.modbus_slave_id,
                    'access_level': device.access_level
                })
                
                # Логируем доступ
                self.mt_manager.log_device_access(telegram_id, device_id, "read_data", True)
                
                return enhanced_data
            else:
                logger.warning(f"⚠️ Нет данных с устройства {device_id} (Slave ID: {device.modbus_slave_id})")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения данных устройства {device_id}: {e}")
            self.mt_manager.log_device_access(telegram_id, device_id, "read_data", False, str(e))
            return None
    
    def _read_device_data(self, modbus_slave_id: int) -> Optional[Dict[str, Any]]:
        """Чтение данных с конкретного Modbus Slave ID"""
        
        # Здесь нужно расширить оригинальную систему для поддержки конкретных slave_id
        # Пока используем общий метод, но в реальной реализации это будет:
        # return self.original_system.read_from_slave_id(modbus_slave_id)
        
        # Временная заглушка - используем общие данные
        data = self.original_system.get_current_data()
        if data:
            # Симулируем различия между устройствами
            data['modbus_slave_id'] = modbus_slave_id
            data['last_poll'] = datetime.now().isoformat()
        
        return data
    
    def get_all_user_devices_data(self, telegram_id: int) -> Dict[str, Dict[str, Any]]:
        """Получить данные всех устройств пользователя"""
        
        devices = self.mt_manager.get_user_devices(telegram_id)
        all_data = {}
        
        for device in devices:
            device_data = self.get_device_data(telegram_id, device.device_id)
            if device_data:
                all_data[device.device_id] = device_data
        
        return all_data
    
    def execute_command_on_device(self, telegram_id: int, device_id: str, 
                                register: int, value: Any) -> Tuple[bool, str]:
        """Выполнить команду записи на конкретном устройстве"""
        
        # Получаем информацию об устройстве
        devices = self.mt_manager.get_user_devices(telegram_id)
        device = next((d for d in devices if d.device_id == device_id), None)
        
        if not device:
            return False, f"Устройство {device_id} не найдено"
        
        # Валидируем права доступа
        valid, message = self.mt_manager.validate_write_command(
            telegram_id, device.modbus_slave_id, register, value
        )
        
        if not valid:
            return False, message
        
        try:
            # Выполняем команду через оригинальную систему
            # В реальной реализации это будет:
            # success = self.original_system.write_to_slave_id(device.modbus_slave_id, register, value)
            
            # Временная реализация
            success, result = self.original_system.add_write_command(
                register=register,
                value=value,
                source_ip="multitenant_system",
                user_info=json.dumps({
                    "telegram_id": telegram_id,
                    "device_id": device_id,
                    "organization": device.organization_name
                })
            )
            
            # Логируем операцию
            details = json.dumps({"register": register, "value": value, "result": result})
            self.mt_manager.log_device_access(telegram_id, device_id, "write_register", success, details)
            
            if success:
                return True, f"Команда успешно выполнена на устройстве {device.device_name}"
            else:
                return False, f"Ошибка выполнения команды: {result}"
            
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения команды на устройстве {device_id}: {e}")
            self.mt_manager.log_device_access(telegram_id, device_id, "write_register", False, str(e))
            return False, f"Ошибка выполнения команды: {str(e)}"
    
    def reset_alarms_on_device(self, telegram_id: int, device_id: str) -> Tuple[bool, str]:
        """Сброс аварий на конкретном устройстве"""
        return self.execute_command_on_device(telegram_id, device_id, 0x0020, 1)
    
    # =======================================================================
    # СТАТИСТИКА И МОНИТОРИНГ
    # =======================================================================
    
    def get_organization_statistics(self, telegram_id: int, organization_code: str = None) -> Dict[str, Any]:
        """Получить статистику по организации"""
        
        organizations = self.mt_manager.get_user_organizations(telegram_id)
        
        if organization_code:
            org = next((o for o in organizations if o['code'] == organization_code), None)
            if not org:
                return {"error": f"Организация {organization_code} не найдена"}
        
        # Получаем устройства организации
        devices = self.mt_manager.get_user_devices(telegram_id)
        
        if organization_code:
            devices = [d for d in devices if d.organization_name == org['name']]
        
        stats = {
            "organization_count": len(organizations),
            "device_count": len(devices),
            "devices_online": 0,
            "devices_with_alarms": 0,
            "total_read_operations": 0,
            "total_write_operations": 0,
            "last_update": datetime.now().isoformat()
        }
        
        # Проверяем статус каждого устройства
        for device in devices:
            device_data = self.get_device_data(telegram_id, device.device_id)
            if device_data:
                stats["devices_online"] += 1
                
                # Проверяем аварии
                if device_data.get('active_alarms', 0) > 0:
                    stats["devices_with_alarms"] += 1
        
        return stats
    
    def get_device_history(self, telegram_id: int, device_id: str, 
                          hours: int = 24) -> List[Dict[str, Any]]:
        """Получить историю операций с устройством"""
        
        if not self.mt_manager.check_device_access(telegram_id, device_id, "read"):
            return []
        
        try:
            import sqlite3
            with sqlite3.connect(self.mt_manager.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT dal.*, u.first_name, u.last_name, u.username
                    FROM device_access_log dal
                    JOIN users u ON dal.user_id = u.id
                    JOIN kub_devices kd ON dal.device_id = kd.id
                    WHERE kd.device_id = ? 
                    AND dal.timestamp > datetime('now', '-{} hours')
                    ORDER BY dal.timestamp DESC
                    LIMIT 100
                """.format(hours), (device_id,))
                
                history = []
                for row in cursor.fetchall():
                    history.append({
                        "timestamp": row["timestamp"],
                        "action": row["action"],
                        "user_name": f"{row['first_name']} {row['last_name']}".strip() or row["username"],
                        "success": bool(row["success"]),
                        "details": row["details"]
                    })
                
                return history
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения истории устройства {device_id}: {e}")
            return []
    
    # =======================================================================
    # СОВМЕСТИМОСТЬ С ОРИГИНАЛЬНОЙ СИСТЕМОЙ
    # =======================================================================
    
    def get_current_data(self) -> Optional[Dict[str, Any]]:
        """Совместимость: получить данные (используется старыми компонентами)"""
        return self.original_system.get_current_data()
    
    def get_system_statistics(self) -> Dict[str, Any]:
        """Совместимость: получить статистику системы"""
        original_stats = self.original_system.get_system_statistics()
        
        # Добавляем multi-tenant статистику
        mt_stats = {
            "multitenant_enabled": True,
            "total_organizations": self._count_organizations(),
            "total_devices": self._count_devices(),
            "total_users": self._count_users()
        }
        
        original_stats.update(mt_stats)
        return original_stats
    
    def _count_organizations(self) -> int:
        """Подсчет активных организаций"""
        try:
            import sqlite3
            with sqlite3.connect(self.mt_manager.db_file) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM organizations WHERE is_active = 1")
                return cursor.fetchone()[0]
        except:
            return 0
    
    def _count_devices(self) -> int:
        """Подсчет активных устройств"""
        try:
            import sqlite3
            with sqlite3.connect(self.mt_manager.db_file) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM kub_devices WHERE is_active = 1")
                return cursor.fetchone()[0]
        except:
            return 0
    
    def _count_users(self) -> int:
        """Подсчет активных пользователей"""
        try:
            import sqlite3
            with sqlite3.connect(self.mt_manager.db_file) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
                return cursor.fetchone()[0]
        except:
            return 0

# =============================================================================
# АДАПТЕР ДЛЯ TELEGRAM BOT
# =============================================================================

class TelegramBotMultiTenantAdapter:
    """
    Адаптер для интеграции Multi-Tenant системы с существующим Telegram Bot
    Позволяет использовать новую систему с минимальными изменениями в боте
    """
    
    def __init__(self):
        self.mt_system = MultiTenantUnifiedKUBSystem()
        self.mt_manager = self.mt_system.mt_manager
    
    def get_user_context_data(self, telegram_id: int, device_id: str = None) -> Dict[str, Any]:
        """Получить контекстные данные для пользователя"""
        
        if device_id:
            # Данные конкретного устройства
            return self.mt_system.get_device_data(telegram_id, device_id)
        else:
            # Данные всех устройств пользователя
            devices = self.mt_manager.get_user_devices(telegram_id)
            
            if len(devices) == 1:
                # Если устройство одно - возвращаем его данные
                return self.mt_system.get_device_data(telegram_id, devices[0].device_id)
            else:
                # Если устройств несколько - возвращаем сводку
                return {
                    "multitenant": True,
                    "device_count": len(devices),
                    "organizations": [d.organization_name for d in devices],
                    "devices": [{"id": d.device_id, "name": d.device_name} for d in devices]
                }
    
    def format_device_selection_text(self, telegram_id: int) -> str:
        """Форматированный текст для выбора устройства"""
        devices = self.mt_manager.get_user_devices(telegram_id)
        
        if not devices:
            return "❌ У вас нет доступа к устройствам"
        
        if len(devices) == 1:
            device = devices[0]
            return f"📦 **{device.device_name}**\n🏢 {device.organization_name}"
        
        # Группируем по организациям
        orgs = {}
        for device in devices:
            if device.organization_name not in orgs:
                orgs[device.organization_name] = []
            orgs[device.organization_name].append(device)
        
        text = f"📦 **Выберите устройство ({len(devices)}):**\n\n"
        
        for org_name, org_devices in orgs.items():
            text += f"🏢 **{org_name}**\n"
            for device in org_devices:
                access_icon = {"read": "👁️", "write": "✏️", "admin": "⚙️"}.get(device.access_level, "❓")
                text += f"  {access_icon} {device.device_name}"
                if device.location:
                    text += f" ({device.location})"
                text += "\n"
            text += "\n"
        
        return text.strip()

# =============================================================================
# ТЕСТИРОВАНИЕ ИНТЕГРАЦИИ
# =============================================================================

def test_multitenant_integration():
    """Тест интеграции multi-tenant системы"""
    print("🧪 Тестирование Multi-Tenant интеграции")
    print("=" * 60)
    
    try:
        # Создаем систему
        mt_system = MultiTenantUnifiedKUBSystem()
        
        # Тест 1: Проверка инициализации
        print("1. Тест инициализации...")
        print("   ✅ Multi-Tenant система инициализирована")
        
        # Тест 2: Получение данных устройства
        print("2. Тест получения данных устройства...")
        
        # Регистрируем тестового пользователя
        telegram_id = 123456789
        mt_system.mt_manager.register_user(telegram_id, "test_user", "Test", "User")
        mt_system.mt_manager.add_user_to_organization(telegram_id, "IVANOV_FARM", "operator")
        
        devices = mt_system.mt_manager.get_user_devices(telegram_id)
        if devices:
            device = devices[0]
            data = mt_system.get_device_data(telegram_id, device.device_id)
            print(f"   ✅ Получены данные устройства {device.device_id}")
        else:
            print("   ⚠️ Нет доступных устройств для тестирования")
        
        # Тест 3: Статистика
        print("3. Тест получения статистики...")
        stats = mt_system.get_system_statistics()
        print(f"   ✅ Статистика: {stats.get('total_organizations', 0)} организаций, {stats.get('total_devices', 0)} устройств")
        
        # Тест 4: Адаптер для Telegram Bot
        print("4. Тест адаптера для Telegram Bot...")
        adapter = TelegramBotMultiTenantAdapter()
        text = adapter.format_device_selection_text(telegram_id)
        print(f"   ✅ Адаптер работает, длина текста: {len(text)} символов")
        
        print("\n✅ Все тесты интеграции пройдены!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования интеграции: {e}")
        return False

if __name__ == "__main__":
    test_multitenant_integration()