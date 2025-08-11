#!/usr/bin/env python3
"""
Тест чтения всех регистров КУБ-1063 из Cube-1063_modbus registers.md
"""
import sys
import os
import time
sys.path.append(os.path.join(os.path.dirname(__file__), 'modbus'))
from reader import KUB1063Reader

# Все регистры из Cube-1063_modbus registers.md (Input Registers, функция 0x04)
REGISTER_LIST = [
    (0x0301, "Версия ПО"),
    (0x0081, "Сост. цифровых выходов (1)"),
    (0x0082, "Сост. цифровых выходов (2)"),
    (0x00A2, "Сост. цифровых выходов (3)"),
    (0x0083, "Отрицательное давление"),
    (0x0084, "Влажность"),
    (0x0085, "CO2"),
    (0x0086, "NH3"),
    (0x0087, "ГРВ базовой вентиляции"),
    (0x0088, "ГРВ туннельной вентиляции"),
    (0x0089, "Демпфер"),
    # 0x008A–0x009B пропущены (групповые)
    (0x00C3, "Активные аварии"),
    (0x00C7, "Зарегистрированные аварии"),
    (0x00CB, "Активные предупреждения"),
    (0x00CF, "Зарегистрированные предупреждения"),
    (0x00D0, "Целевой уровень вентиляции"),
    (0x00D1, "Фактический уровень вентиляции"),
    (0x00D2, "Схема вентиляции"),
    (0x00D3, "Счетчик дней"),
    (0x00D4, "Целевая температура"),
    (0x00D5, "Текущая температура"),
    (0x00D6, "Темп. активации вентиляции"),
]

def main():
    reader = KUB1063Reader()
    print("\n🔍 Чтение всех регистров КУБ-1063 (Input Registers, функция 0x04):\n")
    if not reader.connect():
        print("❌ Не удалось подключиться к устройству!")
        return
    for reg, desc in REGISTER_LIST:
        value = reader.read_register(reg, function_code=0x04)
        if value is not None:
            print(f"0x{reg:04X} ({desc}): 0x{value:04X} ({value})")
        else:
            print(f"0x{reg:04X} ({desc}): ❌ нет ответа")
        time.sleep(0.1)
    reader.disconnect()

if __name__ == "__main__":
    main() 