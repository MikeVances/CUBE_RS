import datetime
import sys
from pathlib import Path

EDGE_ROOT = Path(__file__).parent.parent
if str(EDGE_ROOT) not in sys.path:
    sys.path.insert(0, str(EDGE_ROOT))

from core.device_registry import DeviceInfo, DeviceType
from web_dashboard.services import room_data


class DummyRegistry:
    def __init__(self, devices, payloads):
        self._devices = devices
        self._payloads = payloads

    def get_devices(self, enabled_only: bool = True):
        return self._devices

    def get_device_data(self, device_id: int):
        return self._payloads[device_id]


def test_room_snapshot_keeps_type_specific_metrics():
    devices = [
        DeviceInfo(device_id=1, device_type=DeviceType.KUB_1063, slave_id=1, name="KUB1"),
        DeviceInfo(device_id=2, device_type=DeviceType.VFD_INVERTER, slave_id=2, name="VFD"),
    ]
    timestamp = datetime.datetime.utcnow().isoformat()
    payloads = {
        1: {
            "timestamp": timestamp,
            "registers": {"temp_inside": 24.5, "humidity": 55},
            "connection_status": "online",
            "active_alarms": 1,
            "alarms": ["Перегрев датчика"],
        },
        2: {
            "timestamp": timestamp,
            "registers": {"running_frequency": 48.0},
            "fault_code": 7,
            "connection_status": "error",
            "active_alarms": 0,
        },
    }
    registry = DummyRegistry(devices, payloads)

    room_data.build_room_snapshots.clear()
    rooms = room_data.build_room_snapshots.__wrapped__(registry)  # type: ignore[attr-defined]
    assert rooms, "должно вернуться хотя бы одно помещение"

    snapshot = rooms[0]
    assert set(snapshot.device_metrics[1].keys()) == {"temp_inside", "humidity"}
    assert set(snapshot.device_metrics[2].keys()) == {"running_frequency"}

    vfd_status = snapshot.device_statuses[2]
    assert vfd_status.connection_status == "error"
    assert vfd_status.fault_code == 7

    assert snapshot.device_statuses[1].active_alarms == 1
    assert snapshot.device_statuses[1].alarms == ["Перегрев датчика"]

    meta = snapshot.metric_metadata[1]["temp_inside"]
    assert meta.label
