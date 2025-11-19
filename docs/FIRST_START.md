# First Start Guide (EDGE)

Этот документ описывает шаги подготовки и тестирования EDGE узла с использованием симулятора RTU-шины.

## 1. Подготовка конфигурации и секретов

1. Запустите мастер первого запуска:
   ```bash
   python EDGE/tools/first_start.py
   ```
   Мастер задаст мастер-пароль, удалит `dev_password.txt`, сохранит TELEGRAM токен и при желании запустит автоскан.

2. Убедитесь, что в `config/app_config.yaml` указаны корректные параметры `rs485.port` и секция `polling` (по умолчанию 20 c timeout/intervals для стабильных симуляций).

3. Проверьте `config/devices.yaml` — в нём должны появиться записи после автосканирования. При необходимости откорректируйте `poll_interval` для конкретных устройств.

## 2. Запуск RTU-симулятора

```bash
python EDGE/tools/simulators/rtu_bus_sim.py --kub 1 --vfd 2 --kub1112 3-6 --port /tmp/rtu_sim
```

- Если установлен `socat`, симулятор создаст фиксированный PTY `/tmp/rtu_sim` (иначе используйте путь из вывода симулятора).
- Чтобы остановить симулятор, нажмите `Ctrl+C` в его терминале.

## 3. Автоскан и запуск EDGE

Во втором терминале:
```bash
python EDGE/start_edge.py --autoscan --rs485-port /tmp/rtu_sim --scan-start 1 --scan-end 10
```

- Скрипт обновит `config/devices.yaml` списком обнаруженных устройств и запустит `start.py`.
- В логах ищите строку `📅 Scheduler создан` и затем сообщения `📡 Опрос ...`.

## 4. Проверка данных

- Основная база: `data/kub_data.db`. Проверить актуальные записи:
  ```bash
  sqlite3 data/kub_data.db "SELECT device_id, MAX(updated_at) FROM latest_data GROUP BY device_id;"
  ```
- Логи находятся в `config/logs/` (см. README для симулятора).

## 5. Остановка
a. `Ctrl+C` в терминале симулятора.
b. `Ctrl+C` в терминале `start_edge.py`.

## 6. Рекомендуемые настройки (симулятор)

```yaml
polling:
  timeout: 20.0
  max_retries: 3
  backoff_factor: 10.0
  backoff_max: 60.0
  default_intervals:
    KUB-1063: 20.0
    KUB-1112: 20.0
    VFD-INVERTER: 20.0
```

Эти значения уменьшают нагрузку и предотвращают ложные таймауты при тестовых запуске с симулятором.

