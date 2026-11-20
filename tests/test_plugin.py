from datetime import datetime, timedelta, timezone

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
    off = datetime.now().astimezone().replace(microsecond=0)
    r = on_hook(_payload({
        "event": "trip_ended", "odometer": "20756", "start_odometer": 20672,
        "lat": "52.3731", "lon": 4.8926, "zone": "home",
        "ignition_on": (off - timedelta(hours=1)).isoformat(), "ignition_off": off.isoformat(),
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
    assert on_hook(_payload({"odometer": "inf"})) is None
    assert on_hook(_payload({"odometer": "1e999"})) is None


def _ended_at(stamp):
    return on_hook(_payload({"odometer": 1, "ignition_off": stamp})).ended_at


def test_timestamp_forms():
    now = datetime.now().replace(microsecond=0)
    aware = now.astimezone()
    assert _ended_at(now.isoformat()) == now                                    # naive
    assert _ended_at(aware.isoformat()) == now                                  # with offset
    utc = aware.astimezone(timezone.utc).isoformat()
    assert _ended_at(utc.replace("+00:00", "Z")) == now                         # Z
    assert _ended_at("half past five") is None                                  # garbage


def test_timestamp_outside_the_window_is_dropped():
    now = datetime.now().replace(microsecond=0)
    assert _ended_at((now - timedelta(hours=23)).isoformat()) is not None
    assert _ended_at((now - timedelta(hours=25)).isoformat()) is None           # too old
    assert _ended_at((now + timedelta(minutes=4)).isoformat()) is not None
    assert _ended_at((now + timedelta(minutes=6)).isoformat()) is None          # in the future
    aware_old = (now - timedelta(hours=25)).astimezone().isoformat()
    r = on_hook(_payload({"odometer": 1, "ignition_on": aware_old}))
    assert r.started_at is None and r.end_odo == 1


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


def test_a_position_that_is_not_a_number_is_dropped():
    report = on_hook({"car_id": "c", "body": {"odometer": 150, "lat": "inf", "lon": "nan"}})
    assert report.end_odo == 150 and report.latitude is None and report.longitude is None
