# AstroVital wearable firmware

ESP32 DevKit + MAX30102 (pulse and SpO₂) + DS18B20 (temperature probe). The wearable sends one
frame per second as JSON over your local Wi-Fi to `POST /api/device/ingest`. It holds no clinical
logic: the server re-checks every value.

> **Hardware status: needs hardware.** This firmware compiles, but nothing has been tested on the
> physical parts yet. Run the checks below and `docs/HARDWARE_TEST.md` before trusting any reading,
> and record every result in `docs/HARDWARE_FACTS.md`.

## What you need

- the ESP32 board (30-pin, USB-C), the MAX30102 module, the DS18B20, one 4.7 kΩ resistor (only if
  the DS18B20 has no pull-up of its own) and jumper wires;
- a **2.4 GHz** Wi-Fi network (the ESP32 cannot join 5 GHz), plain ASCII name and password;
- `pip install platformio` (or the Arduino IDE, see the end).

## Before the first power-up (do these in order, do not modify the board)

| Step | Do this | Read the result like this |
|---|---|---|
| V1 Identify | Photograph both sides of the MAX30102 module; keep the seller listing; write down its stated supply range. | If the stated range does not include 3.3 V, stop. If you cannot find one, write "unknown" and continue with V2–V3 only. |
| V2 Power alone | Connect only VIN → 3V3 and GND → GND. Leave SDA, SCL, INT, IRD and RD unconnected. | Nothing should get hot. If it does, unplug and stop. |
| V3 Pull-up voltage | Multimeter on DC volts, black lead on GND: measure VIN, then SDA, SCL and INT. | ≈ 3.3 V on SDA and SCL: continue. ≈ 1.8 V or ≈ 0 V or anything else: **stop and report the numbers**. |
| D1 DS18B20 pull-up | DS18B20 unpowered and unplugged: measure resistance between DQ and VDD. | ≈ 4.7 kΩ: a pull-up is already there, do not add yours. Open / very high: add your 4.7 kΩ. Anything else: stop and report. |
| V4 Wire it | Wire exactly as the tables below, then power from USB. | |
| V5 Scan | Serial console: `scan`. | Expect a device at `0x57`. |
| V6 If 0x57 is missing | Stop. Re-check wiring and your V3 numbers. | **Do not modify the board.** What to do next depends on this module's own documentation. |

Everything runs at **3.3 V**. Never put 5 V on a GPIO, and never use the 5 V pin for the MAX30102
until its supply range is confirmed.

## Wiring (GPIOs are set in `include/pins.h` only)

| MAX30102 | ESP32 | Note |
|---|---|---|
| VIN | 3V3 | provisional until V1–V3 pass |
| GND | GND | |
| SCL | GPIO 22 | |
| SDA | GPIO 21 | |
| INT | not connected | the firmware polls the FIFO |
| IRD | not connected | purpose not confirmed |
| RD | not connected | purpose not confirmed |

| DS18B20 | ESP32 |
|---|---|
| VDD | 3V3 |
| GND | GND |
| DQ | GPIO 4, plus 4.7 kΩ from DQ to 3V3 **only if D1 found no pull-up** |

Check your board's silkscreen: pins 21, 22 and 4 must exist. Avoid GPIO 6–11, 34–39 and the
strapping pins 0/2/5/12/15 for sensors. Keep the I²C and 1-Wire wires short and apart.

## Configure and flash

```bash
python scripts/device_setup.py
```

It lists this computer's local addresses (pick the one on the wearable's Wi-Fi), asks for the Wi-Fi
name and password, and writes `firmware/include/secrets.h` (git-ignored). Then:

```bash
pio run -d firmware -t upload
```

```bash
pio device monitor -b 115200
```

Things to check (not confirmed for this board yet): on Windows the board appears as a COM port through
its USB-serial chip, which may need a driver (look in Device Manager); some boards need the **BOOT**
button held while uploading starts.

## Serial commands (115200 baud)

| Command | What it does |
|---|---|
| `status` | Wi-Fi, server URL, last HTTP status, queue depth, IR/red level, probe reading, free heap |
| `scan` | I²C scan (expect `0x57`) |
| `cal` | prints the IR level for 5 s: compare with and without a finger to tune `FINGER_ON_IR` / `FINGER_OFF_IR` |
| `ping` | `GET /api/device/ping` with the token |
| `ip` | the wearable's own address |
| `server <url>` | store a new server URL in flash (no re-flash): use it when the laptop's address changes |
| `server` | print the stored URL |
| `led` | blink the status LED (tells you whether GPIO 2 has one) |
| `reboot` | restart |

Free heap is printed every 60 s so a leak is visible.

## Status LED (GPIO 2, mirrored to serial)

slow blink = connecting to Wi-Fi · fast blink = server unreachable · three quick blinks = token
rejected · short pulse per heartbeat · off = idle.

## How it behaves

- 25 samples per second from the MAX30102 (100 Hz, average 4); one frame per second.
- Finger detection with hysteresis (on above 50 000, off below 30 000: placeholders, tune with `cal`).
- On finger-off the frame says `finger=false`, values are null and all buffers are cleared, so an
  old value is never reused.
- Heart rate and SpO₂ from the Maxim algorithm over a 4 s window, then a median of the last 5 valid
  values (published only when 3 of 5 were valid). HRV is not computed.
- DS18B20: one non-blocking conversion per second; `-127` (unplugged) and an unconfirmed `85.0`
  (power-on default) are discarded. Only the raw reading is sent: the under-arm offset lives on the
  server and can be calibrated in Settings → Wearable.
- Up to 300 frames (5 min) are buffered while the server or Wi-Fi is down, oldest dropped first.
  Retries back off 1 → 2 → 4 → 8 → 15 s; after 60 s of failures it tries mDNS discovery
  (`_astrovital._tcp`, untested on Windows). A `401` stops sending until the token is fixed.
- After 20 s offline it forces a Wi-Fi reconnect; after 5 minutes it restarts.

## Troubleshooting

- **No Wi-Fi**: 2.4 GHz only; check the name spelling, WPA2, plain ASCII.
- **`401` / three quick blinks**: run `python scripts/device_setup.py` and re-flash (or `--rotate` was used).
- **Connected but no data**: Windows firewall profile (`python scripts/device_setup.py --firewall`),
  a changed laptop address (`server http://<ip>:5000`), or hotspot client isolation (see
  `docs/HARDWARE_TEST.md`, T4).
- **Erratic SpO₂**: pressing too hard, cold finger, strong ambient light. It is a hobby-grade sensor.
- **Temperature stuck at ambient**: the probe is not touching skin, or the arm is not held down.
- **`0x57` missing**: follow V6. Do not modify the board.

## Arduino IDE alternative

Install the four libraries at the versions pinned in `platformio.ini`, open `src/main.cpp` with the
other files in the same sketch folder, copy `include/*.h` next to it, select "ESP32 Dev Module", and
upload. PlatformIO is the tested path.

## Tests

`pio test -d firmware -e native` runs the pure-logic tests (finger hysteresis, median filter, queue
overflow, backoff schedule) on your computer. It needs a host C++ compiler (gcc or clang).
