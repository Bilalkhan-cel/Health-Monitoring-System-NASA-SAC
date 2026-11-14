# AstroVital

**Beyond Earth. Always in Health.**

Astronaut health monitoring, self-assessment and an AI flight doctor (Dr. NOVA, powered by OpenHome).
A prototype for educational purposes, inspired by the NASA Human Research Program.
**Not a certified medical device.**

Three quick daily checks (heart, bones and muscle, mind), a 3D body twin that glows by status, a live
ESP32 wearable, a voice doctor that knows your data, history with a one-page "Downlink Report" for the
ground, and a Mission Control view for the flight surgeon. It runs on one computer, offline-first.

## What is measured and what is generated

Heart rate, SpO₂ and temperature come from the connected wearable when it is present. Blood pressure,
glucose, respiration and the ECG-style trace are **generated for demonstration** because no sensor for
them is attached. The app never labels a number by where it came from on screen, so this is said here,
in Settings → About and in the demo script. Alert rules are cautious placeholders that need calibration
on the real hardware and clinical review. An alert, or the absence of one, is never medical advice.

## Run it

You need Python 3.10–3.13 (built and tested on 3.13) and an internet connection for the first setup.

```bash
python scripts/setup.py
```

```bash
python run.py
```

Then open http://localhost:5000 and log in with **AST-1001** (also AST-1002, AST-1003; the flight
surgeon is **FS-9001**). There is no sign-up: the crew is listed in `.env` (`REGISTERED_ASTRONAUTS`).

`scripts/setup.py` is safe to run again at any time. It creates `.venv`, installs the pinned packages,
creates `.env` with generated secrets, fetches fonts and the local ML models (about 1 GB, in
`ml_models/`) and runs a self-check. A failed download never blocks the app; the matching feature
uses its fallback. Options: `--skip-models`, `--skip-ml`, `--no-venv`.

No API key is needed to start. `run.py` prints a checklist of what is ready and how to fix anything
that is missing. First start seeds 30 days of demo history (`SEED_ON_FIRST_RUN=true`).

## Pages

| Page | What it does |
|---|---|
| `/` | Cinematic landing: live 3D Earth with NASA's ISS model, the hologram twin, the three checks |
| `/dashboard` (Today) | Readiness, per-system scores, the 3D twin, live wearable strip, daily tasks, alerts |
| `/cardio` (Heart) | Rest check, then a streamed session from the wearable, a Bluetooth strap or typed readings |
| `/musculoskeletal` (Body) | Webcam rep counting and form cues (MediaPipe, on this computer; video never stored) |
| `/mental` (Mind) | Voice or typed check-in, local Whisper + sentiment/emotion, wellbeing score, safety screen |
| `/doctor` (Dr. NOVA) | Text and voice consultation grounded in your data |
| `/history` | Filters, calendar heatmap, trend charts, CSV export, Downlink Report PDF |
| `/notifications` | Reminders, results and alerts; the bell polls every 30 s |
| `/settings` | Units, reminders, voice cues, reduce motion, Wearable panel, privacy, badges, About, Demo panel |
| `/mission-control` | Flight surgeon only: crew status colours, flags, read-only physiology; every view audited |

## Dr. NOVA on OpenHome

Works out of the box in practice mode (offline rules engine). To connect the real voice agent, follow
**[docs/OPENHOME_SETUP.md](docs/OPENHOME_SETUP.md)**: create the agent, run a `cloudflared` tunnel,
`python scripts/build_openhome_ability.py`, upload the zip, restart.

## The wearable (ESP32 + MAX30102 + DS18B20)

1. Wire and flash it: [firmware/README.md](firmware/README.md) (pre-power checks first).
2. Join the laptop and the ESP32 to the same **2.4 GHz** network (a phone hotspot works), then:
   ```bash
   python scripts/device_setup.py
   ```
   It picks this computer's LAN address, asks for the Wi-Fi name and password and writes
   `firmware/include/secrets.h` (git-ignored). `--show` prints the URL the wearable should use;
   `--firewall` prints the Windows firewall rule (never runs it).
3. Probe under the arm for 10 minutes, finger on the sensor: values appear on Today within about 10 s
   and clear within 2 s of lifting the finger. Calibrate temperature in Settings → Wearable.
4. Record results in [docs/HARDWARE_TEST.md](docs/HARDWARE_TEST.md) and
   [docs/HARDWARE_FACTS.md](docs/HARDWARE_FACTS.md). **Status: needs hardware** (not yet tested on
   physical parts).

No hardware? `python scripts/device_emulator.py --profile normal` posts firmware-shaped frames to the
real ingest route (profiles: `normal`, `no_finger`, `finger_flap`, `weak_signal`, `spike`, `flatline`,
`probe_missing`, `probe_ambient`, `probe_warming`, `wifi_gap`, `duplicate`, `bad_token`, `malformed`,
`flood`, `restart`). Or switch Settings → Demo panel → Wearable mode → **Demo data**. The mode only
ever changes by hand, and every change is audited.

## 6-minute demo script

Full version: Appendix D of [PROMPT.md](PROMPT.md); it runs end to end as `tests/test_demo_script.py`.

1. **Landing.** Scroll: Earth and the ISS, three checks, spin and tap the hologram, Dr. NOVA,
   "22 minutes away".
2. **Login** with AST-1001 (show that a wrong ID is rejected).
3. **Today.** Say: *"Heart rate, oxygen and temperature come from this wearable. We have no sensor for
   blood pressure, glucose, breathing rate or the ECG-style trace, so those are generated for the
   demo."* Finger on, numbers appear; finger off, they clear. Tap the chest, then the head.
4. **Heart** check (rest is shortened in Demo Mode). 5. **Body:** five push-ups on camera.
6. **Mind:** a 60-second voice check-in. 7. **Dr. NOVA:** "How am I doing?", then Settings → Demo
   panel → **Critical BP event** to show escalation with the 14-minute comms delay.
8. **History** heatmap → **Downlink Report PDF** → log in as FS-9001 for **Mission Control**.

## Privacy

Vitals, camera and microphone analysis run on this computer; the wearable talks only to it over your
local Wi-Fi. Video is never stored. Audio is deleted once read; transcripts are off by default.
Settings → Privacy deletes all mental-health data (check-ins, Dr. NOVA conversations, wellbeing
scores) and recalculates readiness. Only Dr. NOVA's voice uses OpenHome's cloud, and it sees only
what is listed on the Dr. NOVA page. Secrets live only in `.env`, which is git-ignored, as are
`firmware/include/secrets.h` and `build/`.

## Commands

| Command | What it does |
|---|---|
| `python scripts/verify.py --quick` | Setup sanity check |
| `python scripts/verify.py --phase N` | Cumulative gate for phases 0..N; writes `docs/verify_last.md` |
| `python scripts/verify.py --full` | Every phase plus the performance budgets |
| `python -m pytest` | The test suite |
| `python scripts/fetch_assets.py` | Re-fetch vendored fonts and libraries (checksum-verified) |
| `python scripts/download_models.py` | Re-download and verify the ML models |
| `python scripts/build_openhome_ability.py` | Build the Dr. NOVA Ability zip (rotates the bridge token) |
| `python scripts/device_setup.py` | Wearable Wi-Fi and server address |
| `python scripts/device_emulator.py --profile normal` | Fake wearable over HTTP |
| `python scripts/device_check.py` | Is the server reachable, is the token valid, when did the wearable last send |

## Stack

Flask 3, Jinja2, SQLAlchemy on SQLite (WAL), plain HTML, CSS and vanilla JavaScript. Vendored and
checksum-pinned: Chart.js, GSAP, three.js (bundled at build time), MediaPipe Tasks Vision, Lucide
icons, Geist fonts. Local ML: faster-whisper, Hugging Face sentiment and emotion models. One process
(`threaded=True`, no reloader).

## Docs

- [docs/PROGRESS.md](docs/PROGRESS.md): phase-by-phase status and the last verify result
- [docs/DECISIONS.md](docs/DECISIONS.md): decisions and deviations from the specification
- [docs/UI_CRITIQUE.md](docs/UI_CRITIQUE.md): design critique and accessibility audit
- [docs/OPENHOME_SETUP.md](docs/OPENHOME_SETUP.md): connecting Dr. NOVA
- [PROMPT.md](PROMPT.md): the full specification
