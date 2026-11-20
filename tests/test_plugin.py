from datetime import datetime

from rittenregistratie.events import EventBus, hook_event
from rittenregistratie.models import VehicleTripReport
from rittenregistratie_homeassistant import on_hook, register


def _payload(body):
    return {"car_id": "mercedes", "plugin": "homeassistant", "body": body, "headers": {}}


def test_register_subscribes_to_hook_event():
    bus = EventBus()
    register(bus)
    assert len(bus.handlers(hook_event("homeassistant"))) == 1
    out = bus.emit(hook_event("homeassistant"), _payload({"odometer": 20756, "zone": "home"}))
    assert isinstance(out, VehicleTripReport) and out.end_odo == 20756


def test_full_body():
    r = on_hook(_payload({
        "event": "trip_ended", "odometer": "20756", "start_odometer": 20672,
        "lat": "52.3731", "lon": 4.8926, "zone": "home",
        "ignition_on": "2026-09-03T16:16:38+02:00", "ignition_off": "2026-09-03T17:23:02+02:00",
    }))
    assert r.end_odo == 20756 and r.start_odo == 20672
    assert (r.latitude, r.longitude) == (52.3731, 4.8926) and r.zone == "home"
    assert r.source == "homeassistant" and r.raw["odometer"] == "20756"
    assert isinstance(r.ended_at, datetime) and r.ended_at.tzinfo is None
    assert r.started_at < r.ended_at


def test_placeholders_and_non_places_are_dropped():
    r = on_hook(_payload({"odometer": 20756.4, "start_odometer": "unavailable", "lat": "unknown",
                          "lon": None, "zone": "not_home", "ignition_off": "unknown"}))
    assert r.end_odo == 20756 and r.start_odo is None and r.latitude is None
    assert r.zone == "" and r.ended_at is None


def test_ignored_cases():
    assert on_hook(_payload({"event": "ignition_on", "odometer": 1})) is None
    assert on_hook(_payload({"odometer": "unavailable", "zone": "home"})) is None
    assert on_hook(_payload({"zone": "home"})) is None
    assert on_hook({"car_id": "x", "plugin": "homeassistant", "body": "text", "headers": {}}) is None


def test_package_captures_at_ignition_off_and_rechecks_after_the_delay():
    from pathlib import Path

    import yaml

    class Loader(yaml.SafeLoader):
        pass
    Loader.add_constructor("!secret", lambda loader, node: node.value)
    text = (Path(__file__).parent.parent / "homeassistant" / "rittenregistratie.yaml").read_text()
    package = yaml.load(text, Loader)
    assert set(package) == {"automation", "rest_command", "input_number"}
    off = next(a for a in package["automation"] if a["id"] == "rittenregistratie_ignition_off")
    assert off["mode"] == "single" and set(off["variables"]) == {"start_odometer", "ignition_off"}
    delay, still_off, _odometer_ok, post = off["action"]
    assert "delay" in delay and "'0'" in still_off["value_template"]
    assert post["data"] == {k: "{{ %s }}" % k for k in off["variables"]}
    payload = package["rest_command"]["rittenregistratie_trip_ended"]["payload"]
    assert "{{ start_odometer }}" in payload and "{{ ignition_off }}" in payload
