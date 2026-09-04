"""Home Assistant → rittenregistratie-bot: automatic trips at ignition off.

Home Assistant already knows your car (via a car integration such as
``mbapi2020`` for Mercedes, or anything exposing an odometer and a device
tracker). An automation in Home Assistant POSTs one JSON object to the bot
when the ignition turns off; this plugin turns that object into a
``VehicleTripReport`` and the core does the rest: chains the odometer, resolves
the end place, writes the ledger row, notifies the driver(s).

Expected body (see ``homeassistant/`` for the automation that produces it)::

    {
      "event": "trip_ended",              # anything else is ignored
      "odometer": 20756,                  # required; km at ignition off
      "start_odometer": 20672,            # optional; km at ignition on
      "lat": 52.3702, "lon": 5.2147,      # optional; end position
      "zone": "home",                     # optional; device_tracker state
      "ignition_on": "2026-09-03T16:16:38+02:00",   # optional, ISO-8601
      "ignition_off": "2026-09-03T17:23:02+02:00"   # optional, ISO-8601
    }

Home Assistant's placeholder states ("unavailable", "unknown", "none", "") are
treated as absent. A body without a usable odometer is ignored.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from rittenregistratie.events import EventBus, hook_event
from rittenregistratie.models import VehicleTripReport

__all__ = ["register", "on_hook", "PLUGIN_NAME"]

PLUGIN_NAME = "homeassistant"
_PLACEHOLDERS = {"", "unavailable", "unknown", "none", "null"}
_EVENTS = {"trip_ended", "ignition_off"}
# device_tracker states that carry no place information
_NON_PLACES = {"not_home", "away"}

log = logging.getLogger("rittenregistratie.homeassistant")


def register(bus: EventBus) -> None:
    """Entry point: subscribe to inbound posts for this plugin."""
    bus.on(hook_event(PLUGIN_NAME), on_hook)


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in _PLACEHOLDERS else text


def _int(value: Any) -> Optional[int]:
    text = _clean(value)
    if text is None:
        return None
    try:
        return int(round(float(text)))
    except ValueError:
        return None


def _float(value: Any) -> Optional[float]:
    text = _clean(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _local_naive(value: Any) -> Optional[datetime]:
    """ISO-8601 (aware or naive) → naive local time, as the core stores it."""
    text = _clean(value)
    if text is None:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def on_hook(payload: dict) -> Optional[VehicleTripReport]:
    """Turn a Home Assistant post into a trip report, or None to ignore it."""
    body = payload.get("body")
    if not isinstance(body, dict):
        return None
    event = (_clean(body.get("event")) or "trip_ended").lower()
    if event not in _EVENTS:
        return None
    end_odo = _int(body.get("odometer"))
    if end_odo is None:
        log.info("homeassistant: post for %s without a usable odometer; ignored", payload.get("car_id"))
        return None
    zone = _clean(body.get("zone")) or ""
    if zone.lower() in _NON_PLACES:
        zone = ""
    return VehicleTripReport(
        end_odo=end_odo,
        start_odo=_int(body.get("start_odometer")),
        ended_at=_local_naive(body.get("ignition_off")),
        started_at=_local_naive(body.get("ignition_on")),
        latitude=_float(body.get("lat")),
        longitude=_float(body.get("lon")),
        zone=zone,
        place=_clean(body.get("place")) or "",
        source=PLUGIN_NAME,
        raw=body,
    )
