# Hardware test procedure

Run this with the real ESP32, MAX30102 and DS18B20. Record PASS/FAIL, the numbers you observed and the
date for every step in the results table at the end, and update the matching row of
`docs/HARDWARE_FACTS.md`. Do not skip a step to reach a later one. Never write "verified" for
something you did not measure. The wiring and pre-power checks are explained in `firmware/README.md`.

**Status: not run yet (needs hardware).**

## Steps

**T-1 Pre-power checks.** Run V1–V6 and D1 from `firmware/README.md` (identify the module, power it alone, measure the pull-up voltages, measure the DS18B20 pull-up).
PASS when V3 shows ≈ 3.3 V on SDA and SCL (otherwise stop and report). D1 decides whether the 4.7 kΩ resistor is needed.

**T0 Network.** Phone hotspot on 2.4 GHz (WPA2 if selectable, plain ASCII name and password, auto-off disabled, phone plugged in). Join the laptop. In Windows, check whether the hotspot network is Public or Private; set it to Private, or prepare `python scripts/device_setup.py --firewall`. Run `python scripts/device_setup.py` and note the printed URL.
PASS when the URL is printed, the network type is recorded and the laptop's IP is noted.

**T1 Server reachable.** Start `python run.py`. From a second device on the hotspot (the phone browser is enough) open `http://<laptop-ip>:5000/healthz`. Run `python scripts/device_check.py`.
PASS when `/healthz` answers and `device_check.py` reports "server reachable" and "token valid". If the phone cannot reach it, it is a firewall or address problem.

**T2 Flash.** `pio run -d firmware -t upload`, then `pio device monitor -b 115200`. Record the COM port, the USB-serial chip and whether BOOT had to be held.
PASS when the boot log shows the firmware version and a `boot_id`, with no reset loop.

**T3 Sensors found.** Serial `scan`; read the boot log.
PASS when there is an I²C device at `0x57` and the DS18B20 count is 1. If `0x57` is missing, follow V6: stop, do not modify the board, report the V3 numbers.

**T4 Wi-Fi + server (client isolation test).** Watch the LED or serial. Serial `ip` and `ping`. From the laptop run `ping <esp32-ip>`.
PASS when the ESP32 gets an address, `ping` returns `200` and Settings → Wearable shows "Connected". If the ESP32 has an address but `ping` fails while the phone browser could reach the laptop in T1, suspect client isolation (or an ESP32 fault) and try Plan B: Windows Mobile hotspot on the laptop (untested; the laptop's address there is commonly 192.168.137.1, which must be checked).

**T5 No finger.** Leave the sensor uncovered for 30 s.
PASS when Today shows "Place a finger on the sensor", no heart rate or SpO₂ is stored, and `finger=false` frames arrive.

**T5b IR calibration.** Serial `cal` with and without a finger.
PASS when you have values that separate the two cases with margin. Put them in `include/config.h` (`FINGER_ON_IR`, `FINGER_OFF_IR`) and record them.

**T6 Finger on.** Rest a fingertip lightly on the sensor. Count your pulse for 30 s by hand; compare with a trusted oximeter if you have one.
PASS when heart rate and SpO₂ appear within 10 s, heart rate is within ±5 bpm of your count, and SpO₂ is within ±3 points of the reference (or plausible, 94–100 %, if you have none).

**T7 Finger off.** Lift the finger.
PASS when live heart rate and SpO₂ clear within 2 s, nothing stale is shown, and no alert appears.

**T8 Motion.** Tap and shake the hand while the finger is on.
PASS when values are flagged weak or dropped, there is **never a red alert**, at most a Needs attention message for SpO₂, and readings recover within 10 s of holding still.

**T9 Temperature.** Probe on the desk, then under the arm with the arm down for 10 minutes. Compare with a reference thermometer.
PASS when the desk shows state `ambient` with no status; the arm reaches `settled`; after calibrating in Settings → Wearable the shown value is within ±0.3 °C of the reference. Record the real settle time and offset.

**T10 Probe unplugged.** Unplug the DS18B20 for 10 s, then replug.
PASS when "Temperature probe not found" appears within 3 s and readings recover within 5 s of replugging.

**T11 Wi-Fi gap.** Turn the hotspot off for 60 s, then on.
PASS when the device reconnects by itself, the 60 s backlog arrives, history has no hole and the live strip shows only the newest frame.

**T12 Server restart / new address.** Stop `run.py` for 30 s, then start it. Then change the server URL on purpose with `server http://<other-ip>:5000` and back.
PASS when the device retries and resumes with no reboot and no crash, and the stored URL survives a reboot.

**T13 Cardio session.** Rest check, then a full 90 s session on the wearable.
PASS when the session is saved with at least 60 % valid coverage and charts and Today update live.

**T13a Heart-rate gate.** In a rest-checked session, hold still for 30 s, then shake the hand hard for 15 s; repeat once without the rest countdown (the Demo skip does not count).
PASS when shaking never produces Get help now. A steady CRITICAL-range value can only be produced with real data, so use the emulator for that case. Record the quality `q` while still and while shaking to calibrate `min_quality`.

**T13b Mode is manual.** With the wearable switched off for 10 minutes, watch Settings → Demo panel.
PASS when the mode is unchanged and no demo values appear. Then switch to Demo data by hand and back.

**T14 Soak.** Leave it running for 30 minutes with the finger on, on USB power from the laptop.
PASS when there is no gap longer than 3 s in the live feed, free heap is stable (serial prints it every 60 s), ingest p95 is under 50 ms, `/api/summary` p95 is under 300 ms, and there are no brown-out resets.

## Troubleshooting

*No Wi-Fi* → 2.4 GHz band, SSID spelling, WPA2, plain ASCII name. *`401`* → run `device_setup.py` and re-flash. *No data but connected* → firewall profile, a changed laptop IP (use `server <url>`), or client isolation. *Erratic SpO₂* → pressure too hard, cold finger, strong ambient light. *Temperature stuck at ambient* → the probe is not touching skin or the arm is not held down. *`0x57` missing* → V6.

## Results

| Step | Date | PASS / FAIL | Observed numbers and notes |
|---|---|---|---|
| T-1 | | | |
| T0 | | | |
| T1 | | | |
| T2 | | | |
| T3 | | | |
| T4 | | | |
| T5 | | | |
| T5b | | | |
| T6 | | | |
| T7 | | | |
| T8 | | | |
| T9 | | | |
| T10 | | | |
| T11 | | | |
| T12 | | | |
| T13 | | | |
| T13a | | | |
| T13b | | | |
| T14 | | | |
