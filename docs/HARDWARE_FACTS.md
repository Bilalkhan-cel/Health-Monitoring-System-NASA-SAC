# Hardware facts register

This file records what is actually known about the wearable hardware (ESP32 + MAX30102 + DS18B20)
and the demo network. It is updated **only with measured results** from `docs/HARDWARE_TEST.md`
(written in Phase 4, run in Phase 11).

Status values:

- **Confirmed (owner)**: stated by the owner from photos.
- **Documented, not verified**: published information that may not match this exact part.
- **Needs physical test**: unknown until measured.

Nothing in this register has been tested on the physical hardware yet. No row may be changed to
"verified" without a measurement, and no "Needs physical test" row may be stated as a fact in the
README or the UI.

| # | Item | Status | How to settle it | Measured result |
|---|---|---|---|---|
| 1 | Board is a 30-pin, USB-C, classic ESP32 DevKit-style board, shield marked "ESP-32", not S3/C3 | Confirmed (owner) | n/a | n/a |
| 2 | Exact module variant (WROOM-32, "D"/"U" variant, clone) and flash size | Needs physical test | Read the shield text closely; the chip and flash report in the boot log or via the flashing tool | not tested |
| 3 | USB-serial chip and whether Windows needs a driver | Needs physical test | Device Manager when plugged in; record the chip and COM port (T2) | not tested |
| 4 | Pins labelled 21, 22 and 4, plus 3V3 and GND, exist and are usable on this board | 21 and 22 specified by owner; 4 proposed | Check the silkscreen before wiring | not tested |
| 5 | Which pin drives the onboard LED, if any | Needs physical test | CLI LED test; otherwise serial only | not tested |
| 6 | Upload works automatically or needs BOOT held | Needs physical test | T2 | not tested |
| 7 | MAX30102 module has 7 pins: VIN, SCL, SDA, INT, IRD, RD, GND (left to right) | Confirmed (owner) | n/a | n/a |
| 8 | Module supply range on VIN | Documented, not verified. Published listings disagree: one says 3.3–5 V, another says a specific board version accepts 3.3 V only | T-1 step V1 using this module's own listing | not tested |
| 9 | Voltage the I²C pull-ups (SDA, SCL, INT) connect to | Documented to vary between boards; unknown for this one | T-1 step V3 (multimeter) | not tested |
| 10 | Purpose of IRD and RD | Documented only as controlling the infrared and red LED, with no further explanation | Leave unconnected; confirm in this module's own documentation before ever using them | not tested |
| 11 | MAX30102 I²C address 0x57 | Documented for the chip | T3 `scan` | not tested |
| 12 | DS18B20 form (bare, probe, module) and whether a pull-up is already present | Needs physical test | T-1 step D1 | not tested |
| 13 | The owner's resistor is 4.7 kΩ | Stated by owner | Optional: confirm with the colour bands or a multimeter | not tested |
| 14 | Hotspot offers 2.4 GHz, WPA2, and allows client-to-client traffic | 2.4 GHz is the intended setup; the rest is unknown | T0, T1, T4 | not tested |
| 15 | Windows network profile (Public/Private) and firewall behaviour for the hotspot | Needs physical test | T0, T1 | not tested |
| 16 | Laptop address stability on the hotspot | Expected to change between sessions | `device_setup.py --show` every session; T12 | not tested |
| 17 | IR finger-detection thresholds (50 000 on / 30 000 off) | Placeholders | T5b `cal` | not tested |
| 18 | Heart-rate and SpO₂ accuracy of this sensor on this finger | Unknown | T6 | not tested |
| 19 | Under-arm temperature offset (+0.6 °C), settle floor (34.5 °C) and settle time | Placeholders from published ranges | T9 | not tested |
| 20 | USB power from the laptop is enough and stable | Needs physical test | T14 | not tested |
| 21 | The pinned firmware libraries compile for this board | Not verified | `pio run -d firmware` (P4) | not tested |
| 22 | Alert-gate defaults (`min_quality` 60, 10 consecutive frames, 80 % coverage, 15 bpm range) suit this sensor on this finger | Placeholders, not measured | T6, T13a; adjust `thresholds.yaml` and record the final values | not tested |
| 23 | `rest_verified` approximates real rest | Unknown; there is no motion sensor | T13a; treat as a weak check and say so | not tested |
