# RTU Bus Simulator

Скрипт `rtu_bus_sim.py` эмулирует Modbus RTU шину через один виртуальный последовательный порт (PTY) с несколькими slave ID.

## Запуск

```bash
python EDGE/tools/simulators/rtu_bus_sim.py --kub 1-2 --vfd 3-4 --kub1112 5-8
```

Параметры:
- `--kub` — диапазон ID для эмуляции контроллеров КУБ-1063.
- `--vfd` — диапазон ID для эмуляции VFD (частотных преобразователей).
- `--kub1112` — диапазон ID для эмуляции КУБ-1112.

После запуска скрипт выводит путь к созданному PTY (например, `/dev/ttys027`). Этот порт можно указать в `start_edge.py`:

```bash
python EDGE/start_edge.py --autoscan --rs485-port /dev/ttys027 --scan-start 1 --scan-end 8
```

Для вывода помощи используйте:

```bash
python EDGE/tools/simulators/rtu_bus_sim.py --help
```
