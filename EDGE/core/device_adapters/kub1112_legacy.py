#!/usr/bin/env python3
"""
Адаптер для КУБ-1112 (блок управления обогревателя)
"""

from typing import Dict, List, Any
from .base import DeviceAdapter, RegisterInfo, DeviceData, ValueType


class KUB1112Adapter(DeviceAdapter):
    """Адаптер для КУБ-1112"""
    
    @property
    def device_type(self) -> str:
        return "KUB-1112"
    
    @property
    def register_map(self) -> Dict[str, RegisterInfo]:
        """Карта регистров КУБ-1112 согласно документации"""
        return {
            # Системная информация
            "software_version": RegisterInfo(0x0301, "software_version", ValueType.VERSION),
            
            # Основные параметры
            "flame_level": RegisterInfo(
                0x0400, "flame_level", ValueType.PERCENTAGE, "%", 0.01, True,
                "Уровень пламени"
            ),
            "flame_present": RegisterInfo(
                0x0401, "flame_present", ValueType.BOOLEAN,
                description="Флаг наличия пламени"
            ),
            
            # Настройки (потенциометры)
            "min_work_time": RegisterInfo(
                0x0402, "min_work_time", ValueType.FLOAT, "с", 0.1, False,
                "Минимальное время работы",
                special_values={0xFFFF: "pending"}
            ),
            "start_delay": RegisterInfo(
                0x0403, "start_delay", ValueType.FLOAT, "с", 0.1, False,
                "Задержка включения",
                special_values={0xFFFF: "pending"}
            ),
            "purge_duration": RegisterInfo(
                0x0404, "purge_duration", ValueType.FLOAT, "с", 0.1, False,
                "Продолжительность продувки",
                special_values={0xFFFF: "pending"}
            ),
            
            # Датчики
            "temperature": RegisterInfo(
                0x0405, "temperature", ValueType.TEMPERATURE, "°C", 0.1, True,
                "Показание датчика температуры",
                special_values={0x8000: "error"}
            ),
            "temp_resistance": RegisterInfo(
                0x0406, "temp_resistance", ValueType.INTEGER, "Ом", 1, False,
                "Сопротивление датчика температуры"
            ),
            
            # Состояние реле (битовое поле)
            "relay_state": RegisterInfo(
                0x0407, "relay_state", ValueType.BITFIELD,
                description="Состояние реле управления"
            ),
            
            # Дискретные входы (битовое поле)
            "discrete_inputs": RegisterInfo(
                0x0408, "discrete_inputs", ValueType.BITFIELD,
                description="Состояние дискретных входов"
            ),
            
            # Режим работы
            "operation_mode": RegisterInfo(
                0x0409, "operation_mode", ValueType.INTEGER,
                description="Режим работы"
            ),
            
            # Зарегистрированные аварии (4 регистра)
            "registered_alarms_0": RegisterInfo(0x0410, "registered_alarms_0", ValueType.BITFIELD),
            "registered_alarms_1": RegisterInfo(0x0411, "registered_alarms_1", ValueType.BITFIELD),
            "registered_alarms_2": RegisterInfo(0x0412, "registered_alarms_2", ValueType.BITFIELD),
            "registered_alarms_3": RegisterInfo(0x0413, "registered_alarms_3", ValueType.BITFIELD),
            
            # Настройки Modbus (Holding Registers - FC=3)
            "modbus_address": RegisterInfo(0x0220, "modbus_address", ValueType.INTEGER),
            "modbus_baudrate": RegisterInfo(0x0221, "modbus_baudrate", ValueType.INTEGER),
        }
    
    def parse_register_value(self, register_name: str, raw_value: int) -> tuple[Any, str]:
        """Парсинг значения регистра КУБ-1112"""
        register_info = self.register_map.get(register_name)
        if not register_info:
            return raw_value, "unknown"
        
        # Проверяем специальные значения
        special_status = self._check_special_values(raw_value, register_info)
        if special_status:
            return special_status, special_status
        
        # Специальная обработка для булевых значений
        if register_info.value_type == ValueType.BOOLEAN:
            return bool(raw_value), "ok"
        
        # Применяем масштаб и знак
        parsed_value = self._apply_scale_and_sign(raw_value, register_info)
        
        return parsed_value, "ok"
    
    def format_for_display(self, data: DeviceData) -> str:
        """Форматирование для отображения"""
        lines = []
        
        # Состояние пламени
        lines.append("🔥 <b>ПЛАМЯ:</b>")
        if "flame_present" in data.registers:
            flame_present = data.registers["flame_present"]
            status_icon = "🟢" if flame_present else "🔴"
            status_text = "ЕСТЬ" if flame_present else "НЕТ"
            lines.append(f"  • Статус: {status_icon} <code>{status_text}</code>")
        
        if "flame_level" in data.registers:
            flame_level = data.registers["flame_level"]
            if isinstance(flame_level, (int, float)):
                lines.append(f"  • Уровень: <code>{flame_level:.2f}%</code>")
        
        # Температура
        lines.append("\n🌡️ <b>ТЕМПЕРАТУРА:</b>")
        if "temperature" in data.registers:
            temp = data.registers["temperature"]
            status = data.status.get("temperature", "ok")
            if status == "ok" and isinstance(temp, (int, float)):
                lines.append(f"  • Датчик: <code>{temp:.1f}°C</code>")
            elif status == "error":
                lines.append("  • Датчик: ❌ <code>Ошибка измерения</code>")
        
        if "temp_resistance" in data.registers:
            resistance = data.registers["temp_resistance"]
            lines.append(f"  • Сопротивление: <code>{resistance} Ом</code>")
        
        # Режим работы
        lines.append("\n⚙️ <b>РЕЖИМ РАБОТЫ:</b>")
        if "operation_mode" in data.registers:
            mode = data.registers["operation_mode"]
            mode_names = {
                0: "Не выбран",
                1: "Авто обогрев + авто вентиляция",
                2: "Непрерывный обогрев", 
                3: "Непрерывная вентиляция",
                4: "Авто обогрев + непрерывная вентиляция"
            }
            mode_name = mode_names.get(mode, f"Режим {mode}")
            lines.append(f"  • Режим: <code>{mode_name}</code>")
        
        # Состояние реле
        lines.append("\n🔌 <b>РЕЛЕ:</b>")
        if "relay_state" in data.registers:
            relay_state = data.registers["relay_state"]
            relay_names = [
                ("Клапан газа", 0),
                ("Розжиг", 1),
                ("Основной вентилятор", 2),
                ("Доп. вентилятор", 3),
                ("Авария", 4)
            ]
            
            for name, bit in relay_names:
                state = "🟢 ВКЛ" if (relay_state & (1 << bit)) else "🔴 ВЫКЛ"
                lines.append(f"  • {name}: {state}")
        
        # Дискретные входы
        lines.append("\n📥 <b>ВХОДЫ:</b>")
        if "discrete_inputs" in data.registers:
            inputs = data.registers["discrete_inputs"]
            input_names = [
                ("Флюгер", 2, "Обдув есть", "Обдува нет"),
                ("Давление газа", 3, "Нормальное", "Низкое"),
                ("Вентиляция", 4, "Запуск", "Останов"),
                ("Нагрев", 5, "Запуск", "Останов")
            ]
            
            for name, bit, on_text, off_text in input_names:
                state = on_text if (inputs & (1 << bit)) else off_text
                icon = "🟢" if (inputs & (1 << bit)) else "🔴"
                lines.append(f"  • {name}: {icon} <code>{state}</code>")
        
        return "\n".join(lines)
    
    def get_critical_alarms(self, data: DeviceData) -> List[str]:
        """Критичные аварии КУБ-1112"""
        alarms = []
        
        # Проверяем аварийные регистры
        alarm_registers = ["registered_alarms_0", "registered_alarms_1", "registered_alarms_2", "registered_alarms_3"]
        for reg_name in alarm_registers:
            if reg_name in data.registers:
                alarm_value = data.registers[reg_name]
                if alarm_value > 0:
                    # Декодируем специфичные аварии
                    critical_bits = self._decode_critical_alarms(reg_name, alarm_value)
                    alarms.extend(critical_bits)
        
        # Проверяем отсутствие пламени в режиме обогрева
        if "flame_present" in data.registers and "operation_mode" in data.registers:
            flame_present = data.registers["flame_present"]
            mode = data.registers["operation_mode"]
            if mode in [1, 2, 4] and not flame_present:  # Режимы с обогревом
                alarms.append("🚨 Нет пламени при включенном обогреве")
        
        # Проверяем температурный датчик
        temp_status = data.status.get("temperature")
        if temp_status == "error":
            alarms.append("❌ Ошибка датчика температуры")
        
        return alarms
    
    def get_warnings(self, data: DeviceData) -> List[str]:
        """Предупреждения КУБ-1112"""
        warnings = []
        
        # Проверяем неготовые измерения
        for reg_name, status in data.status.items():
            if status == "pending":
                warnings.append(f"⏳ {reg_name}: измерение не готово")
        
        # Проверяем низкое давление газа
        if "discrete_inputs" in data.registers:
            inputs = data.registers["discrete_inputs"]
            if not (inputs & (1 << 3)):  # Бит 3 - давление газа
                warnings.append("⚠️ Низкое давление газа")
        
        return warnings
    
    def _decode_critical_alarms(self, register_name: str, alarm_value: int) -> List[str]:
        """Декодирование критичных аварий из битового поля"""
        alarms = []
        
        if register_name == "registered_alarms_0":
            # Младшие 16 бит (биты 0-15)
            alarm_bits = {
                1: "Не обнаружено пламя при запуске",
                2: "Низкое давление / обрыв датчика",
                3: "Пламя погасло",
                4: "Зафиксирован обдув при выключенном вентиляторе",
                5: "Отсутствует обдув камеры сгорания",
                6: "Обрыв датчика температуры",
                7: "Пламя не гаснет",
                8: "Неправильный сигнал пламени"
            }
        elif register_name == "registered_alarms_1":
            # Биты 16-31
            alarm_bits = {
                0: "Продолжительный сигнал сброса аварии",  # бит 16
                1: "Частые попытки сброса аварий",          # бит 17
                11: "Сигнал от STL",                       # бит 27
                12: "Низкое напряжение питания"            # бит 28
            }
        else:
            return alarms
        
        for bit, description in alarm_bits.items():
            if alarm_value & (1 << bit):
                alarms.append(f"🚨 {description}")
        
        return alarms