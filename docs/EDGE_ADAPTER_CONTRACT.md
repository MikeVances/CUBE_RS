# EDGE Adapter Contract

Документ описывает минимальный набор агрегированных данных, которые должен формировать любой адаптер устройства, чтобы веб-дашборд, room_snapshot_service и Telegram-бот работали без знания карты регистров.

## 1. Данные по цепочке

```
Modbus → DeviceAdapter.parse_device_data → DeviceRegistry (payload) →
room_snapshot_service.build_room_snapshots → UI/бот
```

Адаптер обязан вернуть нормализованный `DeviceData.registers`, содержащий человекочитаемые ключи и агрегаты. UI работает только с этими ключами; прямой доступ к регистрам запрещён.

## 2. Обязательные поля payload

Каждый адаптер формирует:

- `connection_status`, `status`, `timestamp` — строковые статусы устройства.
- `active_alarms_total`, `active_warnings_total` — суммарные счётчики (карточки «Аварии/Предупреждения»).
- `active_alarms_list`, `active_warnings_list` — список словарей `{id, label, severity, category}`. UI больше не парсит битовые маски.
- `relay_assignments` — массив структур для реле/аналоговых каналов (см. §4).
- `emergency_relay` и алиасы `emergency_relay_state`, `emergency_relay_state_label`, `emergency_relay_channel` — состояние аварийного реле и канал для кнопки сброса.
- `supports_alarm_reset` — булев флаг, сигнализирующий, что устройство поддерживает команду квитирования (UI показывает кнопку сброса только если поле истинно).
- Все метрики, которые должны отображаться на плитках, описываются через `extra_metric_metadata`/`variable_mapper` (название → label/unit/hidden).

## 3. Поведение при деградации связи

Если устройство недоступно, адаптер возвращает урезанный payload, но поддерживает поля из п.2. `collect_device_payloads` сохраняет только эти агрегаты, поэтому UI всегда видит актуальные данные даже при «нет связи».

## 4. Формат `relay_assignments`

Каждый элемент:

| поле | тип | описание |
|------|-----|----------|
| `key` | str | уникальный идентификатор функции |
| `label` | str | подпись в UI |
| `category` | str | группа карточек |
| `channel` | int	null | номер физического канала (0-based) |
| `channel_label` | str | форматированный канал (`K1`, `AI1`, `AO1`) |
| `channel_display` | str | fallback текст для UI |
| `channel_type` | str | `relay`/`analog_input`/`analog_output` |
| `state` | bool|null | фактическое состояние (по битовому полю) |
| `state_label` | str | «ВКЛ», «ВЫКЛ», «Назначено», «Н/Д» |
| `state_variant` | str | `on/off/assigned/unknown` — используется в CSS |
| `register` | int | адрес Modbus |
| `register_hex` | str | адрес в hex для подсказок |
| `bitfield`/`bit` | опционально — источник состояния |
| `order` | int | сортировка внутри категории |

UI не интерпретирует регистры; он использует `channel_display`, `state_label` и `state_variant`.

## 5. Аварийное реле

Адаптеры с аварийным реле выполняют:

- `emergency_relay = {state, state_label, channel, channel_label, source}`;
- дублируют `state/state_label` в `emergency_relay_state*` для обратной совместимости;
- добавляют запись в `relay_assignments` с `key="emergency"`.

Фронт использует эти данные для подсветки состояния и кнопки сброса, без чтения `digital_outputs_*`.

## 6. Аварии и предупреждения

Адаптер сам декодирует битовые маски и выдаёт список элементов вида:

```json
{
  "id": 43,
  "label": "Перегрев туннеля",
  "severity": "alarm",
  "category": "Температура"
}
```

Если нет точного текста, используется `label = "Авария <id>"`. Severity следует задавать явно: `alarm`, `warning`, `info` или, для отключённых датчиков, `sensor_disabled`. UI по умолчанию фильтрует элементы с `severity: sensor_disabled`, поэтому «выключенные» сенсоры не засоряют список тревог.

## 7. Метаданные метрик

- `extra_metric_metadata`/`variable_mapper` описывают все метрики (label/unit/hidden).
- Технические поля (`*_relay_channel`, `relay_assignments`) помечаются `hidden: true`, UI исключает их из пользовательских списков.

## 8. Пример payload (фрагмент)

```json
{
  "connection_status": "ok",
  "status": "ok",
  "active_alarms_total": 0,
  "active_alarms_list": [],
  "emergency_relay": {
    "state": true,
    "state_label": "Аварийное реле: ВКЛ",
    "channel": 11,
    "channel_label": "K12"
  },
  "supports_alarm_reset": true,
 "relay_assignments": [ {"key": "emergency", "state_label": "ВКЛ", ... }, ... ]
}
```

## 9. Требования к новым адаптерам

1. Нормализуйте данные в `parse_device_data` и формируйте агрегаты даже при недоступности устройства.
2. Не публикуйте `digital_outputs_*`, `vent_curve_*` и прочие регистры напрямую — только готовые структуры.
3. Если сенсор отключён, отображайте это через `status`/`MetricMetadata`, а не через `get_warnings()` — список предупреждений должен содержать только реальные события.
4. Документируйте новые агрегаты в этом файле или в docstring адаптера.
5. Соблюдайте безопасность: не логируйте секреты, не храните токены в коде.

Следуя контракту, любое новое устройство появляется в UI без дополнительных правок фронтенда.
