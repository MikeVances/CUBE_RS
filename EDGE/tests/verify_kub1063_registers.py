#!/usr/bin/env python3
"""
Проверка соответствия регистров КУБ-1063 с документацией
Сравнивает адреса регистров в адаптере с официальной документацией
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.device_adapters.kub1063 import KUB1063Adapter

# Регистры из документации КУБ-1063_modbus_registers.pdf
# Все регистры - INPUT REGISTERS (Function Code 04)
DOCUMENTED_REGISTERS = {
    # Системная информация
    0x0301: {"name": "software_version", "description": "Версия ПО", "type": "version"},
    0x0302: {"name": "factory_number", "description": "Заводской номер (месяц/год)", "type": "integer"},
    0x0303: {"name": "device_number", "description": "Номер устройства", "type": "integer"},

    # Цифровые выходы (битовые поля)
    0x0081: {"name": "digital_outputs_1", "description": "ГНВ базовой/туннельной", "type": "bitfield"},
    0x0082: {"name": "digital_outputs_2", "description": "ГРВ, нагреватели, освещение", "type": "bitfield"},
    0x00A2: {"name": "digital_outputs_3", "description": "Таймеры 1-2", "type": "bitfield"},

    # Основные датчики
    0x0083: {"name": "pressure", "description": "Отрицательное давление", "type": "unsigned", "scale": 0.1, "unit": "Па"},
    0x0084: {"name": "humidity", "description": "Относительная влажность", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x0085: {"name": "co2", "description": "Концентрация CO2", "type": "unsigned", "scale": 1.0, "unit": "ppm"},
    0x0086: {"name": "nh3", "description": "Концентрация NH3", "type": "unsigned", "scale": 0.1, "unit": "ppm"},

    # Управляющие выходы (аналоговые)
    0x0087: {"name": "grv_base", "description": "ГРВ базовой вентиляции", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x0088: {"name": "grv_tunnel", "description": "ГРВ туннельной вентиляции", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x0089: {"name": "damper", "description": "Демпфер", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x008A: {"name": "air_intake_1", "description": "Воздухозаборник 1", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x008B: {"name": "air_intake_2", "description": "Воздухозаборник 2", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x008C: {"name": "air_intake_tunnel", "description": "Туннельный воздухозаборник", "type": "unsigned", "scale": 0.1, "unit": "%"},

    # Температурные датчики
    0x008D: {"name": "temp_inside_1", "description": "Внутренняя температура 1", "type": "signed", "scale": 0.1, "unit": "°C"},
    0x008E: {"name": "temp_inside_2", "description": "Внутренняя температура 2", "type": "signed", "scale": 0.1, "unit": "°C"},
    0x008F: {"name": "temp_outside", "description": "Наружная температура", "type": "signed", "scale": 0.1, "unit": "°C"},
    0x0090: {"name": "temp_inside_3", "description": "Внутренняя температура 3", "type": "signed", "scale": 0.1, "unit": "°C"},
    0x0091: {"name": "temp_inside_4", "description": "Внутренняя температура 4", "type": "signed", "scale": 0.1, "unit": "°C"},

    # Дополнительные воздухозаборники
    0x0092: {"name": "air_intake_3", "description": "Воздухозаборник 3", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x0093: {"name": "air_intake_4", "description": "Воздухозаборник 4", "type": "unsigned", "scale": 0.1, "unit": "%"},

    # Освещение
    0x0094: {"name": "lighting_1", "description": "Управление освещением 1", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x0095: {"name": "lighting_2", "description": "Управление освещением 2", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x0096: {"name": "lighting_3", "description": "Управление освещением 3", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x0097: {"name": "lighting_4", "description": "Управление освещением 4", "type": "unsigned", "scale": 0.1, "unit": "%"},

    # Таймеры
    0x0098: {"name": "timer_1_output_1", "description": "Таймер 1, выход 1", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x0099: {"name": "timer_1_output_2", "description": "Таймер 1, выход 2", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x009A: {"name": "timer_1_output_3", "description": "Таймер 1, выход 3", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x009B: {"name": "timer_1_output_4", "description": "Таймер 1, выход 4", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x009C: {"name": "timer_2_output_1", "description": "Таймер 2, выход 1", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x009D: {"name": "timer_2_output_2", "description": "Таймер 2, выход 2", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x009E: {"name": "timer_2_output_3", "description": "Таймер 2, выход 3", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x009F: {"name": "timer_2_output_4", "description": "Таймер 2, выход 4", "type": "unsigned", "scale": 0.1, "unit": "%"},

    # Аварии и предупреждения
    0x00C0: {"name": "active_alarms_0", "description": "Активные аварии (часть 1)", "type": "bitfield"},
    0x00C1: {"name": "active_alarms_1", "description": "Активные аварии (часть 2)", "type": "bitfield"},
    0x00C2: {"name": "active_alarms_2", "description": "Активные аварии (часть 3)", "type": "bitfield"},
    0x00C3: {"name": "active_alarms_3", "description": "Активные аварии (часть 4)", "type": "bitfield"},

    0x00C4: {"name": "registered_alarms_0", "description": "Зарегистрированные аварии (часть 1)", "type": "bitfield"},
    0x00C5: {"name": "registered_alarms_1", "description": "Зарегистрированные аварии (часть 2)", "type": "bitfield"},
    0x00C6: {"name": "registered_alarms_2", "description": "Зарегистрированные аварии (часть 3)", "type": "bitfield"},
    0x00C7: {"name": "registered_alarms_3", "description": "Зарегистрированные аварии (часть 4)", "type": "bitfield"},

    0x00C8: {"name": "active_warnings_0", "description": "Активные предупреждения (часть 1)", "type": "bitfield"},
    0x00C9: {"name": "active_warnings_1", "description": "Активные предупреждения (часть 2)", "type": "bitfield"},
    0x00CA: {"name": "active_warnings_2", "description": "Активные предупреждения (часть 3)", "type": "bitfield"},
    0x00CB: {"name": "active_warnings_3", "description": "Активные предупреждения (часть 4)", "type": "bitfield"},

    0x00CC: {"name": "registered_warnings_0", "description": "Зарегистрированные предупреждения (часть 1)", "type": "bitfield"},
    0x00CD: {"name": "registered_warnings_1", "description": "Зарегистрированные предупреждения (часть 2)", "type": "bitfield"},
    0x00CE: {"name": "registered_warnings_2", "description": "Зарегистрированные предупреждения (часть 3)", "type": "bitfield"},
    0x00CF: {"name": "registered_warnings_3", "description": "Зарегистрированные предупреждения (часть 4)", "type": "bitfield"},

    # Система вентиляции
    0x00D0: {"name": "ventilation_target", "description": "Целевой уровень вентиляции", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x00D1: {"name": "ventilation_level", "description": "Фактический уровень вентиляции", "type": "unsigned", "scale": 0.1, "unit": "%"},
    0x00D2: {"name": "ventilation_scheme", "description": "Активная схема вентиляции", "type": "unsigned"},
    0x00D3: {"name": "day_counter", "description": "Счетчик дней", "type": "signed"},
    0x00D4: {"name": "temp_target", "description": "Целевая температура вентиляции", "type": "signed", "scale": 0.1, "unit": "°C"},
    0x00D5: {"name": "temp_inside", "description": "Текущая температура для вентиляции", "type": "signed", "scale": 0.1, "unit": "°C"},
    0x00D6: {"name": "temp_vent_activation", "description": "Температура активации вентиляции", "type": "signed", "scale": 0.1, "unit": "°C"},
}


def verify_kub1063_registers():
    """Проверка соответствия регистров в адаптере с документацией"""

    print("="*80)
    print("ПРОВЕРКА РЕГИСТРОВ КУБ-1063")
    print("="*80)

    # Создаем адаптер
    adapter = KUB1063Adapter()
    register_map = adapter.register_map

    # Получаем адреса из адаптера
    adapter_addresses = set(reg_info.address for reg_info in register_map.values())
    doc_addresses = set(DOCUMENTED_REGISTERS.keys())

    print(f"\nВсего регистров в документации: {len(doc_addresses)}")
    print(f"Всего регистров в адаптере: {len(adapter_addresses)}")

    # Проверка 1: Регистры из документации, которых нет в адаптере
    missing_in_adapter = doc_addresses - adapter_addresses
    if missing_in_adapter:
        print(f"\n❌ ОТСУТСТВУЮТ В АДАПТЕРЕ ({len(missing_in_adapter)} шт.):")
        for addr in sorted(missing_in_adapter):
            doc_info = DOCUMENTED_REGISTERS[addr]
            print(f"  0x{addr:04X} - {doc_info['description']}")
    else:
        print("\n✅ Все регистры из документации присутствуют в адаптере")

    # Проверка 2: Регистры в адаптере, которых нет в документации
    extra_in_adapter = adapter_addresses - doc_addresses
    if extra_in_adapter:
        print(f"\n⚠️  ЛИШНИЕ В АДАПТЕРЕ ({len(extra_in_adapter)} шт.):")
        for addr in sorted(extra_in_adapter):
            # Найдем имя регистра в адаптере
            for name, reg_info in register_map.items():
                if reg_info.address == addr:
                    print(f"  0x{addr:04X} - {name} ({reg_info.description})")
                    break
    else:
        print("\n✅ Нет лишних регистров в адаптере")

    # Проверка 3: Соответствие типов регистров (все должны быть INPUT)
    print(f"\n🔍 ПРОВЕРКА ТИПОВ РЕГИСТРОВ (все должны быть INPUT/FC04):")
    wrong_type_count = 0
    for name, reg_info in register_map.items():
        if reg_info.register_type.value != "input":
            print(f"  ❌ {name} (0x{reg_info.address:04X}): тип = {reg_info.register_type.value}, ожидается: input")
            wrong_type_count += 1

    if wrong_type_count == 0:
        print("  ✅ Все регистры имеют правильный тип (INPUT)")
    else:
        print(f"  ❌ Найдено {wrong_type_count} регистров с неправильным типом")

    # Проверка 4: Соответствие scale (масштаба)
    print(f"\n🔍 ПРОВЕРКА МАСШТАБА (scale):")
    wrong_scale_count = 0
    for name, reg_info in register_map.items():
        if reg_info.address in DOCUMENTED_REGISTERS:
            doc_info = DOCUMENTED_REGISTERS[reg_info.address]
            expected_scale = doc_info.get("scale")
            if expected_scale is not None and reg_info.scale != expected_scale:
                print(f"  ❌ {name} (0x{reg_info.address:04X}): scale = {reg_info.scale}, ожидается: {expected_scale}")
                wrong_scale_count += 1

    if wrong_scale_count == 0:
        print("  ✅ Все регистры имеют правильный масштаб")
    else:
        print(f"  ❌ Найдено {wrong_scale_count} регистров с неправильным масштабом")

    # Проверка 5: Соответствие знаковости (signed/unsigned)
    print(f"\n🔍 ПРОВЕРКА ЗНАКОВОСТИ (signed/unsigned):")
    wrong_sign_count = 0
    for name, reg_info in register_map.items():
        if reg_info.address in DOCUMENTED_REGISTERS:
            doc_info = DOCUMENTED_REGISTERS[reg_info.address]
            doc_type = doc_info.get("type")

            if doc_type == "signed" and not reg_info.signed:
                print(f"  ❌ {name} (0x{reg_info.address:04X}): unsigned, ожидается: signed")
                wrong_sign_count += 1
            elif doc_type == "unsigned" and reg_info.signed:
                print(f"  ❌ {name} (0x{reg_info.address:04X}): signed, ожидается: unsigned")
                wrong_sign_count += 1

    if wrong_sign_count == 0:
        print("  ✅ Все регистры имеют правильную знаковость")
    else:
        print(f"  ❌ Найдено {wrong_sign_count} регистров с неправильной знаковостью")

    # Итоговый отчет
    print(f"\n{'='*80}")
    print("ИТОГОВЫЙ ОТЧЕТ:")
    print(f"{'='*80}")

    total_errors = len(missing_in_adapter) + len(extra_in_adapter) + wrong_type_count + wrong_scale_count + wrong_sign_count

    if total_errors == 0:
        print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО")
        print("   Адаптер КУБ-1063 полностью соответствует документации")
        return 0
    else:
        print(f"❌ НАЙДЕНО ОШИБОК: {total_errors}")
        print(f"   - Отсутствуют в адаптере: {len(missing_in_adapter)}")
        print(f"   - Лишние в адаптере: {len(extra_in_adapter)}")
        print(f"   - Неправильный тип регистра: {wrong_type_count}")
        print(f"   - Неправильный масштаб: {wrong_scale_count}")
        print(f"   - Неправильная знаковость: {wrong_sign_count}")
        return 1


if __name__ == "__main__":
    sys.exit(verify_kub1063_registers())
