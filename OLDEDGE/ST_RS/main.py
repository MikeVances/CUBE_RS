#!/usr/bin/env python3
"""
main.py - Entry point for Stienen RS485 Gateway
Точка входа для гейтвея Stienen RS485
"""

import asyncio
import sys
import os
from pathlib import Path

# Добавляем текущую директорию в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from stienen.main_application import main

if __name__ == "__main__":
    # Проверяем Python версию
    if sys.version_info < (3, 8):
        print("Ошибка: Требуется Python 3.8 или выше")
        sys.exit(1)
    
    # Проверяем права доступа на Linux для COM портов
    if sys.platform.startswith('linux'):
        user_groups = os.getgroups()
        # Получаем GID группы dialout
        try:
            import grp
            dialout_gid = grp.getgrnam('dialout').gr_gid
            if dialout_gid not in user_groups:
                print("Предупреждение: Пользователь не в группе 'dialout'")
                print("Для доступа к COM портам выполните: sudo usermod -a -G dialout $USER")
                print("Затем перелогиньтесь")
        except KeyError:
            pass  # Группа dialout не существует
    
    # Запуск основного приложения
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nПрограмма прервана пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
