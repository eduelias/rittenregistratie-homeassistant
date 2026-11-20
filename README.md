# rittenregistratie-homeassistant

Home Assistant plugin for [rittenregistratie-bot](https://github.com/eduelias/rittenregistratie-bot):
when your car's ignition goes off, Home Assistant posts the odometer and position to the
bot and the trip is logged automatically. No typing, same ledger, same faithful record.

Works with any car Home Assistant can see with an **odometer sensor**, an **ignition
state** and a **device tracker** (for Mercedes: the `mbapi2020` integration).

## How it fits together

```
car cloud ──▶ Home Assistant ──automation──▶ POST /hooks/homeassistant/<car>  ──▶ rittenregistratie-bot
                                             (X-Hook-Secret)                      │
                                                                                  ├─ this plugin: body → VehicleTripReport
                                                                                  └─ core: chain odometer, resolve place,
                                                                                     write ledger row, notify on WhatsApp
```

The core never guesses. The end place is a known location (by name or by proximity to
its `lat`/`lon`), otherwise the reverse-geocoded address; unknown places ask you to
reply `name <place>` on WhatsApp. If the odometer at ignition on differs from the last
row, the uncovered kilometres are stated in the row's note, never filled in.

## Install (on the machine running the bot)

```bash
pip install git+https://github.com/eduelias/rittenregistratie-homeassistant
```

In the bot's `.env`:

```
RIT_HOOK_SECRET=<a long random string>
```

In the bot's `config/cars.yaml`, opt the car in (other cars are unaffected):

```yaml
mercedes:
  event_plugins: ["homeassistant"]      # add to any plugins already listed
```

Give known locations coordinates so trips resolve to them:

```yaml
# config/locations.yaml
home:   { address: "Dam 1, Amsterdam", lat: 52.3731, lon: 4.8926 }          # example values
office: { address: "Stationsplein 1, Utrecht", lat: 52.0894, lon: 5.1100 }
```

Restart the bot. The bot must be reachable from Home Assistant (bind to your LAN
address, not only localhost).

## Home Assistant side

Copy [`homeassistant/rittenregistratie.yaml`](homeassistant/rittenregistratie.yaml) to
`<config>/packages/`, replace the placeholder entity ids (`sensor.my_car_odometer`,
`sensor.my_car_ignition_state`, `device_tracker.my_car`) with your car's, and add to
`secrets.yaml`:

```yaml
rittenregistratie_hook_url: "http://<bot-host>:8000/hooks/homeassistant/<car_id>"
rittenregistratie_hook_secret: "<the same RIT_HOOK_SECRET>"
```

It defines an `input_number` that remembers the odometer at ignition on, a
`rest_command` that posts the trip, and two automations: one at ignition on, one at
ignition off.

The ignition-off automation notes the stored start odometer and the moment the ignition
went off, waits two minutes so the last odometer and position update land, and posts only
if the ignition is still off. A car switched on again within those two minutes is still on
its trip, so nothing is posted until it is switched off and stays off. The row carries the
ignition-off time, not the time of the post.

## What the bot receives

```json
{"event": "trip_ended", "odometer": "20756", "start_odometer": "20672",
 "lat": "52.3731", "lon": "4.8926", "zone": "home",
 "ignition_off": "2026-09-03T15:23:02.512345+00:00"}
```

Only `odometer` is required. Home Assistant placeholders (`unavailable`, `unknown`)
are treated as absent; `not_home` carries no place and is dropped. An `ignition_off`
more than 24 hours old or more than 5 minutes ahead is dropped too, and the bot's own
clock is used. A post without a
usable odometer is ignored, and so is a reading that is not above the last logged one,
so a typed message and an automatic one for the same trip never produce two rows.

## Test it without driving

```bash
curl -X POST http://<bot-host>:8000/hooks/homeassistant/mercedes \
  -H "X-Hook-Secret: $RIT_HOOK_SECRET" -H "Content-Type: application/json" \
  -d '{"event":"trip_ended","odometer":20757,"zone":"home","lat":52.3731,"lon":4.8926}'
```

A reading equal to the current one answers `{"status": "ignored", ...}`; a higher one
logs a trip, so use a real reading or expect a row you will have to explain.

## License

MIT.
