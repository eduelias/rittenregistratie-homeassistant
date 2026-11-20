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
