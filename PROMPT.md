# ASTROVITAL — MASTER BUILD PROMPT v3.2 (SINGLE FILE, SELF-DRIVING BUILD, WITH ESP32 WEARABLE)
### Astronaut Health Monitoring, Self-Assessment & AI Flight Doctor (powered by OpenHome)

> **How to use:** paste this entire file into your coding AI (Claude Code, Cursor, Windsurf…) or save it as `PROMPT.md` in an empty folder and say *"Read PROMPT.md and build it."* Nothing else is needed. The AI builds the whole system by itself, one phase at a time, in a **Plan → Design → Execute → Monitor → Optimize** loop (Section 0.1), and keeps its own state in `docs/PROGRESS.md`. If the session stops, start a new one with *"Read PROMPT.md and docs/PROGRESS.md and continue."* API keys are optional: the finished app runs without them (OpenHome off, rule-based doctor); add keys later in `.env`. The ESP32 wearable (MAX30102 + DS18B20) is optional too: everything is built and verified first with a device emulator, and the physical bring-up (Appendix G) is the last step. v3.2 adds the wearable in **Section 10A**, uses the owner-confirmed hardware facts (Appendix H), and gates the emergency alerts for wearable heart rate and typed-in SpO₂ (Section 9.7). Every other section has been updated to match.

**Project name:** ASTROVITAL  
**Tagline:** *Beyond Earth. Always in Health.*  
**Hero question:** *Astronaut, are you mission-ready?*  
**AI doctor:** **Dr. NOVA**, the AI Flight Surgeon Assistant, a voice agent running on **OpenHome**

---

## 0. YOUR ROLE AND RULES OF ENGAGEMENT

You are a senior full-stack engineer, Python/Flask architect, ML/CV engineer, voice-AI integrator, and award-winning UI/UX + WebGL designer. Build a **complete, connected, runnable prototype**. It should feel like software a crew could plausibly use on the ISS, in an Orion capsule, or at a Mars base. It is not a hospital-management CRUD app, and it should not look like a gaming site.

**Non-negotiable rules**

1. **Inspect first, then resume.** If `docs/PROGRESS.md` exists, read it and continue from the recorded step. Otherwise, if the directory already contains code, models or assets, read them before writing anything, preserve what works, and don't rewrite for the sake of it. If the directory is empty, scaffold from Section 4 and create `docs/PROGRESS.md` and `docs/DECISIONS.md`.
2. **Everything visible must work.** No dead buttons, fake links, or decorative controls. If a feature can't be finished, hide it behind a clearly labeled "Coming soon" state that doesn't look clickable.
3. **Never fake data or connections, and keep the source out of the UI.** Internally every reading carries a `source` (`sensor`, `derived`, `manual`, `simulated`, `cv`, `nlp`, `voice`) and the database keeps it. That classification is **data-handling metadata, not interface**: do not render source badges, tags, legends, colours or suffixes anywhere in the app, and do not return a `source` field from browser-facing routes, charts or exports. A metric shows its name, value, unit, status word and timestamp, nothing else. The honesty duties are met in other ways: never describe a number with a measurement method its source does not support (for example, never say the wearable measured blood pressure, glucose or an ECG); never show a ✓ for a device that is not really connected; never present a stale reading as current; Dr. NOVA answers truthfully when asked how a number was obtained; and the README, the demo script and Settings → About state which attributes are generated (Section 16).
4. **Scientifically responsible.** Sentiment analysis is not a psychiatric diagnosis. Camera exercise tracking does not measure bone mineral density. Thresholds are prototype values in a config file, cited and editable. The AI doctor never invents readings, never diagnoses definitively, and never prescribes drugs or doses.
5. **Plug and play for the end user.** The complete user path is exactly:
   `python scripts/setup.py` → `python run.py` → open `http://localhost:5000`.
   - `scripts/setup.py` is idempotent and cross-platform (Windows/macOS/Linux). It installs `requirements.txt`, creates `.env` from `.env.example` with a freshly generated `FLASK_SECRET_KEY` and bridge token, fetches any missing vendored assets (`scripts/fetch_assets.py`) and ML models (`scripts/download_models.py`), and finishes by running `scripts/verify.py --quick`. If a download fails (offline, proxy), it prints a clear message, continues, and the app still starts in a degraded-but-working mode.
   - `run.py` bootstraps by itself on every start: creates or upgrades the database, upserts the crew and the wearable's `Device` row from `.env`, seeds 30 days of demo history on first run (if `SEED_ON_FIRST_RUN=true` and the DB is empty), prints the boot checklist (Section 3), and serves the app on `BIND_HOST` (`0.0.0.0` when `DEVICE_ENABLED=true` so the ESP32 can reach it, otherwise `127.0.0.1`). No API key is required to boot.
   - **Wearable (optional, hardware only): one extra command, `python scripts/device_setup.py`.** It detects this computer's LAN address, asks only for the Wi-Fi name and password, writes the git-ignored `firmware/include/secrets.h` and prints the flash command. (`pip install platformio` is a developer tool for flashing, not part of the end-user path.) With no wearable the app is still complete.
   - **No Node.js for the end user.** Node is a build-time tool for you (the AI). All vendored JS/CSS, fonts, optimized models and textures are produced during the build and committed into the project. If Node or the network is unavailable and an asset is missing, use the documented fallback (procedural station, poster image, system font) and log it in `docs/DECISIONS.md`.
   - ML models live **inside the project folder** (`ml_models/`) and load with `local_files_only=True`. Use lightweight models, lazy loading behind a lock, cached instances, and background threads for heavy inference.
6. **Offline-first.** Everything except the OpenHome doctor (and its LLM fallback) works with no internet (the wearable needs only your local Wi-Fi network, not internet). Vendor all JS, CSS, **fonts** and icons into `static/vendor/`. No CDNs at runtime.
7. **Run the build loop (Section 0.1) for every phase.** Never mark a phase done without a green exit gate from `python scripts/verify.py --phase N`.
8. **Code quality.** Type hints, docstrings, small functions, Blueprints + service layer (no business logic in routes), config-driven, structured logging, no secrets in code.
9. **Don't stall.** Don't wait for the user between phases. If something external is missing (an OpenHome key, a model download, a tunnel), build against the mock or fallback, record it in `docs/DECISIONS.md`, and continue. Ask the user only for credentials or for approval of a destructive action.
10. **Report honestly.** At every checkpoint, state what verify actually printed. Never claim something works that you did not run.
11. **Hardware honesty.** You cannot touch the ESP32. Build and verify everything you can with the emulator, mark anything that needs the physical device as "needs hardware" in `PROGRESS.md`, and never write "verified on hardware" unless Appendix G was actually run and its numbers recorded. Appendix H lists which hardware facts the owner confirmed and which still need a physical test: never state a "needs physical test" item as a fact, never recommend modifying a board without a verified reason, and keep `docs/HARDWARE_FACTS.md` honest.

### 0.1 THE BUILD LOOP (applies to every phase in Section 21)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PLAN → DESIGN → EXECUTE → MONITOR → OPTIMIZE ─┐                           │
│   ▲                                           │ exit gate green?          │
│   └──── loop (max 3 per phase) ◄── no ────────┘      yes → CHECKPOINT → next phase
└──────────────────────────────────────────────────────────────────────────┘
```

| Step | What you do | Artifact |
|---|---|---|
| **PLAN** | Read the phase's row in Section 21 and the sections it references. List the files to create or change, the acceptance checks, the top 3 risks, and the smallest vertical slice that proves the phase (e.g. one metric end to end before all metrics). | Update `docs/PROGRESS.md` → "Current phase plan" |
| **DESIGN** | Before coding, write down the interfaces for this phase: function signatures, JSON shapes, DB columns, route contracts, UI states (empty / loading / error / offline / success). For UI, decide the states first. Write only what's needed in `docs/DECISIONS.md` if you deviate from this brief. | Short design note in `PROGRESS.md`; types/stubs in code |
| **EXECUTE** | Build the vertical slice first, make it run, then widen it. Write the tests for that slice in the same loop (not at the end). Small commits (if git is available): `phase-N: <what>`. | Code + tests |
| **MONITOR** | Run `python scripts/verify.py --phase N`. It must cover: (1) `pytest`, (2) app boot with a clean DB, (3) Flask-test-client smoke test of every route in Section 18 for each crew member and for an anonymous user (no 5xx; anonymous gets a redirect or 401), (4) log scan for tracebacks and `WARNING`s you didn't expect, (5) forbidden-pattern scan (CDN URLs, `|safe`, secrets, `console.log` leftovers, `print(` in app code), (6) asset and performance budgets (below), (7) `node --check` on JS modules if Node exists, (8) from Phase 3 on, the device-emulator contract run and the `pio run -d firmware` compile (if PlatformIO is available), (9) the **label scan**: no rendered page, template, JS bundle or browser-facing JSON may contain a source label (`SENSOR`, `DERIVED`, `SIMULATED` or `SIM` as uppercase tags, or the words "simulated" / "demo data" outside Settings → About and the Settings → Demo panel) or a `source` key (the Dr. NOVA bridge payload and database internals are exempt). **If a browser tool is available, also open the pages, read the console for errors, check the status colours and layouts against Section 5, and measure FPS on the 3D pages.** Record the table of results in `PROGRESS.md`. | `docs/verify_last.md` |
| **OPTIMIZE** | Fix every failing check, then fix the single biggest weakness you measured (slowest endpoint, heaviest asset, flakiest ML result, worst UX state) and re-run MONITOR. Refactor only what the measurements justify. | Fixes + a one-line "what improved, by how much" |
| **CHECKPOINT** | When the gate is green (or after 3 loops: record the remaining issues under "Known limitations" and move on), update `PROGRESS.md`, then send the user a 5-line summary: what was built, how to test it, verify results, known limitations, next phase. Continue immediately. | Updated `PROGRESS.md` |

**Budgets checked by verify (fail = loop again):** `/api/summary` p95 < 300 ms on seed data · page HTML first byte < 500 ms · optimized ISS glb ≤ 15 MB · any single JS module ≤ 400 KB (vendored libraries excluded) · landing JS+CSS ≤ 1.5 MB excluding models/textures · pose round-trip logged (see Section 11) · no console errors on any page · from Phase 3: `POST /api/device/ingest` p95 < 50 ms · device-to-browser latency < 1.5 s (emulator) · `/api/summary` p95 < 300 ms with 30 days of history plus 7 days of raw frames.

**`docs/PROGRESS.md` template (create in Phase 0):**

```md
# PROGRESS
Current: P<n> · loop <k>/3 · step: <PLAN|DESIGN|EXECUTE|MONITOR|OPTIMIZE>
| Phase | Status | Loops | Gate |
## Current phase plan   (files, acceptance checks, risks, slice)
## Design notes         (interfaces, JSON shapes, UI states)
## Last verify result   (paste docs/verify_last.md summary)
## Known limitations    (accepted, with reason)
## Next action         (one concrete sentence a fresh session can resume from)
```

**`scripts/verify.py`** is created in Phase 0 and extended in every phase. It accepts `--quick` (setup sanity), `--phase N` (cumulative gates 0..N) and `--full` (everything + perf budgets). It exits non-zero on failure and writes `docs/verify_last.md`.

---

## 1. PROBLEM STATEMENT (context you must design around)

Space missions are getting longer (Artemis lunar missions, planned Mars missions). NASA's Human Research Program groups the risks of spaceflight into **five hazards**, remembered as **RIDGE**:

| Hazard | What it does to the body | Indicator(s) we track |
|---|---|---|
| **R**adiation | Raises long-term cancer and cardiovascular risk, CNS effects, immune changes | Cardio trends, fatigue, mood |
| **I**solation & confinement | Behavioral-health decline, stress, sleep disruption, team friction | Mood/wellbeing score, sleep |
| **D**istance from Earth | Communication delay (Mars up to ~22 min one way), limited medical evacuation, so **crew must self-assess** | Everything; alerts include comms delay |
| **G**ravity fields | Bone loss (~1–1.5 %/month in microgravity), muscle atrophy, fluid shift to the head, cardiovascular deconditioning | HR, BP, exercise loading index |
| Hostile/closed **E**nvironment | CO₂, temperature, noise, microbes, altered circadian light | Temperature, SpO₂, sleep |

**Objective:** a *visual* tool that lets astronauts assess their own health and gives plain-language guidance on what to do. Don't assume astronauts know how to assess their own health. Every number needs a "what is this / why it matters in space / normal range / what to do" explanation.

**Inputs:** keyboard, clicks, camera, microphone, a Wi-Fi wearable (ESP32 + MAX30102 pulse/SpO₂ sensor + DS18B20 temperature probe, Section 10A), a Bluetooth heart-rate strap where available, and manual entry. Attributes that no available sensor can measure (blood pressure, glucose, respiration, the ECG-style trace) are generated for the prototype (10A.9).

**Must include:** animation, interactivity, a clickable 3D human figure, color-coded status, dynamic charts, simple instructions, a mission routine with reminders, gamification, environment awareness (spacecraft / station / rover / lunar base / Mars base).

---

## 2. TECH STACK (fixed)

| Layer | Choice |
|---|---|
| Backend | **Python 3.10–3.12 recommended (3.13 tested last), Flask 3** (app factory, Blueprints, service layer). Run threaded, reloader off: `app.run(host=BIND_HOST, threaded=True, use_reloader=False)` |
| DB | **SQLite** via **Flask-SQLAlchemy** + **Flask-Migrate**; engine options: WAL mode, `busy_timeout`, `check_same_thread=False`. Keep `DATABASE_URL` configurable (Postgres later) |
| Realtime | **Server-Sent Events** through an in-process `StreamHub` for live vitals (`/api/stream`) and the cardio session stream (`/cardio/stream`); **flask-sock** WebSocket for the OpenHome voice proxy; notifications by **polling** `/api/notifications/poll` every 30 s (no scheduler dependency). Single process only (say so in the README) |
| Security libs | **Flask-WTF** (CSRF), **Flask-Limiter** (memory storage) |
| Frontend | **Jinja2 templates, HTML5, CSS3, Bootstrap 5 (grid/utilities only, custom theme on top), vanilla JS ES modules** |
| Fonts / icons | **Geist**, **Instrument Serif**, **Geist Mono** self-hosted as woff2 in `static/vendor/fonts/` (fetch from the `@fontsource` packages at build time); **Lucide** vendored SVG sprite |
| Charts | **Chart.js 4** + `chartjs-plugin-annotation` (status bands) |
| 3D / motion | **Three.js** (vendored) + `GLTFLoader` + `MeshoptDecoder`; **GSAP 3 + ScrollTrigger** (Lenis optional). Models optimized at build time with **@gltf-transform** + **meshoptimizer** (Node, build-time only) |
| Speech-to-text | **faster-whisper** (CTranslate2, int8 on CPU), weights in `ml_models/whisper/<size>/` |
| NLP | Hugging Face **transformers**, local: sentiment `cardiffnlp/twitter-roberta-base-sentiment-latest`, emotion `j-hartmann/emotion-english-distilroberta-base`. **English only**: say so in the UI and fall back to the self-rating plus lexicon for other languages |
| Computer vision | **Default `POSE_BACKEND=mediapipe`**: MediaPipe Pose Landmarker (client-side WASM + `pose_landmarker_lite.task`, vendored). Frames never leave the browser; only keypoints are sent. **Optional `hf_vitpose`**: `usyd-community/vitpose-base-simple` (`VitPoseForPoseEstimation`, `transformers>=4.51`) in `ml_models/pose/`, downloaded only with `download_models.py --with-vitpose`; for stronger machines |
| AI Doctor | **OpenHome** voice agent ("Personality") + a custom **OpenHome Ability** that pulls the astronaut's data from Flask. Optional OpenAI-compatible LLM fallback. `OPENHOME_MOCK=true` swaps in a local mock for development and tests |
| Audio | Browser **AudioWorklet** captures 16 kHz mono Int16 PCM and uploads **WAV** chunks. `ffmpeg` is optional (only for uploaded media-file fallbacks). **No pydub** |
| Wearable | **ESP32 DevKit** + **MAX30102** (heart rate, SpO₂) + **DS18B20** (temperature). C++/Arduino firmware built with **PlatformIO** (`pip install platformio`); libraries SparkFun MAX3010x, DallasTemperature + OneWire, ArduinoJson |
| Device link | **HTTP + JSON at 1 Hz over the local Wi-Fi** to `/api/device/ingest` with a shared-secret header. Optional discovery with **zeroconf** (mDNS `_astrovital._tcp`, guarded import). No MQTT, no WebSocket, no cloud |
| Auth | Flask session, Astro IDs pre-registered via `.env`, CSRF via Flask-WTF |
| PDF export | **reportlab** (Downlink Report). No WeasyPrint (system-library pain on Windows) |

> **Important correction carried over from the original brief:** "open home API" means **OpenHome** (app.openhome.com), a voice-AI agent platform. It does **not** mean an OpenAI-compatible key. Build the doctor on OpenHome. An OpenAI-compatible LLM is only a *fallback*.

---

## 3. ENVIRONMENT CONFIG

`.env.example` (copied to `.env` by `setup.py`; `.env` is in `.gitignore`):

```env
# ── Flask ───────────────────────────────────────────────
FLASK_SECRET_KEY=                              # setup.py generates one; run.py also generates a dev key if empty
FLASK_DEBUG=0                                  # (FLASK_ENV is obsolete in Flask 3)
DATABASE_URL=                                  # empty = <project>/instance/astrovital.db (absolute path built in config.py)
PUBLIC_BASE_URL=http://localhost:5000          # set to your tunnel URL (cloudflared/ngrok) so OpenHome can reach /api/openhome/*
TRUSTED_HOSTS=localhost,127.0.0.1              # Host headers allowed to reach the full app. Any other host (the tunnel) only reaches /api/openhome/* and /healthz. /api/device/* has its own LAN rule (below)
BIND_HOST=                                     # empty = 0.0.0.0 when DEVICE_ENABLED=true (so the ESP32 can reach Flask), otherwise 127.0.0.1

# ── Crew (registered by Mission Control HQ; no sign-up page exists) ─
# Format: ASTRO_ID:Full Name:Role:Callsign   (comma-separated; fields must not contain ':' or ',')
REGISTERED_ASTRONAUTS=AST-1001:Cmdr. Sara Whitman:Commander:Falcon,AST-1002:Dr. Leo Marquez:Flight Engineer:Atlas,AST-1003:Aisha Rahman:Mission Specialist:Nova
FLIGHT_SURGEON_IDS=FS-9001:Dr. Grace Okafor:Flight Surgeon:Hippocrates   # same 4-field format; optional Mission Control view

# ── Mission ─────────────────────────────────────────────
MISSION_NAME=ARES-SURFACE-01
MISSION_START_DATE=2026-06-01                  # Day 1 = this date
MISSION_DAY_OVERRIDE=160                       # demo: pin the mission day (empty = computed from the start date)
DEFAULT_ENVIRONMENT=Mars Base                  # Spacecraft | Space Station | Rover | Lunar Base | Mars Base

# ── OpenHome AI Doctor (Dr. NOVA) ───────────────────────
OPENHOME_API_KEY=                              # app.openhome.com → Settings → API Keys
OPENHOME_AGENT_ID=                             # the Dr. NOVA personality/agent id
OPENHOME_VOICE_WS=wss://app.openhome.com/websocket/voice-stream/{api_key}/{agent_id}
OPENHOME_BRIDGE_TOKEN=                         # build_openhome_ability.py generates and rotates this on every push
OPENHOME_ENABLED=true
OPENHOME_MOCK=false                            # true = local mock voice/text server (no keys needed)

# ── Optional LLM fallback (used only if OpenHome is unreachable) ─
FALLBACK_LLM_API_KEY=
FALLBACK_LLM_BASE_URL=https://api.openai.com/v1
FALLBACK_LLM_MODEL=gpt-4o-mini

# ── Local ML ────────────────────────────────────────────
WHISPER_MODEL_SIZE=base                        # tiny | base | small
WHISPER_MODEL_PATH=ml_models/whisper           # a <size> subfolder is expected inside
WHISPER_COMPUTE_TYPE=int8
NLP_SENTIMENT_PATH=ml_models/sentiment
NLP_EMOTION_PATH=ml_models/emotion
POSE_BACKEND=mediapipe                         # mediapipe | hf_vitpose
POSE_MODEL_PATH=ml_models/pose
MENTAL_SESSION_TARGET_MIN=3                    # recommended daily check-in length
MENTAL_SESSION_MIN_SECONDS=60                  # shortest valid analysis (demo may lower it)
MENTAL_SESSION_MAX_MIN=20                      # hard cap
CARDIO_SESSION_SECONDS=90
STORE_TRANSCRIPTS=false                        # privacy by default: scores + summary only

# ── Wearable (ESP32 + MAX30102 + DS18B20), see Section 10A ─────────
DEVICE_ENABLED=true
DEVICE_TOKEN=                                  # setup.py generates it; device_setup.py copies it into firmware/include/secrets.h
DEVICE_ID=AV-ESP32-01
DEVICE_WEARER_ID=AST-1001                      # Astro ID the wearable is bound to (changeable in Settings)
DEVICE_AUTO_REGISTER=false                     # true = accept unknown device_ids that carry the right token
DEVICE_HOSTS=                                  # extra Host names allowed for /api/device/* (for example astrovital.local)
DEVICE_LAN_IP=                                 # empty = auto-detect and confirm in device_setup.py; set it to pin the address when the laptop has several adapters
DEVICE_RATE_LIMIT=120/minute
SENSOR_MODE=device                             # device | demo. Initial value only; afterwards Mission.sensor_mode decides. Changed by hand only, never automatically
ZEROCONF_ENABLED=true                          # advertise _astrovital._tcp so the ESP32 can find the server; failure is non-fatal
LIVE_STALE_S=5                                 # a live value older than this is treated as no signal
DEVICE_OFFLINE_S=10
BACKLOG_LIVE_MAX_S=30                          # frames older than this on arrival are history only, never live
FINGER_SETTLE_S=8
MIN_SIGNAL_QUALITY=50
AGG_WINDOW_S=60
AGG_MIN_VALID=20
RAW_RETENTION_DAYS=7
TEMP_SITE=axilla                               # axilla | skin (skin needs its own offset)
TEMP_OFFSET_C=0.6                              # added to the raw probe reading to estimate body temperature; calibrate in Settings
TEMP_CONTACT_MIN_C=30.0
TEMP_SETTLE_MIN_RAW_C=34.5                     # raise this in a room warmer than 30 °C
TEMP_SETTLE_SLOPE_C_PER_MIN=0.1
SIM_RECORD_INTERVAL_MIN=5
MEAL_TIMES=07:30,12:30,18:30                   # drives the generated glucose curve (mission clock = UTC)

# ── Demo ────────────────────────────────────────────────
DEMO_MODE=true                                 # Judge Mode scenario presets + force-status dev panel
SEED_DAYS=30
SEED_ON_FIRST_RUN=true
```

**Rules**

- On startup, parse `REGISTERED_ASTRONAUTS` and `FLIGHT_SURGEON_IDS` and upsert them into the DB. Malformed lines are skipped with a readable warning, never a crash. IDs not in `.env` can't log in.
- Never send `OPENHOME_API_KEY`, `FALLBACK_LLM_API_KEY` or `OPENHOME_BRIDGE_TOKEN` to the browser. All external calls go through Flask. Redact the OpenHome WebSocket URL (it contains the key) from every log line.
- **Host guard:** a `before_request` hook rejects (404) every request whose `Host` is not in `TRUSTED_HOSTS`, with two exceptions. (1) `/api/openhome/*` and `/healthz` are allowed on any host, which makes it safe to expose Flask through a tunnel for OpenHome without exposing the login page or health data. (2) **`/api/device/*` is allowed only when the `Host` header is an IP literal in a private, loopback or link-local range, or is listed in `DEVICE_HOSTS`, and the request carries no forwarding headers (`X-Forwarded-For`, `CF-Connecting-IP`, `Forwarded`).** A tunnel hostname can therefore never reach the device routes, while the ESP32 (which addresses the server by its LAN IP) can. Binding to `0.0.0.0` is safe because every other path still needs a trusted `Host`. Test this with a table: `localhost`, `127.0.0.1`, `192.168.1.23:5000`, `10.0.0.7`, `203.0.113.9`, `abc.trycloudflare.com`, `astrovital.local` (only with `DEVICE_HOSTS`) against `/login`, `/api/openhome/context`, `/api/device/ingest` and `/healthz`.
- `config.py` validates the env at boot and prints a readable checklist: ✓ DB, ✓ crew loaded (3), ✓ Whisper model found, ✓ MediaPipe assets found, ✗ OpenHome key missing → doctor runs in fallback mode. A missing optional thing is a ✗ line with the fix, never a crash. Add the wearable lines: `✓ Listening on 0.0.0.0:5000, wearable URL http://192.168.1.23:5000`, `✓ DEVICE_TOKEN set`, `✓ Wearable AV-ESP32-01 last seen 4 s ago` or `✗ No wearable seen yet → run scripts/device_setup.py, then Appendix G`, and `✓ Sensor mode: device` (or a clearly visible `! Sensor mode: DEMO DATA` line).

---

## 4. PROJECT STRUCTURE

```
astrovital/
├── run.py                         # entry point: bootstrap + serve
├── config.py                      # loads + validates .env
├── requirements.txt               # pinned
├── .env.example  .gitignore  README.md  PROMPT.md
├── docs/            PROGRESS.md  DECISIONS.md  verify_last.md  HARDWARE_TEST.md  HARDWARE_FACTS.md
├── config/
│   ├── thresholds.yaml            # ALL clinical ranges (Section 9.2, prototype, cited)
│   ├── recommendations.yaml       # advice per system × status × environment
│   ├── environments.yaml          # gravity, comms delay, exercise options + targets per environment
│   ├── safety_lexicon.yaml        # self-harm / crisis phrases for the mandatory safety screen
│   └── dr_nova_persona.md         # SINGLE source of the persona (Appendix A)
├── app/
│   ├── __init__.py                # create_app(), host guard, blueprints, extensions
│   ├── extensions.py              # db, migrate, csrf, sock, limiter
│   ├── bootstrap.py               # db upgrade/create, crew + Device upsert, first-run seed, upload sweeper, raw-frame purge, generated-data catch-up
│   ├── models.py                  # SQLAlchemy models (Section 17)
│   ├── auth/            routes.py  services.py  decorators.py
│   ├── landing/         routes.py
│   ├── dashboard/       routes.py                # /dashboard + /api/summary, /api/bodypart
│   ├── cardio/          routes.py  services.py
│   ├── musculoskeletal/ routes.py  services.py   # "Bone & Muscle"
│   ├── mental/          routes.py  services.py
│   ├── doctor/          routes.py  services.py   # chat, voice proxy, OpenHome bridge API
│   ├── history/         routes.py
│   ├── notifications/   routes.py  services.py
│   ├── devices/         routes.py                # /api/device/ingest, /api/device/ping, /api/live, /api/stream (Section 10A)
│   ├── mission_control/ routes.py                # optional flight-surgeon crew view
│   ├── services/
│   │   ├── thresholds.py          # classify(), personal-baseline deviation
│   │   ├── readiness.py           # Readiness Score
│   │   ├── measurements.py        # record(): the ONE write path (classify → AlertGate → alert rules → notify → SSE → gamification)
│   │   ├── alert_gate.py          # AlertGate: configurable gates for heart rate (resting session, quality, sustained run) and manual SpO2 confirmation (9.7)
│   │   ├── stream_hub.py          # in-process pub/sub behind every SSE endpoint
│   │   ├── sensors/               # base.py (SensorSource) · device_gateway.py · quality.py · live_state.py · aggregator.py
│   │   │                          # physiology.py (PhysiologyModel) · simulated.py (SimulatedSource, SimRecorder) · demo_wearable.py · manual.py
│   │   ├── whisper_service.py
│   │   ├── nlp_service.py         # sentiment + emotion + safety screen
│   │   ├── pose_service.py        # canonical keypoints → angles → rep state machines, cadence
│   │   ├── loading_index.py       # Musculoskeletal Loading Index
│   │   ├── openhome_service.py    # voice WS upstream, text call, health check, mock
│   │   ├── doctor_context.py      # builds the astronaut context JSON + prompt text (ONE path for voice and text)
│   │   ├── llm_fallback.py
│   │   ├── recommendations.py
│   │   ├── gamification.py
│   │   └── report_pdf.py          # Downlink Report export
│   ├── templates/  (base.html, landing.html, login.html, dashboard.html, cardio.html,
│   │                musculoskeletal.html, mental.html, doctor.html, history.html,
│   │                notifications.html, settings.html, mission_control.html, partials/*)
│   └── static/
│       ├── css/  theme.css  landing.css  app.css
│       ├── js/   astro3d.js            # mountHero / mountBody (Section 9.5); helpers in js/3d/ (earth.js, iss.js, twin.js, quality.js)
│       │         app/ (api.js [fetch wrapper + CSRF], charts.js, cardio.js, ble.js, exercise.js, pose_adapters.js,
│       │               mental.js, pcm_worklet.js, doctor_voice.js, doctor_chat.js, notifications.js, gamification.js, live.js, ecg_synth.js)
│       ├── vendor/ three, gsap, lenis, chart.js, mediapipe (wasm + .task), lucide, bootstrap, fonts/
│       ├── textures/  earth_day, earth_night, earth_clouds, earth_specular, stars  (2K and 4K tiers, WebP/JPG)
│       ├── models/    iss.glb  astronaut.glb  (meshopt-compressed; heart/brain are generated in code)
│       └── audio/     ui sounds (optional, muted by default)
├── openhome_ability/
│   ├── main.py.tmpl               # Dr. NOVA context Ability (Appendix B)
│   └── README.md
├── firmware/                      # ESP32 wearable (10A.3): platformio.ini, include/{config,pins,secrets.example}.h, src/*, test/, README.md
├── ml_models/   whisper/  sentiment/  emotion/  pose/        # git-ignored, filled by download_models.py
├── scripts/
│   ├── setup.py                   # one-command bootstrap for the end user
│   ├── verify.py                  # the Monitor step: phase gates, budgets, smoke tests
│   ├── fetch_assets.py            # Python-only: re-fetch vendored libs, fonts, textures, mediapipe files if missing
│   ├── download_models.py         # Whisper + sentiment + emotion (+ ViTPose with --with-vitpose)
│   ├── optimize_models.mjs        # BUILD-TIME ONLY (Node): NASA ISS glb → optimized iss.glb
│   ├── seed_demo_data.py          # 30 days of realistic history per astronaut
│   ├── device_setup.py            # lists LAN IPs, Wi-Fi prompt → firmware/include/secrets.h (--show, --firewall, --rotate)
│   ├── device_emulator.py         # pretends to be the ESP32 over real HTTP (profiles in 10A.11)
│   ├── device_check.py            # server reachable? token valid? age of the last frame
│   └── build_openhome_ability.py  # render main.py from template + persona, rotate token, zip, `openhome push`
├── instance/                      # sqlite db
├── uploads/                       # temp audio, auto-deleted after transcription; swept at startup
└── tests/                         # pytest (Section 19), incl. tests/mock_openhome.py and tests/fixtures/device_frames/
```

---

## 5. DESIGN SYSTEM: "CINEMATIC MINIMAL"

**References:** the cinematic 3D landing pages on motionsites.ai and vividsites.app. A near-black canvas, **one hero 3D object per view**, huge confident headlines whose second line is a grey italic serif, tiny pill controls, and almost no chrome. **Design for a layperson:** one idea per screen, plain words, only the important numbers. If a screen needs a legend to understand, simplify it.

**Rules**
- Black background, white text, hairline dividers. No glassy neon dashboards, no grids of 10 cards, no gauges for their own sake.
- Every number gets a plain verdict next to it ("104 bpm · usual 72 · A bit high"). Never show a number without saying whether it's okay.
- Colour only where it means something: the four status colours, plus one soft cyan for 3D glow.
- Every screen has one obvious primary action (a white pill button).
- Never show where a number came from: no source badges, legends, colours or suffixes (Section 0 rule 3).

### 5.1 Tokens (`theme.css`)

```css
--bg:#000000; --surface:rgba(255,255,255,.03); --surface-2:#07090D;
--line:rgba(255,255,255,.08); --line-strong:rgba(255,255,255,.16);
--text:#F2F4F7; --text-2:#A3ABB8; --text-3:#8E97A6;   /* all pass WCAG AA on black */
--primary-bg:#F2F4F7; --primary-fg:#050608;          /* white pill buttons */
--glow:#7CF3FF;                                       /* 3D hologram + orbit lines only */
--good:#2EE59D; --okay:#3B9EFF; --watch:#FFC53D; --alert:#FF4D6D;
--radius-pill:999px; --radius-card:24px; --radius-stage:32px;
```

**Typography (self-hosted, see Section 2):** **Geist** for everything (headlines 500 weight, letter-spacing −0.045em; huge numbers 200–300 weight). **Instrument Serif italic** in grey for the second line of headlines ("Beyond Earth. / *always in health.*"). **Geist Mono** only for tiny captions. Sizes: hero 104px, page titles 48–56px, big readings 96–200px, body 15–17px. Define a system-font fallback stack so the app is readable if a font file is missing.

**Components:** pill nav (rounded group, active tab = white pill), white primary pill, ghost pill, hairline list rows (label left, value right, verdict word in status colour), soft surface cards (radius 24, 1px line), status pill (tinted background + coloured word). Inline stroke icons (Lucide), never emoji **in the UI**. (Emoji dots in this brief are notation only.)

**Motion:** slow and calm. 3D scenes idle gently; sections fade up on scroll (CSS `animation-timeline: view()` or GSAP ScrollTrigger); the heart icon beats at the real BPM; voice orbs breathe. Respect `prefers-reduced-motion`.

### 5.2 Status system (same everywhere: lists, chart dots, body hotspots, notifications, Dr. NOVA)

| Internal status | Colour | Word shown to the astronaut | Meaning | Tone | Readiness points |
|---|---|---|---|---|---|
| NOMINAL | `--good` | **Good** | Optimal range | "Keep it up." | 100 |
| STABLE | `--okay` | **Okay** | Inside normal limits, or informational. **Not a problem state** | "Nothing to do." | 85 |
| CAUTION | `--watch` | **Needs attention** (or "A bit high/low") | Mild deviation | "Do this today." | 55 |
| CRITICAL | `--alert` | **Get help now** | Value that could be dangerous without prompt action | "Tell your crew medical officer now." | 20 |

Worst-of ordering: CRITICAL > CAUTION > STABLE > NOMINAL. Never use colour alone: always pair it with the word and an icon. Blue is never shown as worse than green *in colour weight* (both are calm); the word carries the difference. Every user-facing string (UI, notifications, Dr. NOVA speech) uses the **Word column**; the internal names appear only in code and JSON.

---

## 6. LANDING PAGE `/`: CINEMATIC 3D, SCROLL

### 6.1 3D assets (real, with graceful fallbacks)

- **ISS:** NASA's official model from **NASA 3D Resources** (`github.com/nasa/NASA-3D-Resources`, folder `3D Models/International Space Station (ISS) (D) (IGOAL)`, ~96 MB glb). *Verify the real path and file list before scripting; list the mesh names and print them.* `scripts/optimize_models.mjs` (build-time, Node) uses `@gltf-transform` + `meshoptimizer`: **remove only the tiny greeble meshes** (names matching `Details|Handrail|Handlebar|Lettering`; if none match, print the names and pick by vertex count), **keep original materials and textures** (resize to 1024 px WebP), lightly simplify (ratio 0.6, error 0.0008), quantize and meshopt-compress. **Budget: ≤ 15 MB, ≈ 780k vertices or fewer; the output is committed to `static/models/iss.glb`.** Load with `GLTFLoader` + `MeshoptDecoder` (no Draco). Keep the loaded materials, set max anisotropy, add a PMREM studio environment, pixel ratio up to 2 (capped by the quality tier). **Fallback:** if the download or optimization is impossible, ship a clearly labelled procedural station (trusses + panels) and record it in `DECISIONS.md`.
- **Earth:** a 192×96 sphere with a custom shader using the **NASA Blue Marble day map**, a **city-lights night map**, a **cloud map** (alpha as grayscale WebP) and an ocean specular mask. Blend day/night by the sun direction with a soft terminator, tight ocean sun-glint, drifting clouds lit by the sun, blue Fresnel haze, and a back-side atmosphere shell (radius ×1.07) with a warm lit side. Light from the left so the lit side faces the headline. Sources: three-globe example images (`earth-blue-marble.jpg`, `earth-night.jpg`, `clouds/clouds.png`) and three.js `earth_specular_2048.jpg`, or NASA Visible Earth. Ship **2K and 4K tiers**.
- **Quality tiers (`js/3d/quality.js`):** `high` (4K, clouds, full ISS, DPR ≤ 2), `med` (2K, clouds, DPR ≤ 1.5), `low` (2K, no clouds layer, DPR 1, ISS idle only). Pick automatically from a 1-second FPS probe, `devicePixelRatio` and `navigator.hardwareConcurrency`; allow `?q=low|med|high`. If WebGL is unavailable or `prefers-reduced-motion` is set, show a static poster image (generate one from the scene at build time) with the same layout. Pause rendering when the tab is hidden.
- **Body:** a rigged humanoid glb with an idle animation (e.g. three.js's `Xbot.glb`, or a Mixamo character; check the licence). Bone names vary by model: resolve bones by case-insensitive regex with fallbacks (`/spine2|spine_?02|chest/i`, `/head$/i`) and log which ones were found. See 9.5.

### 6.2 Sections (in scroll order; keep each to one idea)

1. **Hero (920px, full-bleed WebGL):** Earth fills the right half; the ISS drifts gently along an inclined orbit over Earth's limb (drift ±18°, never behind the planet); mouse parallax; scrolling dollies the camera toward the station. Left side, bottom-aligned: small status pill "Crew health system for long missions", H1 **"Beyond Earth." / *always in health.*"**, one-line sub ("Check your heart, bones and mind in a few minutes a day, guided by an AI doctor that knows your data."), white pill **Astronaut login**, ghost pill **How it works**. Pill nav centred at the top. Tiny mono caption: "ISS · NASA 3D model · live WebGL". *"Astronaut, are you mission-ready?" is used as the login-page eyebrow and the final CTA, not as the H1.*
2. **How it works:** "Three quick checks. / *A few minutes a day.*" Three columns divided by hairlines: Heart / Bones & muscle / Mind. Each has one tiny live visual (heartbeat line, pose dots + rep count, voice bars) and one sentence.
3. **Digital twin:** a large dark stage holding the **interactive hologram body** (same component as the dashboard) next to "Tap your body. / *See how it's doing.*", three system pills (Mind · Heart · Bones & muscle) and a small card that updates with a status word, one sentence and one "Do this" tip (from demo data).
4. **Dr. NOVA:** a breathing gradient orb, "A doctor who knows you. / *Just ask.*", one two-bubble sample conversation, and a single line: "Voice AI powered by OpenHome (cloud). It only sees what's listed under *What Dr. NOVA sees*, and it tells you to alert your crew medical officer when something is serious."
5. **Statement:** "Built for when Earth is / *22 minutes away.*" + three hairline-topped facts: **Local-first** (vitals, camera and microphone analysis run on this device, the wearable talks only to your own computer over your local Wi-Fi; only Dr. NOVA's voice uses the cloud), **Private** (video never saved, audio deleted once read, transcripts off by default), **Honest** (prototype, not a medical device, never diagnoses).
6. **CTA:** "Astronaut, are you / *mission-ready?*" white pill. One-line footer with the NASA HRP inspiration + "Prototype, not a medical device" + "ISS model: NASA 3D Resources".

No NASA logos or trademarks.

---

## 7. AUTHENTICATION `/login`

- Full-bleed WebGL: Earth's horizon rising from the bottom of the screen with the ISS passing above it (same scene component, different camera; same quality tiers and poster fallback).
- Centred minimal form: eyebrow "Astronaut, are you mission-ready?", "Welcome back, / *astronaut.*", one **Astro ID** field (mono, auto-uppercase), white pill **Continue**, tiny note "No sign-up. Crew accounts are set up by Mission Control."
- Invalid ID: gentle shake + "That ID isn't on this mission's crew list." Rate-limit with Flask-Limiter: 5 attempts/min per IP **and** per submitted ID.
- `@login_required` on every app route, `@surgeon_required` on `/mission-control`. Every query is scoped to `current_astronaut.id`. Session cookie: `HttpOnly`, `SameSite=Lax`, `Secure` when served over HTTPS.
- No sign-up route. Add `# SECURITY NOTE:` comments: ID-only login is a prototype shortcut; production needs MFA / badge / biometric auth. The host guard (Section 3) keeps the login page off the public tunnel.

---

## 8. APP SHELL (all logged-in pages)

- **Top bar only (no sidebar):** wordmark left; centred pill nav **Today · Heart · Body · Mind · Dr. NOVA · History** (routes `/dashboard`, `/cardio`, `/musculoskeletal`, `/mental`, `/doctor`, `/history`); right: "Day 160 · Mars Base" (click = environment picker, see 9.4a) and an avatar (menu: Settings, Notifications, Log out).
- Critical alerts appear as one full-width red bar under the nav, written in plain words, with one button ("Tell crew medical officer" / "Ask Dr. NOVA").
- Footer line on every page: *"Prototype for educational purposes. Not a certified medical device."*

---

## 9. DASHBOARD `/dashboard` ("Today")

**Three columns, one screen, no scrolling on a 1440×900 display (at 1024 px: twin on top, panels stacked):**
- **Left:** date, "Good morning, / *Sara.*", a readiness card (one huge number, e.g. **74 / 100**, a thin bar, the caption *"Wellness estimate · not a fitness-for-duty decision"*, and one sentence like "Mostly good. One thing needs attention: your heart rate is higher than usual."), then **Today's checks** as a simple list (done ✓ / due with a Start button / later).
- **Centre:** the **3D Digital Twin** on a dark stage (Section 9.5), hint pill "Drag to turn · tap a glowing point", and three system pills underneath.
- **Right:** the selected system in plain language: status pill, a one-sentence headline ("Your heart is working harder than usual."), **at most three** key numbers as hairline rows (label · value · verdict; pick the three worst-status metrics of that system, ties by the order in 9.1a), "What to do" as three numbered steps, white pill to start that check, ghost pill **Ask Dr. NOVA**, and the Earth comms delay as a footnote.

Detailed per-metric cards, sparklines and charts live on the module pages and History, not on Today.

### 9.1 Indicators tracked (live from `/api/summary`, refresh every 30 s and immediately on an SSE `summary` event)

Heart Rate · Blood Pressure (sys/dia) · Blood Glucose · Body Temperature · SpO₂ · Respiration rate · Sleep (last night) · Mental Wellbeing · Musculoskeletal Loading Index · Hydration (optional, informational, no status).

Each card shows: large value + unit, status badge (colour + icon + word), 7-reading sparkline, trend arrow + delta vs personal baseline, "updated 2 h ago", and an ⓘ popover (*what it is · why it matters in space · normal range · what to do*). **No source badge, tag or legend** (Section 0 rule 3). Resting vitals (`heart_rate`, `systolic`, `diastolic`, `respiration`; flagged `requires_rest` in `thresholds.yaml`) carry a context (`resting` | `active` | `unspecified`); only `resting` readings are classified against resting ranges, and the cardio flow enforces the 5-minute rest instruction before starting. Live wearable values appear in the **Live strip** (10A.7), never as a status.

### 9.1a Indicator → body system mapping (drives hotspots, right panel and readiness)

| Hotspot (bone) | System id (`/api/bodypart/<id>`) | Metrics (ordered by priority) |
|---|---|---|
| Head | `mind` | wellbeing, sleep_hours |
| Chest | `heart` | blood pressure (systolic/diastolic), heart_rate, spo2, glucose, respiration, temperature, (hydration, informational) |
| Legs | `bones` | loading_index, last workout |

System status = worst-of its metrics' current statuses. Readiness uses the subsystem mapping in 9.3.

### 9.2 Thresholds: `config/thresholds.yaml` (prototype, adult, resting; editable)

Write this file **exactly** as below and load it in `services/thresholds.py`. Intervals are `[lo, hi)` (lower bound inclusive, upper exclusive, `null` = unbounded). **Every value must map to exactly one status.** `max_status` caps a metric's worst possible level.

```yaml
version: 1                       # stored on every Measurement as threshold_version
# Educational prototype ranges pending clinical validation.
# Sources: AHA resting HR 60–100; AHA/ACC 2017 BP categories (crisis ≥180 or ≥120 diastolic);
# ADA Standards of Care (glucose; the 100–110 split is a prototype UI subdivision);
# clinical convention (temperature, SpO2, respiration); AASM/NSF (sleep); prototype scales (scores).
# CRITICAL is reserved for values that could be dangerous without prompt action.

heart_rate:        # bpm, resting
  unit: bpm
  requires_rest: true
  nominal:  [[60, 91]]
  stable:   [[50, 60], [91, 101]]
  caution:  [[40, 50], [101, 130]]
  critical: [[null, 40], [130, null]]
systolic:          # mmHg
  unit: mmHg
  requires_rest: true
  nominal:  [[90, 120]]
  stable:   [[120, 130]]
  caution:  [[80, 90], [130, 180]]
  critical: [[null, 80], [180, null]]
diastolic:         # mmHg
  unit: mmHg
  requires_rest: true
  nominal:  [[60, 80]]
  stable:   [[55, 60]]
  caution:  [[50, 55], [80, 120]]
  critical: [[null, 50], [120, null]]
glucose_fasting:   # mg/dL (store canonical mg/dL; convert for display)
  unit: mg/dL
  nominal:  [[70, 100]]
  stable:   [[100, 110]]
  caution:  [[54, 70], [110, 250]]
  critical: [[null, 54], [250, null]]
glucose_post_meal: # mg/dL, 2 h after eating. The "random" context uses this table too
  unit: mg/dL
  nominal:  [[70, 140]]
  stable:   [[140, 160]]
  caution:  [[54, 70], [160, 250]]
  critical: [[null, 54], [250, null]]
temperature_c:     # °C
  unit: °C
  nominal:  [[36.1, 37.3]]
  stable:   [[35.8, 36.1], [37.3, 37.6]]
  caution:  [[35.0, 35.8], [37.6, 39.0]]
  critical: [[null, 35.0], [39.0, null]]
spo2:              # %
  unit: "%"
  max_status_by_origin: {wearable: CAUTION}   # the wearable alone can never produce CRITICAL (owner decision); other origins keep CRITICAL
  nominal:  [[96, null]]
  stable:   [[94, 96]]
  caution:  [[90, 94]]
  critical: [[null, 90]]
respiration:       # breaths/min
  unit: br/min
  requires_rest: true
  nominal:  [[12, 19]]
  stable:   [[10, 12], [19, 21]]
  caution:  [[8, 10], [21, 25]]
  critical: [[null, 8], [25, null]]
sleep_hours:       # hours, last night
  unit: h
  max_status: CAUTION
  nominal:  [[7, 9.1]]
  stable:   [[6, 7], [9.1, 10.1]]
  caution:  [[null, 6], [10.1, null]]
wellbeing:         # 0–100 prototype scale. CRITICAL only ever comes from the safety screen (Section 12)
  unit: score
  max_status: CAUTION
  nominal:  [[70, null]]
  stable:   [[55, 70]]
  caution:  [[null, 55]]
loading_index:     # 0–100 prototype scale
  unit: score
  max_status: CAUTION
  force_caution_after_days_without_exercise: 3
  nominal:  [[75, null]]
  stable:   [[60, 75]]
  caution:  [[null, 60]]

alert_confirm:     # the gates of 9.7. A range that says CRITICAL becomes "Get help now" only if its gate passes; otherwise it shows `unmet_status`. A gate can only LOWER a status.
  unmet_status: CAUTION               # Needs attention
  heart_rate:
    wearable:                         # the MAX30102 path. A single frame can never pass.
      require_resting_session: true   # only inside a cardio session that began after the rest countdown (Section 10)
      require_rest_verified: true     # the rest_verification checks below passed for that session
      rest_verification:              # prototype checks; there is no motion sensor, so these cannot prove stillness
        countdown_completed: true     # a skipped countdown (DEMO_MODE) never verifies rest
        min_valid_coverage: 0.8       # share of the last 60 s of the countdown with valid heart-rate frames
        max_hr_range_bpm: 15          # max minus min of the six 10 s medians in that minute
      min_quality: 60                 # q required on every frame of the run (frame validity itself is MIN_SIGNAL_QUALITY)
      consecutive_frames: 10          # 1 Hz frames in the CRITICAL range in a row; any invalid frame resets the run
      min_span_s: 10                  # and the run must span at least this many seconds
      outside_session_display: true   # outside a resting session a sustained run shows Needs attention on the live strip only
  spo2:
    wearable_notice_frames: 5         # valid frames below 94 % before the Needs attention notice (the wearable is capped at CAUTION)
    manual:                           # a typed-in value is never an emergency on its own
      confirmations_required: 2       # entries in the CRITICAL range needed, the first one included
      min_gap_s: 60                   # the confirming entry must come at least this long after the previous one
      window_min: 10                  # and within this long, otherwise the first entry expires
      symptom_override_confirms: true # ticking a symptom in the same form confirms at once (9.2)
  wearable_temperature_aggregates: 2  # consecutive 60 s aggregates, both settled
  generated_readings: 2

baseline:          # per-metric parameters for the personal-baseline layer (9.2a)
  heart_rate:   {floor: 3,   min_change: 8}
  systolic:     {floor: 4,   min_change: 10}
  diastolic:    {floor: 3,   min_change: 7}
  glucose_fasting: {floor: 8, min_change: 15}
  temperature_c: {floor: 0.2, min_change: 0.5}
  spo2:         {floor: 1,   min_change: 2}
  respiration:  {floor: 1.5, min_change: 3}
  sleep_hours:  {floor: 0.7, min_change: 1.5}
  wellbeing:    {floor: 6,   min_change: 12}
  loading_index: {floor: 6,  min_change: 12}
```

`services/thresholds.py` exposes `classify(indicator, value, context=None, origin=None) -> {status, color, label, icon, message, threshold_version}`. When `origin` has an entry in the metric's `max_status_by_origin`, the returned status is capped at that level (the message still tells the astronaut to re-measure). `classify` stays a pure function of the value; everything that needs time or history (consecutive frames, resting session, confirmation) lives in `AlertGate`, which reads the `alert_confirm` block and **can only lower a status, never raise one**. Glucose takes `context` of `fasting | post_meal | random`. **Blood pressure status = worst-of systolic and diastolic** (store both on one `Measurement` row using `value`/`value2`). The module docstring states these are **educational prototype ranges pending clinical validation** and cites the sources above.

**Symptom override:** the manual-entry and results screens offer an optional "I have chest pain / severe headache / vision changes / severe shortness of breath / fainting" checkbox group. Any tick sets the session to CRITICAL regardless of numbers and triggers the escalation text.

**Test requirement (mandatory):** a property test sweeps each metric from its minimum to maximum in 0.1 steps and asserts exactly one interval matches (no gap, no overlap); boundary tests assert `[lo, hi)` behaviour.

### 9.2a Personal-baseline layer

Spaceflight shifts physiology, so beyond the absolute ranges, compare each metric with the astronaut's own usual:

- **Window:** the 14 days ending 3 days ago (the latest 3 days are excluded so a developing trend doesn't contaminate the baseline). Need ≥ 7 daily values, otherwise show "baseline: building (n/7)" and apply nothing.
- **Robust z-score:** `z = (x − median) / max(1.4826 · MAD, floor)` using the metric's `floor` from the yaml (prevents division by zero and over-sensitivity).
- **Annotate** whenever `|z| ≥ 2` and `|x − median| ≥ min_change`: "Your resting heart rate is 32 above your usual (72)." Show both "vs normal range" and "vs your usual".
- **Escalate** a NOMINAL or STABLE metric to CAUTION only when `|z| ≥ 3` on 2+ consecutive daily values in the same direction. Baseline logic never produces CRITICAL by itself, and never changes a CAUTION/CRITICAL.
- The `HealthProfile.baseline_json` field stores only the computed cache (median, MAD, n, window dates).
- **Prefer measured data:** if ≥ 7 distinct days of measured rows (wearable or manual, with the right context) exist for a metric in the window, the baseline ignores generated rows (10A.8). Only `resting` heart-rate rows count toward the heart-rate baseline.

### 9.3 Readiness Score (0–100)

```
Subsystems and their metrics (only FRESH metrics count):
  cardio  (30 %): heart_rate, bp (worst of sys/dia, counted once), spo2, respiration, temperature, glucose   fresh ≤ 48 h
  bones   (25 %): loading_index                                                                              fresh ≤ 7 days
  mental  (25 %): wellbeing                                                                                  fresh ≤ 48 h
  sleep   (20 %): sleep_hours                                                                                fresh ≤ 36 h
subsystem_score = mean(points[status]) over its fresh metrics     # points: Section 5.2 (100/85/55/20)
readiness = Σ(weight_i · subsystem_score_i) / Σ(weight_i)         # over subsystems that have fresh data
caps: any fresh CRITICAL → readiness ≤ 49; any fresh CAUTION → readiness ≤ 79
if fewer than 2 subsystems have fresh data → show "Not enough data yet" and the checks to do (no number)
```

Display it as one huge number with a thin progress bar, the caption *"Wellness estimate · not a fitness-for-duty decision"*, and one plain sentence naming the lowest subsystem's worst metric. Store daily in `ReadinessDaily` (with the breakdown). The score is private to the astronaut; Mission Control sees only the status colour (Section 16).

### 9.4 Charts

Chart.js charts kept minimal: one smooth white line with a soft fade, dashed reference lines, and coloured dots only where something happened (each with a short label like "Oct 21 · blood pressure spike"). A row of daily status-coloured tiles sits under the chart. Range toggle: 7 d / 30 d / mission. Tooltips show value + plain verdict (never the source). Series are bucketed to ≤ 500 points (10A.8). Charts update immediately after a session is saved (custom `astro:data-updated` event). Every chart has an `aria-describedby` text summary.

### 9.4a Environment (mission-level, advice-only)

The environment (Spacecraft · Space Station · Rover · Lunar Base · Mars Base) is stored on the **Mission** (one source of truth). It changes: gravity shown, comms delay, available exercises and loading targets, and the wording of advice. **It never changes clinical thresholds.** For the prototype, any crew member may change it from the top-bar picker or Settings (the picker is a demo convenience; note this in a `# SECURITY NOTE`). `config/environments.yaml` defines per environment:

```yaml
Spacecraft:    {gravity_g: 0.0,   comms_delay_one_way_s: 600,  exercise: [device_log, treadmill_harness]}   # deep-space transit; scenarios may override the delay
Space Station: {gravity_g: 0.0,   comms_delay_one_way_s: 2,    exercise: [device_log, treadmill_harness]}   # ARED/cycle logged manually
Lunar Base:    {gravity_g: 0.166, comms_delay_one_way_s: 1.3,  exercise: [run, pushup, pullup, squat, device_log]}
Rover:         {gravity_g: 0.166, comms_delay_one_way_s: 1.3,  exercise: [run, pushup, squat, device_log]}   # lunar surface rover
Mars Base:     {gravity_g: 0.38,  comms_delay_one_way_s: 760,  exercise: [run, pushup, pullup, squat, device_log]}
# plus per environment: weekly_active_min_target, target_days, target_met, advice_notes
```

Defaults for targets (prototype): `weekly_active_min_target` Station/Spacecraft 420, Lunar/Rover 240, Mars 300; `target_days` 5; `target_met` 5.0. `Mission.comms_delay_s` (nullable) overrides the yaml value (used by Judge Mode scenarios).

### 9.5 Interactive 3D Digital Twin (centerpiece)

- **Model:** rigged humanoid glb playing its idle animation, scaled to 1.85 m (measure height from bone world positions, not skinned-mesh bounds).
- **Hologram look:** a translucent body material (MeshStandardMaterial + `onBeforeCompile` Fresnel rim, opacity ≈ 0.06), a faint **wireframe layer** sharing the same skeleton, the real rig drawn as glowing **skeleton lines** (`SkeletonHelper`), and a soft **scan band** that sweeps up the body every few seconds. Floor rings + soft disc under the feet. Slow auto-rotate with momentum drag-to-turn and a gentle zero-g bob.
- **Organs attached to bones:** an extruded **heart** on the chest/spine bone that beats at the astronaut's real BPM, and a wireframe **brain** on the head bone, both coloured by status.
- **Three hotspots** (invisible hit spheres parented to bones, so they follow the animation) with billboarded rings + pulsing halos in the live status colour: **Head → Mind**, **Chest → Heart**, **Legs → Bones & muscle** (metrics per 9.1a).
- Hover changes the cursor and enlarges the ring. Click (or the pills under the stage, for keyboard and screen-reader users) selects the system and updates the right-hand panel through an `onSelect` callback. Expose `select(name)` so the pills can highlight the 3D ring too.
- One reusable module `static/js/astro3d.js` exposing `mountHero(canvas, opts)` and `mountBody(canvas, opts)` (helpers in `js/3d/`), used by the landing page, login and dashboard. Pause rendering when the tab is hidden; cap DPR by quality tier (max 1.75 for the body). If WebGL fails, render a 2D SVG body with the same three clickable hotspots.

### 9.6 Daily mission checklist + gamification

Daily tasks: ☐ Cardio check · ☐ Exercise session · ☐ Mental check-in · ☐ Sleep log · ☐ Hydration/nutrition log. Reminders fire at configurable mission times (Settings): the server computes "due reminders" from settings + `DailyTask` and returns them from `/api/notifications/poll`; the client shows them as toasts and notifications (deduplicated).

- **XP** (per task completed, never dependent on the measured values, so there is no incentive to fake good numbers): cardio 30 · exercise 40 · mental 30 · sleep log 10 · hydration 10 · all five in a day +20. **Level** = `floor(sqrt(xp / 50)) + 1`.
- **Streak:** consecutive mission days (UTC date) with ≥ 3 of 5 tasks done.
- **Badges:** Iron Heart (7 cardio sessions in 7 days) · Titanium Bones (5 exercise days in a week) · Steady Mind (7 mental check-ins in 10 days) · 7-Day Streak · Night Owl Reformed (3 consecutive nights ≥ 7 h after 3 nights < 6 h) · Full Systems Go (readiness ≥ 85 for 3 days).
- Tasteful particle burst on completion. Keep gamification quiet: a streak count in Today's checks and badges in Settings. No XP bars on the main screens.

### 9.7 Alerts

If any metric is CRITICAL, show the red alert bar under the nav in plain words, using the readings and the current comms delay: *"Your blood pressure is very high (186/118). Tell your crew medical officer now. Messages to Earth take 12 min 40 s."* with **[ Ask Dr. NOVA ]** and **[ View protocol ]**. Use the Section 5.2 colour logic for all notifications. An alert never says where a number came from.

**Don't spam alerts from noisy signals, but never delay a real danger.** How many readings a CRITICAL needs depends on how the reading arrived. That is an internal property (`Measurement.device_pk`, `source`) and is never shown:

| Reading arrives from | A CRITICAL alert needs | Why |
|---|---|---|
| Symptom override (9.2) | Immediately | The astronaut reported it |
| Manual entry, **SpO₂** | **Never from a single value.** A first entry in the CRITICAL range is saved as Needs attention with `confirmed = false` and a **Re-measure to confirm** prompt. It becomes Get help now only when a **second** manual SpO₂ entry is also in the CRITICAL range, at least `min_gap_s` (60 s) and at most `window_min` (10 min) after the first, or when a symptom is ticked in the same form (immediate). A normal second entry clears the prompt, and the first row stays in history as Needs attention. | A typed or misread number must not raise an emergency by itself. The symptom override stays immediate because the astronaut reported it |
| Manual entry, other metrics | Immediately, with a "Re-measure to confirm" button | A typo is possible, a delay is not acceptable (unchanged from v2) |
| Bluetooth strap or any other non-wearable source, for a fast-path metric (`spo2` from a Bluetooth oximeter, `glucose_*`) | The first CRITICAL reading | Clinically fast-moving |
| **Wearable heart rate** | **Get help now only when every condition of `alert_confirm.heart_rate.wearable` holds:** (1) a cardio session that began after the rest countdown, (2) rest verified for that session, (3) `q ≥ min_quality` on every frame, (4) the reading stays in the CRITICAL range for ≥ `consecutive_frames` (10) consecutive 1 Hz frames spanning ≥ `min_span_s`; any invalid frame resets the run. **Otherwise Needs attention** (`unmet_status`): a single frame, a short run, a session without verified rest, or a run outside a session (live strip only, no notification, never stored as a status and never used for readiness or baselines). A frame that fails the quality gate is not a reading at all; the strip shows the signal message instead. | One abnormal reading from a hobby-grade optical sensor is far more likely motion, a loose finger or ambient light than a heart problem, and there is no motion sensor to prove rest |
| **Wearable SpO₂** | **Never CRITICAL, at any value.** Capped at Needs attention (`max_status_by_origin`). After ≥ 5 consecutive valid frames below 94 % with the finger continuously present and `q ≥ MIN_SIGNAL_QUALITY`, post a normal Needs attention notification (no red bar): "Oxygen reading is low. Hold still and re-measure. If you feel short of breath, tick the symptom box or tell your crew medical officer." | Owner decision: a hobby-grade PPG sensor must not raise Get help now on its own. A person who feels unwell escalates through the symptom override (9.2) |
| **Wearable body temperature** | High side: two consecutive 60 s aggregates, both `settled`. Low side: never CRITICAL (capped at CAUTION, 10A.6) | A skin or under-arm probe cannot establish hypothermia, and a probe off the body must never alarm |
| Generated values (blood pressure, glucose, respiration) | 2 consecutive CRITICAL readings ≥ 5 s apart; Judge Mode scenarios write these directly | Same rule as the original sensor/simulated path |

Every count, window and quality level above lives in `config/thresholds.yaml` under `alert_confirm`; nothing is hard-coded. At the end of a cardio session the stored wearable heart-rate status uses the same gate: CRITICAL only if a qualifying run happened during the session, otherwise Needs attention. Alerts are deduplicated by `dedupe_key`; a cleared condition closes the alert and sends an SSE `alert` event.

**Prototype safety logic.** These rules make the prototype cautious, not clinically validated. The counts, quality levels and time windows are placeholders that need calibration on the real hardware and clinical review, and an alert, or the absence of one, is never medical advice. The README, Settings → About and the demo script say so in plain words.

---

## 10. MODULE A: CARDIOVASCULAR `/cardio`

**Screen:** latest readings + 30-day trends at top; the wearable status line from 10A.7; an **[ Start Assessment ]** hero button.

1. **Pre-check panel** (plain language with small illustrations): how to sit (5 min rest, feet anchored in 0 g, arm at heart level); **how to wear the sensor** (rest one fingertip lightly on the pulse sensor, keep the hand still and relaxed; put the temperature probe under the arm and keep the arm down, ideally 10 minutes before the check); how to enter a reading by hand if a cuff or glucometer is available; the glucose context selector (fasting / post-meal / random); and why it matters in microgravity (fluid shift toward the head, cardiac deconditioning, orthostatic intolerance on landing, radiation-linked CV risk). Include the symptom checkboxes from 9.2.
2. **Input per metric**, chosen in a "Device link" step. Defaults are picked automatically and the astronaut can override them:
   - **Wearable (Wi-Fi), the default whenever it is online:** heart rate, SpO₂ and temperature from the ESP32 (Section 10A).
   - **Bluetooth strap:** Web Bluetooth (Chrome/Edge, secure context: `localhost` or HTTPS) using the standard Heart Rate GATT service `0x180D`; implement it fully. Blood Pressure `0x1810`, Health Thermometer `0x1809`, Glucose `0x1808` and Pulse Oximeter `0x1822` are optional stretch services.
   - **Enter by hand:** large numeric steppers with validation, available for every metric. A first oxygen value in the CRITICAL range saves with the amber Needs attention word and shows "This reading is very low. Please re-measure to confirm. If you feel short of breath, tick a symptom below or tell your crew medical officer." with a **Re-measure** button that waits `min_gap_s` before it accepts the second entry. The red alert bar appears only after confirmation (9.7).
   - **Blood pressure, glucose and respiration** have no sensor. They come from the generator (10A.9) unless the astronaut enters a value by hand. They are presented exactly like any other value, with **no mode label, badge or legend** (Section 0 rule 3).
   - **Data flow (be explicit):** every source produces the same reading object `{metric, value, value2?, unit, source, context, ts}`. Wearable frames arrive through `DeviceGateway`, BLE readings are `POST`ed by the browser to `/cardio/reading`, manual values come from the form and generated values come from `PhysiologyModel`. All of them are saved through `measurements.record()` and all of them appear in the same session stream (`/cardio/stream`), so the UI has one code path.
   - *Stretch:* **camera pulse (rPPG)**, labeled "experimental estimate".
3. **Rest countdown and device handshake.** The 5-minute rest countdown is enforced (skippable only when `DEMO_MODE=true`, and the live strip stays visible during it). When the countdown ends, compute `rest_verified` from `alert_confirm.heart_rate.wearable.rest_verification` (countdown not skipped, enough valid heart-rate frames in the last 60 s, steady 10 s medians) and keep it on the session. It is an honest approximation: the app has no motion sensor, so it cannot prove the astronaut is still, and it never tells the astronaut that rest was "verified". Then a handshake animation lists **only real connections**: "Searching… ✓ Wearable connected ✓ Heart-rate strap". A ✓ appears only when the device is actually online and, for heart rate and SpO₂, a finger is actually detected. Otherwise show "Waiting for a finger on the sensor" or "Wearable not connected: use the strap or enter by hand". Blood pressure, glucose and respiration never appear in the handshake.
4. **Live session** (`CARDIO_SESSION_SECONDS`, default 90 s, countdown ring) with one `reading` event per second over **SSE** (`/cardio/stream`): the latest valid value for each metric, in the `resting` context. Show a live **"Heartbeat" waveform** (the real pulse wave when the wearable has a finger on it and sends `ppg`, otherwise the synthetic trace from `ecg_synth.js` at the current BPM), a heart icon that beats at the live BPM only while the value is fresh, per-metric live status chips (the heart-rate chip shows Needs attention for a CRITICAL-range value until the gate of 9.7 passes), and a session timeline. If the finger is lifted, show "Place a finger on the sensor" and pause the countdown (for at most 60 s; after that the session ends with what it has). In Demo Mode the generated values can be forced to Needs attention / Get help now. Controls: Pause · Resume · End.
5. **End session.** Compute average, min and max from **valid frames only**. A metric is saved only if ≥ 60 % of the session's seconds were valid for it; otherwise show "Not enough clean readings for heart rate. Try again with your hand still." and save nothing for that metric. Temperature is included only if the probe was `settled` for ≥ 30 s of the session. **HRV is not computed** (the sensor does not support it). Save one `CardioSession` (with the input modes used and the valid-frame percentage per metric) and `Measurement` rows through `measurements.record()` with `context = resting`. Show a **results screen**: per-metric status, overall cardio status, comparison vs last 7 sessions (bar + line), plain-language explanation, 3 tailored actions, "re-measure in X h" suggestion. Award XP and tick the checklist.

---

## 10A. WEARABLE (IoT) INTEGRATION: ESP32 + MAX30102 + DS18B20

> This section is the single source of truth for the hardware path. Sections 0, 3, 4, 9, 10, 13, 16–22 and the appendices are consistent with it. If you find a contradiction, this section wins and you record the fix in `docs/DECISIONS.md`.

### 10A.0 What the hardware can and cannot do (design around this, never hide it)

| Attribute | Where the value comes from | Honest limits |
|---|---|---|
| Heart rate | **Real.** MAX30102 fingertip PPG (pulse), computed on the ESP32 | Valid only with a finger resting still on the sensor. It is a pulse rate, not an ECG. |
| SpO₂ | **Real.** MAX30102 red/IR ratio-of-ratios on the ESP32 | Hobby-grade and uncalibrated. Expect a few percent error. Motion, cold fingers, pressure, ambient light and skin tone degrade it. Not a medical oximeter. **Its status is capped at Needs attention: wearable SpO₂ can never produce Get help now on its own** (9.7). |
| Body temperature | **Real, but an estimate.** DS18B20 contact probe, ±0.5 °C sensor accuracy | It reports what it touches. Under-arm or skin reads *below* core, while the thresholds in 9.2 are core-like. A site offset is applied and only *settled* readings are classified (10A.6). |
| Blood pressure, glucose, respiration, ECG trace | **Generated** by `PhysiologyModel` (10A.9) | No sensor exists for these. No screen, message or Dr. NOVA sentence may say or imply they were measured by the wearable. |
| HRV, rhythm analysis, BP-from-PPG, respiration-from-PPG | **Not computed** | The sensor, sample rate and signal quality do not support them. Leave them out instead of faking them. |

### 10A.1 Architecture and data flow

```
MAX30102 (I²C) ─┐
                ├─► ESP32 firmware ──HTTP POST JSON, 1 Hz, LAN──► Flask  /api/device/ingest
DS18B20 (1-Wire)┘   sensor_task (core 1)  net_task (core 0)          │ token auth → schema validate
                    ring buffer + backoff                            ▼
                                                           DeviceGateway ──► QualityGate (plausibility, finger, jump, flatline, temp state)
                                                                │
              ┌─────────────────────────────────────────────────┼───────────────────────────────┐
              ▼                                                 ▼                               ▼
     SensorSample (raw 1 Hz, 7 d)                    LiveState (in memory)            Aggregator (60 s medians)
                                                                │                               │
                                                                ▼                               ▼
                                                    StreamHub ──► SSE /api/stream     measurements.record()  ◄── manual, BLE strap,
                                                                │    (Today live strip,            │             cardio session, PhysiologyModel
                                                                │     twin heartbeat, cardio)      ▼
                                                                                      Measurement → thresholds.classify → alert rules
                                                                                      → notifications → readiness → SSE `summary` event
```

| Component | File | New / changed | Responsibility |
|---|---|---|---|
| Firmware | `firmware/` | New | Sample, validate at the source, buffer, POST. No clinical logic. |
| `devices` Blueprint | `app/devices/routes.py` | New | `/api/device/ingest`, `/api/device/ping`, `/api/live`, `/api/stream` |
| `DeviceGateway` | `app/services/sensors/device_gateway.py` | New | Frames → validate → persist raw → update live state → publish → aggregate |
| `QualityGate` | `app/services/sensors/quality.py` | New | Plausibility, finger state, jump and flatline filters, temperature state machine |
| `LiveState` | `app/services/sensors/live_state.py` | New | Freshest valid values per astronaut, with staleness rules |
| `StreamHub` | `app/services/stream_hub.py` | New | In-process pub/sub that feeds every SSE endpoint |
| `Aggregator` | `app/services/sensors/aggregator.py` | New | 60 s tumbling-window medians → `measurements.record()` |
| `AlertGate` | `app/services/alert_gate.py` | New | Applies the `alert_confirm` gates of 9.7 to a classified reading: heart-rate run tracking (consecutive valid frames, quality, resting session, `rest_verified`), manual SpO₂ confirmation, expiry of unconfirmed entries. Returns the **effective** status that is stored, shown and alerted on. Pure Python, unit-tested, no I/O. |
| `measurements.record()` | `app/services/measurements.py` | New (one write path) | The only way a `Measurement` is saved: classify → `AlertGate` → alert rules → notifications → SSE `summary` → gamification hooks. Manual entry, the BLE strap, cardio sessions, the wearable and the generator all call it, so there are no duplicate code paths. |
| `PhysiologyModel`, `SimRecorder` | `app/services/sensors/physiology.py`, `simulated.py` | New / `SimulatedSource` changed | Generated attributes (10A.9) |
| `SensorSource` | `app/services/sensors/base.py` | Changed | Add `Esp32Source` (reads `LiveState`) and `DemoWearableSource` (10A.11) next to `SimulatedSource` and `ManualSource` |
| Cardio service | `app/cardio/services.py` | Changed | Wearable input mode, coverage rule, uses the hub (Section 10) |
| `thresholds.classify` | `app/services/thresholds.py` | Changed | Honour `requires_rest` (below) and `max_status_by_origin`; one new optional argument `origin`, otherwise the same call shape |
| Host guard | `app/__init__.py` | Changed | LAN rule for `/api/device/*` (Section 3) |
| `/api/summary` | `app/dashboard/routes.py` | Changed | Never returns `source`; adds `age_s` per metric and a `live` block |

**Resting rule for an always-on stream (important).** The wearable has no motion sensor, so it cannot know whether the astronaut is resting. Therefore:
- `heart_rate`, `systolic`, `diastolic`, `respiration` are `requires_rest` metrics. They are classified, alerted on, used for readiness and used for baselines **only when `context = resting`**. For the wearable that means *inside a cardio session that started after the 5-minute rest countdown*.
- Background wearable heart-rate frames and their 60 s aggregates are stored with `context = unspecified`. They feed the live strip, charts and history, but never stored status, alerts, readiness or baselines. The one exception is display only: a sustained CRITICAL-range run at adequate quality (`outside_session_display`) shows **Needs attention** on the live strip with "Heart rate reads outside the resting range. If you have been active, that is normal. Rest for 5 minutes and re-check."
- `spo2` and body temperature need no rest context and are classified from aggregates whenever the quality rules pass.
- Optional upgrade (list under "Roadmap"): an MPU6050 accelerometer would enable automatic rest detection. Do not build it.

### 10A.2 Hardware, wiring and GPIO

**Owner-confirmed facts (from the owner's photos).** Everything else in this subsection is provisional until Appendix H says it was checked.
- **ESP32:** 30-pin, USB-C, classic ESP32 DevKit-style board; the metal shield is marked "ESP-32". It is not an S3 or C3. The exact module variant (for example WROOM-32, a "D" or "U" variant, or a clone) is **not readable and unconfirmed**.
- **MAX30102:** a 7-pin module with pins, left to right: **VIN, SCL, SDA, INT, IRD, RD, GND**.
- The owner has one 4.7 kΩ resistor. The DS18B20's form (bare TO-92, waterproof probe, or a small module that may already have a pull-up) is **not confirmed**.

**GPIO assignments are configurable.** They all live in `firmware/include/pins.h`; no other file may hard-code a pin. Defaults:

| Function | Default | Origin |
|---|---|---|
| I²C SDA | GPIO 21 | Specified by the owner |
| I²C SCL | GPIO 22 | Specified by the owner |
| DS18B20 data (DQ) | GPIO 4 | Proposed by the design (any free output-capable pin works; change `pins.h`) |
| Status LED | GPIO 2 | Optional; if the board has no LED on that pin, mirror every LED pattern to the serial log |

Before wiring, check the board's silkscreen: pins labelled 21, 22 and 4 must exist, and you must identify the 3V3 and GND pins. 30-pin boards are not all laid out alike. Avoid GPIO 6–11 (flash), GPIO 34–39 (input only: they cannot drive a 1-Wire bus) and the strapping pins 0/2/5/12/15 for sensors.

**MAX30102 wiring (provisional until the pre-power checks below pass):**

| MAX30102 pin | Connect to | Note |
|---|---|---|
| VIN | ESP32 3V3 | Provisional. Documentation for this module family is not consistent about the allowed supply range, so confirm yours first. Never use a 5 V pin until the range is confirmed. |
| GND | ESP32 GND | |
| SCL | GPIO 22 | |
| SDA | GPIO 21 | |
| INT | not connected | Optional interrupt output; the firmware polls the FIFO instead |
| IRD | **not connected** | Published documentation only says it "controls the infrared LED" and does not explain how. Unconfirmed, so leave it unconnected. |
| RD | **not connected** | Same for the red LED. |

**DS18B20 wiring:** VDD → 3V3, GND → GND, DQ → GPIO 4, with **4.7 kΩ between DQ and 3V3 only if the DS18B20 board or cable has no pull-up of its own** (check D1 below). Never fit a second pull-up on top of an existing one without measuring first.

**Pre-power checks (do them in order before the first power-up; record every result in `docs/HARDWARE_FACTS.md`; do not modify the board):**

| Step | Do this | Read the result like this |
|---|---|---|
| **V1 Identify** | Photograph both sides of the MAX30102 module; keep the seller listing or datasheet; write down its stated supply range. | If the stated range does not include 3.3 V, stop. If you cannot find a stated range, record "unknown" and continue only with V2–V3. |
| **V2 Power alone** | Connect only VIN→3V3 and GND→GND. Leave SDA, SCL, INT, IRD and RD unconnected. | Nothing should get hot. If it does, unplug and stop. |
| **V3 Measure the pull-up voltage** | With a multimeter on DC volts and the black lead on GND, measure VIN, then SDA, SCL and INT each against GND. | ≈ 3.3 V on SDA and SCL: the pull-ups sit on the 3.3 V rail, which matches the ESP32; continue. ≈ 1.8 V: the pull-ups appear to sit on the sensor's own 1.8 V rail and a 3.3 V ESP32 may not read the bus; **stop and report the numbers**. ≈ 0 V: no pull-up on that line; **stop and report**. Anything else: **stop and report**. |
| **D1 DS18B20 pull-up** | With the DS18B20 **unpowered and unplugged from the ESP32**, measure resistance between its DQ and VDD (on a module, between the matching pads). | ≈ 4.7 kΩ: a pull-up is already present, so do not add yours. Very high or open: none present, add your 4.7 kΩ. Anything else: stop and report. |
| **V4 Wire it** | Wire exactly as the tables above, then power from USB. | |
| **V5 Scan** | Serial `scan`. | Expect an I²C device at `0x57` (the address documented for this chip). |
| **V6 If `0x57` is missing** | Stop. Re-check wiring and the V3 numbers. | **Do not modify the board.** Report the V3 numbers; what to do next depends on this module's own documentation and needs the owner's decision. |

Other wiring rules: everything runs at **3.3 V**, never put 5 V on a GPIO; keep the DS18B20 and I²C wires short and apart. The ESP32 radio is **2.4 GHz only**; the demo network is covered in 10A.13.

### 10A.3 Firmware specification (`firmware/`, PlatformIO + Arduino framework)

```
firmware/
├── platformio.ini            # env:esp32dev (+ env:native for pure-logic unit tests if PlatformIO can run them)
├── include/ config.h  pins.h  secrets.example.h      # secrets.h is generated and git-ignored
├── src/ main.cpp  sensor_max30102.{h,cpp}  sensor_ds18b20.{h,cpp}  finger_detect.{h,cpp}
│        quality.{h,cpp}  frame_queue.{h,cpp}  net_client.{h,cpp}  cli.{h,cpp}
├── test/ (pure-logic tests: finger hysteresis, median filter, queue overflow, backoff schedule)
└── README.md                 # wiring, flashing, serial commands, troubleshooting
```

- **Toolchain.** `pip install platformio` (no IDE required) → `pio run -d firmware` → `pio run -d firmware -t upload` → `pio device monitor -b 115200`. Pin a tested `platform = espressif32@<version>` and exact library versions in `platformio.ini` after you verify that they compile (record them in `DECISIONS.md`). Libraries: *SparkFun MAX3010x Pulse and Proximity Sensor Library* (includes `MAX30105.h` and the Maxim `spo2_algorithm.h`, so verify where the installed version ships it and keep its licence header), *DallasTemperature* + *OneWire*, *ArduinoJson* 7. The Arduino IDE is an acceptable alternative: say so in the README. On Windows the board appears as a COM port through its USB-serial chip. The chip type is unconfirmed, so a driver may be needed, and some boards need the BOOT button held while uploading; list these in the firmware README as things to check, not as facts.
- **Boot sequence.** Serial 115200 → I²C at 400 kHz → MAX30102 `begin()` and `setup(60, 4, 2, 100, 411, 4096)` (LED current 60, average 4, red+IR, 100 Hz, 411 µs pulse, 4096 range, giving an effective 25 samples/s that matches the Maxim algorithm's 25 sps assumption) → DS18B20 `begin()`, 12-bit, `setWaitForConversion(false)` → Wi-Fi station mode → find the server (1. the URL stored in flash by the serial `server <url>` command, otherwise `SERVER_URL` from `secrets.h`; 2. after 3 failed pings, try mDNS for service `_astrovital._tcp`, which works only if the laptop's firewall allows it and is **untested on Windows**) → `GET /api/device/ping` with the token → generate `boot_id` (random 32-bit hex from `esp_random()`), `seq = 0` → start the two tasks.
- **`sensor_task` (core 1, never blocks on network).** Poll the MAX30102 FIFO every ≤ 20 ms. Keep 100-sample IR/red ring buffers. **Every 25 new samples (1 s)** close one *frame*:
  1. **Finger detection** with hysteresis on the mean IR of the last 25 samples: on when `> FINGER_ON_IR` (default 50 000), off when `< FINGER_OFF_IR` (default 30 000). Both thresholds live in `config.h`. The `cal` serial command prints IR with and without a finger so they can be tuned per board.
  2. On finger **off**: the same frame sends `finger=false, hr=null, spo2=null`, the 100-sample buffers and the smoothing history are cleared, and no earlier value is ever reused. On finger **on**: restart the buffer and report nothing until the first full 4-second window plus `SETTLE_S` (default 2 s) has passed.
  3. Run `maxim_heart_rate_and_oxygen_saturation(...)`. Treat `-999`, `valid=0`, `hr` outside 30–220 and `spo2` outside 70–100 as invalid (`hr_ok`/`spo2_ok` false, values null).
  4. Smooth: median of the last 5 valid values for each of HR and SpO₂; publish only when ≥ 3 of the last 5 were valid.
  5. Compute `pi` = (IR peak-to-peak in the window ÷ mean IR) × 100 and `sat` = any sample ≥ 260 000. Compute `q` (0–100) = 50 if both flags valid + 25 if 0.3 ≤ pi ≤ 10 + 10 if not `sat` + 15 if |HR − median of last 5| ≤ 10.
  6. Attach `temp_c` (below), `ppg[25]` (optional, `SEND_PPG=1`: IR minus window mean, divided by 16, as ints) and push the frame to a bounded queue.
  7. If `I²C` returns errors three times in a row: re-initialise the sensor, emit an `i2c_error` flag on the frame, and never block longer than 200 ms.
- **DS18B20 handling.** Request a conversion once per second without waiting; read it ≥ 800 ms later. `-127.0` (`DEVICE_DISCONNECTED_C`) → `temp_ok=false`. Exactly `85.0` right after a request is the power-on default → discard unless two consecutive frames agree. Anything outside 10–50 °C → `temp_ok=false`. The firmware sends the **raw** probe reading only. The offset and all body-temperature logic live on the server so they can change without re-flashing.
- **`net_client` task (core 0).** Take frames from the queue and send a batch every `SEND_INTERVAL_MS` (1000 ms; up to 20 frames when catching up). `POST /api/device/ingest`, timeout 3 s, headers `X-Device-Token` and `X-Device-Id`. Do not rely on keep-alive.
  - 2xx → drop the sent frames, read `cfg.send_interval_ms`.
  - 401 → stop sending, blink the error pattern and print "token rejected". Do not hammer the server.
  - Other 4xx → drop that batch (it is malformed). 429 → honour `Retry-After`.
  - 5xx, timeout, DNS or connect failure → keep the frames and back off 1 → 2 → 4 → 8 → 15 s (cap 15 s, reset on success). After 60 s of server failures, re-run discovery.
  - **Buffer:** `BUFFER_MAX = 300` frames (5 minutes) in RAM; when full, drop the oldest and increment `dropped`.
- **Wi-Fi resilience.** `WiFi.persistent(false)`, `setAutoReconnect(true)`, an event handler that logs every disconnect reason, a forced `disconnect()` + `reconnect()` after 20 s offline, and `ESP.restart()` after 5 minutes offline. The sensor task keeps sampling the whole time.
- **Status LED (GPIO 2, optional; see `pins.h`).** Slow blink = connecting to Wi-Fi · fast blink = server unreachable · three quick blinks = token rejected · short pulse per heartbeat while a valid pulse is detected · off = idle with no finger.
- **Serial CLI (115200).** `status` (Wi-Fi, server, free heap, queue depth, last IR/red, temp), `scan` (I²C scan), `cal` (IR levels), `ping`, `ip` (print the ESP32's own address), `server <url>` (store the server URL in flash with no re-flash; `server` alone prints it), `reboot`. Print free heap every 60 s so a leak is visible.
- **Config files.** `include/config.h` holds committed defaults (thresholds, intervals, feature flags). `include/secrets.h` (git-ignored) holds `WIFI_SSID`, `WIFI_PASS`, `SERVER_URL`, `DEVICE_TOKEN`, `DEVICE_ID`. **`python scripts/device_setup.py`** creates it: it lists the computer's private IPv4 addresses with their adapter names and asks you to confirm the right one, asks only for the Wi-Fi name and password (plain ASCII), copies `DEVICE_TOKEN` and `DEVICE_ID` from `.env`, and prints the flash command. Flags: `--show` (print the server URL and nothing else), `--firewall` (print, never run, the Windows command from 10A.13), `--rotate` (new token). Never write the Wi-Fi password anywhere else.
- **Verification you can do without hardware:** `pio run -d firmware` must compile (if PlatformIO or the network is unavailable, record "firmware not compiled" in `PROGRESS.md`), and the native pure-logic tests must pass when `pio test -e native` can run. Everything else is exercised by the device emulator (10A.11).

### 10A.4 HTTP contract

Full examples are in Appendix F. Rules:

- `POST /api/device/ingest`: JSON body ≤ 16 KB, ≤ 60 frames. Fields per frame: `seq` (int, increasing per `boot_id`), `up_ms` (device uptime in ms at frame close), `finger` (bool), `hr` and `spo2` (number or null), `hr_ok`, `spo2_ok` (bool), `pi`, `ir_dc`, `q`, `sat`, `temp_c` (raw, number or null), `temp_ok` (bool), optional `ppg` (≤ 25 ints), optional `flags` (list of short strings). Batch fields: `v` (=1), `device_id`, `fw`, `boot_id`, `sent_uptime_ms`, `wifi_rssi`, `dropped`.
- **The device never sends wall-clock time.** The server sets each frame's timestamp as `received_at − (sent_uptime_ms − up_ms)`. This survives buffering and a restart (a new `boot_id` resets the sequence and the live state).
- Responses: `200 {"ok":true,"server_time":"…Z","accepted":n,"duplicate":n,"rejected":n,"cfg":{"rev":n,"send_interval_ms":1000}}` · `400 bad_payload` (with a field path) · `401 bad_token` · `413 too_large` · `429 rate_limited` + `Retry-After` · `503 busy` + `Retry-After` (database locked).
- **Idempotent:** `UNIQUE(device_pk, boot_id, seq)`. A retried batch is answered `200` with `duplicate` counts and stores nothing twice.
- `GET /api/device/ping` → `200 {"ok":true,"server_time":"…Z","server":"astrovital","cfg":{…}}` (token-checked). Used by the firmware at boot and by `scripts/device_check.py`.
- Both routes: no cookies and no session, CSRF-exempt, token compared with `hmac.compare_digest`, rate-limited by `device_id` (`DEVICE_RATE_LIMIT`, default `120/minute`), and covered by the LAN host rule in Section 3.

### 10A.5 Server-side validation and signal quality (`QualityGate`)

Never trust the device. Re-check everything:
- **Schema and ranges.** Unknown fields ignored, wrong types → `400`. `hr` 30–220, `spo2` 70–100, `temp_c` 10–50, `q` 0–100. NaN and ±inf rejected. A bad frame inside a batch is counted as `rejected` and does not fail the others.
- **Finger gate.** `finger=false` → HR and SpO₂ are invalid for that frame. After `finger_on` the first `FINGER_SETTLE_S` seconds (default 8) of values are stored raw but excluded from aggregates and live display (`state = settling`).
- **Quality gate.** A frame is *valid* for HR/SpO₂ only if `finger`, the matching `*_ok` flag, `q ≥ MIN_SIGNAL_QUALITY` (50) and not `sat`.
- **Jump filter.** If a valid HR differs by more than 25 bpm from the previous valid HR (≤ 3 s earlier), mark it `suspect` and accept it only if the next frame agrees within 10 bpm. Same idea for SpO₂ with a 6-point threshold.
- **Flatline filter.** `finger=true` and identical `hr`, `spo2` and `ppg` for ≥ 15 consecutive frames → `stuck` (invalid, `sensor_error` event).
- **Staleness.** A value is *live* only if its frame is ≤ `LIVE_STALE_S` (5 s) old. A frame older than `BACKLOG_LIVE_MAX_S` (30 s) when it arrives (replayed after a Wi-Fi gap) is stored as history and aggregated into the right window by its timestamp, but it **never** updates `LiveState`, never drives the live strip, and never triggers alerts.
- **Order.** Out-of-order `seq` inside one `boot_id` is stored by timestamp; a new `boot_id` resets `LiveState` for that device and logs a `boot` event.
- **Origin caps (SpO₂).** Wearable SpO₂ is classified with `origin=wearable`, and `max_status_by_origin` in `thresholds.yaml` caps its status at CAUTION (Needs attention) at **every** value, including 0. It never produces Get help now, never opens the red alert bar, and cannot pull readiness below the CAUTION cap on its own. Breathlessness escalates only through the symptom override (9.2) and Dr. NOVA's symptom rules. SpO₂ from a Bluetooth oximeter keeps its normal classification. A typed-in SpO₂ is classified normally too, but a single CRITICAL-range value is held at Needs attention until it is confirmed (9.7).
- **Heart-rate gate (wearable).** Wearable heart rate is **not** capped: it can reach Get help now, but only through the gate in 9.7 (verified resting session, adequate quality, sustained run). `AlertGate` keeps one run counter per astronaut and device in memory; the counter resets on any invalid frame, a new `boot_id`, a finger-off, a stale gap above `DEVICE_OFFLINE_S`, or the end of the session. Replayed backlog frames (older than `BACKLOG_LIVE_MAX_S`) never extend a run.

### 10A.6 Body temperature handling

The DS18B20 is accurate (±0.5 °C) but it reads the temperature of whatever it touches.
- **Recommended placement:** probe under the arm (axilla) with the arm held against the body. Closed-axilla readings climb over 10–20 minutes and still sit below core, which is why an offset is needed. Document this in the cardio pre-check and the README. Never use the probe orally.
- Server-side state machine on the raw reading (`temp_state`), evaluated per frame from the last 120 s of raw values:
  - `missing`: `temp_ok=false`.
  - `ambient`: raw < `TEMP_CONTACT_MIN_C` (default 30.0 °C). The probe is in the air or on a desk.
  - `warming`: raw ≥ 30.0 °C but not settled yet (raw < `TEMP_SETTLE_MIN_RAW_C`, or the slope over the last 120 s is above `TEMP_SETTLE_SLOPE_C_PER_MIN`, or fewer than 90 s of data).
  - `settled`: raw ≥ `TEMP_SETTLE_MIN_RAW_C` (default **34.5 °C**) **and** slope ≤ `TEMP_SETTLE_SLOPE_C_PER_MIN` (default 0.1 °C/min) over the last 120 s. The 34.5 °C floor is deliberately above hot-room air (this prototype may be demoed in a warm room); document in the README that in a room above 30 °C the floor should be raised.
- **Only `settled` readings are classified.** Body temperature = `raw + TEMP_OFFSET_C` (default **+0.6 °C** for `TEMP_SITE=axilla`; a prototype estimate based on published under-arm-versus-core differences of roughly 0.6–1 °C after 10–20 minutes). The stored `Measurement.value` is the adjusted estimate (`source = derived`) and `raw_value` keeps the probe reading. `ambient`, `warming` and `missing` are shown as plain messages ("Place the probe under your arm", "Measuring temperature… keep your arm down") and **never** produce a status or an alert. This is what stops a probe lying on a desk from raising a "Get help now".
- **Low-side cap.** A wearable-derived temperature can never be CRITICAL on the *low* side: values below 35.0 °C are capped at CAUTION with the message "Temperature reads low. Check the probe placement and re-measure." (A skin probe cannot establish hypothermia.) The *high* side is unchanged, but needs a settled reading plus the confirmation rule in 9.7.
- **Calibration.** Settings → Wearable has "Calibrate temperature": the astronaut enters a reference thermometer reading while the probe is `settled`, and the server stores `temp_offset_c = reference − raw` on the `Device` row (limit ±2.0 °C). This replaces the default offset.

### 10A.7 Live state, SSE and the dashboard

**`LiveState.snapshot(now)`** returns, per astronaut: device `{linked, online, last_seen_age_s, rssi, fw}`, `finger`, `hr`, `spo2`, `temp {state, value_c}` and a single UI `state`:
`no_device` · `device_offline` (no frame for `DEVICE_OFFLINE_S`, default 10) · `no_finger` · `settling` · `poor_signal` · `ok`. A value older than `LIVE_STALE_S` is returned as `null`, never repeated.

**`StreamHub`** (`app/services/stream_hub.py`): per-astronaut topics, one bounded `queue.Queue(maxsize=100)` per subscriber (drop the oldest when full), `publish()` never blocks, at most 4 concurrent streams per astronaut (the 5th gets `429`), subscribers always removed in a `finally`. It lives in one process; the app already runs `threaded=True` without the reloader. State this single-process limit in the README (multi-worker deployment would need Redis; that is outside this prototype).

**`GET /api/stream`** (login required, scoped to the current astronaut): `text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`, a `: keepalive` comment every 15 s. Events: `snapshot` (once on connect), `vital` (≈ 1 Hz while frames arrive: `{t, hr, spo2, temp, finger, state, q, ppg?}`), `device` (online/offline/finger/probe changes), `summary` (a classified `Measurement` was saved: clients refetch `/api/summary` and dispatch `astro:data-updated`), `alert` (a CRITICAL alert opened or cleared). The generator must not touch the database; it only reads hub messages. `GET /api/live` returns the same snapshot for page load, tests and the polling fallback.

**Client (`static/js/app/live.js`):** an `EventSource` wrapper with reconnect backoff 1 → 10 s, a fallback to polling `/api/live` every 3 s after 3 failures, and closing the stream when the tab has been hidden for 60 s. It exposes `on('vital'|'device'|'summary'|'alert', cb)`.

**Today page — Live strip** (a thin hairline row in the right panel header; not another card): *Heart rate 74 bpm · SpO₂ 97 % · Temp 36.7 °C* with a tiny pulse dot that blinks at the live BPM. States are plain text and never colour-coded by origin:
- `no_device` "No wearable linked. Connect your sensor to see live readings." · `device_offline` "Sensor not connected" (the last reading may be shown dimmed with its age, "74 bpm · 2 h ago", and is never presented as current) · `no_finger` "Place a finger on the sensor." · `settling` "Hold still… reading in a few seconds." · `poor_signal` "Weak signal. Keep your hand still." · temperature states per 10A.6.
- Live heart rate has no resting context, so (unless a sustained run shows Needs attention, 10A.5) its verdict line reads "Live · rest 5 min for a resting reading" with a ghost pill **Start rest check** (goes to `/cardio`). SpO₂ and temperature show their normal verdict word from the latest classified aggregate. After ≥ 5 consecutive valid frames below 94 %, the strip says "Oxygen reading is low. Hold still and re-measure. If you feel short of breath, tick the symptom box or tell your crew medical officer." with the word Needs attention (never Get help now).
- The digital twin's heart beats at the live BPM **only** while the live value is fresh; otherwise it shows a calm idle glow that implies no BPM.
- The indicator list and `/api/summary` keep using the latest *classified* values and show "updated X ago". Readiness freshness windows (9.3) are unchanged.

### 10A.8 Persistence, aggregation and retention

- **Raw frames** → `SensorSample` (≈ 86 k rows per day at 1 Hz). Purge rows older than `RAW_RETENTION_DAYS` (default 7) at startup and at most once per hour afterwards, in batches of 5 000 so the database is never locked for long. Aggregated `Measurement` rows are kept forever.
- **`Aggregator`:** 60 s tumbling windows aligned to the minute and keyed by frame timestamp. For each of HR, SpO₂ and temperature, a window produces a `Measurement` only if it has ≥ `AGG_MIN_VALID` (20) valid frames. Value = median, `quality` = mean `q`, `n_samples`, `window_s=60`, `device_pk` set. Sources: HR and SpO₂ = `sensor`; temperature = `derived` and only while `settled`. Windows close when a later frame arrives, on device offline, and when a cardio session ends. Every row goes through `measurements.record()`.
- **Chart load.** `/api/history` buckets to ≤ 500 points per series (median per bucket), so a 30-day chart is never 40 000 points.
- **Baselines prefer measured data** (extends 9.2a): for a metric, if ≥ 7 distinct days of `sensor`, `derived` or `manual` rows with the right context exist in the baseline window, use only those; otherwise use all rows, including the demo history.
- **Database settings:** WAL, `busy_timeout=5000`, one short transaction per ingest request (raw insert + aggregation in the same commit). On `database is locked`, retry twice, then answer `503` with `Retry-After`.

### 10A.9 Generated attributes (`PhysiologyModel`)

Blood pressure, glucose, respiration and the ECG-style trace come from a **deterministic, time-based model**, not from random noise.

- `PhysiologyModel(seed, profile).sample(t_utc, hints) -> dict` is a **pure function**. `seed` comes from a stable hash of the Astro ID and `MISSION_NAME`. There are no `random()` calls at read time. Smooth variation comes from `smooth_noise(seed, t, period_s)`, a cosine-interpolated value noise in [−1, 1], layered at periods of 8 min, 45 min and 3 h.
- **Shared latent "arousal" `a(t)` ∈ [0, 1]** keeps related values consistent: `a = clip(0.5 + 0.25·noise(45 min) + 0.10·circadian(t) + 0.5·hr_excess, 0, 1)`, where `circadian(t) = cos(2π·(hour − 16)/24)` and `hr_excess = clip((hr_live − hr_expected)/40, −0.5, 0.5)` when a live wearable heart rate (≤ 60 s old) is available, otherwise 0. So generated BP and respiration rise when the real pulse rises.
- **Blood pressure:** `sys = sys_base + 8·(a − 0.5) + 4·circadian + 2.5·noise(8 min)` with `sys_base` ∈ [108, 122] per astronaut; `dia = 0.6·sys + 6 + 1.5·noise(8 min)`. Clamp `sys` to 98–135, `dia` to 62–86, keep pulse pressure `sys − dia` within 32–55, and round to integers.
- **Glucose:** `fasting_base` ∈ [80, 94] per astronaut plus a gamma-shaped excursion after each meal in `MEAL_TIMES` (jittered ±15 min per day by the seed): `A·(dt/τ)·exp(1 − dt/τ)` with `A` ∈ [25, 38] mg/dL, `τ = 45 min`, `dt` = minutes since the meal (zero before it), plus `2·noise(45 min)`. Clamp to 72–145. Context: ≥ 8 h since a meal → `fasting`; 90–150 min after a meal → `post_meal`; otherwise `random`.
- **Respiration:** `13.5 + 2.5·(a − 0.5) + 0.5·noise(8 min)`, clamped to 11–19, rounded to whole breaths/min.
- **ECG-style trace (not stored, not classified):** `static/js/app/ecg_synth.js` draws a PQRST waveform from a sum of Gaussians at the current BPM (live wearable BPM if fresh, otherwise the last known), with small baseline wander. It is only a visual. The cardio page titles the waveform **"Heartbeat"**. When the wearable's real pulse wave (`ppg`) is available and the finger is on, the same component draws that instead.
- **Normal mode** keeps every generated value inside the NOMINAL/STABLE bands of `thresholds.yaml`. Only a **scenario overlay** (Judge Mode, `DEMO_MODE=true`) may leave them: it ramps a metric toward a target over 60 s and the scenario writes the required consecutive readings itself.
- **Realistic change rates, enforced by tests:** BP ≤ 6 mmHg per minute, glucose ≤ 8 mg/dL per minute, respiration ≤ 1.5 breaths/min per minute, over 7 simulated days sampled every minute. Also test determinism (same time → same value), bounds, pulse pressure, glucose peak timing (≈ 45 min after each meal), and a positive correlation between `hr_live` and generated systolic pressure.
- **`SimRecorder.catch_up(astronaut_id, now)`** keeps charts populated without a scheduler: it writes any missing 5-minute slots (`SIM_RECORD_INTERVAL_MIN`) for generated metrics, at most the last 24 h, idempotently (unique on astronaut, metric, source, slot time), through `measurements.record()`. Call it from startup, `/api/summary`, `/api/history` and once a minute from the ingest path, behind a per-astronaut lock and a 30 s minimum interval. It **never** back-fills real-sensor metrics (HR, SpO₂, temperature): a missing wearable means a visible gap, not invented data.
- Generated values are stored with `source = simulated` and `context = resting` (or the glucose context). They flow through the same classification, charts, history, baselines and Dr. NOVA context as every other value.

### 10A.10 Failure handling matrix

| Failure | Detected by | Device does | Server does | User sees |
|---|---|---|---|---|
| Wi-Fi lost | Event handler | Keeps sampling, buffers ≤ 5 min, reconnects with backoff | `device_offline` after 10 s, `offline` event | "Sensor not connected" (last value dimmed with age) |
| Wi-Fi back, backlog | Batch arrives with old frames | Sends ≤ 20 frames per second until the queue is empty | Stores history, aggregates by timestamp, never updates live state | Charts fill in; live strip shows only the newest real frame |
| Server down or restarted | Timeout, connection refused | Backoff, re-discover after 60 s | n/a, resumes cleanly | Nothing broken on reconnect |
| Wrong or rotated token | `401` | Stops sending, LED pattern, serial message | `token_rejected` event (rate-limited) | "Sensor not connected" + Settings hint |
| MAX30102 missing at boot | `begin()` fails | Retries every 5 s, reports `i2c_error` | Marks the pulse sensor unavailable | "Pulse sensor not found" (Settings → Wearable) |
| MAX30102 drops mid-run | Repeated I²C errors | Re-initialises | `sensor_error` event | "Weak signal" until it recovers |
| Finger removed | IR below `FINGER_OFF_IR` | Sends `finger=false` and clears buffers at once | Clears live HR/SpO₂ immediately | "Place a finger on the sensor" |
| Weak or motion-corrupted signal | `q`, `pi`, jump and flatline filters | Flags it | Excludes it from live display, aggregates and alerts | "Weak signal. Keep your hand still." |
| DS18B20 unplugged | `-127.0` | `temp_ok=false` | `temp_state=missing` | "Temperature probe not found" |
| DS18B20 power-on `85.0` | Value check | Discards it | n/a | Nothing |
| Probe not on the body | `temp_state` ambient/warming | Sends raw values | Never classifies | "Place the probe under your arm" |
| Duplicate or retried batch | `UNIQUE(device,boot,seq)` | n/a | `200`, `duplicate` count, no second row | Nothing |
| Device flooding | Rate limit | n/a | `429` + `Retry-After` | Nothing |
| Database locked | `OperationalError` | Retries on `503` | Retries twice, then `503` | Nothing |
| Browser SSE drops | `onerror` | n/a | Removes the subscriber | Reconnects, or polls `/api/live` |
| Browser has no wearable at all | `no_device` | n/a | Everything else works as before | "No wearable linked" |

### 10A.11 Modes: real device, demo fallback, emulator

- **`SENSOR_MODE=device` (default).** Only the real wearable supplies HR, SpO₂ and temperature. Nothing is substituted when it is absent.
- **`SENSOR_MODE=demo` (explicit opt-in).** An in-process `DemoWearableSource` produces the same frames as the firmware once per second (virtual device `AV-DEMO-01`, finger always on, values from `PhysiologyModel`, an occasional short finger-off gap to exercise the states) and feeds the **same** `DeviceGateway` path, so the UI, SSE, aggregation and alerts behave exactly as with hardware. The switch rule is below. The boot checklist prints the active mode in a visible line, and the readings are stored with `source = simulated`.
- **Manual switch only, in both directions.** The mode lives in `Mission.sensor_mode` (`.env` `SENSOR_MODE` only sets the initial value on first boot; the database wins afterwards). It changes only when a person uses Settings → Demo panel, through `POST /settings/sensor-mode`, which writes an `AuditLog` row. **No code path may change it for any other reason**: not a wearable going offline, a sensor failure, a finger lift, a timeout or a restart. In `device` mode a missing wearable shows "Sensor not connected" and nothing is substituted. In `demo` mode, frames from a real device are acknowledged with `"ignored": true` and neither stored nor shown, so real and generated readings never mix; switching back to `device` resumes the real device. Test it: leave the device offline for 10 minutes and assert the mode is unchanged and no demo frame was produced.
- **`scripts/device_emulator.py`** is an HTTP client that posts to the real `/api/device/ingest` with the real token, so it tests the whole network path without hardware. Profiles: `normal`, `no_finger`, `finger_flap`, `weak_signal`, `spike`, `flatline`, `probe_missing`, `probe_ambient`, `probe_warming`, `wifi_gap` (sends a 90-second backlog), `duplicate`, `bad_token`, `malformed`, `flood`, `restart` (new `boot_id`). The tests and `verify.py` use it; it is also a handy second terminal during a demo.

### 10A.12 Security of the device path

- Shared secret `DEVICE_TOKEN` (generated by `setup.py`, kept in `.env` and in the git-ignored `firmware/include/secrets.h`, never logged), sent in `X-Device-Token`, compared in constant time. To rotate it run `python scripts/device_setup.py --rotate`, restart `run.py` and re-flash.
- `/api/device/*` is reachable only from the local network (host rule in Section 3), CSRF-exempt, cookie-free, rate-limited, size-limited and schema-validated. Unknown `device_id`s are rejected unless `DEVICE_AUTO_REGISTER=true`.
- Each device is bound to one astronaut (`Device.astronaut_id`, initially `DEVICE_WEARER_ID`). Ingest writes only for that astronaut. A logged-in astronaut can switch the wearer to themselves in Settings, and the change is audited.
- Plain HTTP on a trusted LAN is a **prototype shortcut**: anyone on the same network could sniff the token. Add `# SECURITY NOTE:` comments, state it in the README, and note that production needs TLS with a pinned certificate and a per-device key.
- Never expose `/api/device/*` through the tunnel (host rule), and never return `DEVICE_TOKEN` to a browser. No script may change Windows firewall settings by itself.

### 10A.13 Network: Windows laptop + 2.4 GHz phone hotspot

This is the confirmed demo setup. Every point below is a **risk to test (Appendix G, T0–T4)**, not a known fact.
- **Band and security.** The ESP32 supports 2.4 GHz only. Set the hotspot to 2.4 GHz if the phone offers a band or compatibility setting; use WPA2-Personal if there is a choice; use a plain ASCII network name and password (no curly apostrophes, emoji or hidden SSID). Keep the phone plugged in and turn off any hotspot auto-off.
- **Changing address.** A phone hotspot hands out addresses by DHCP and cannot reserve them, so the laptop's IP may differ every session. The boot checklist prints the wearable URL on every start; `python scripts/device_setup.py --show` prints it again; if it changed, run `server http://<ip>:5000` in the firmware's serial console (stored in flash, no re-flash). `device_setup.py` lists every private IPv4 address with its adapter (Wi-Fi, Ethernet, VPN, WSL, Hyper-V, VirtualBox) and asks you to confirm; `DEVICE_LAN_IP` pins the choice.
- **Windows Firewall.** The first time Python listens on `0.0.0.0`, Windows asks for permission. A hotspot network may be classed as *Public*, where inbound connections can be blocked even after you tick "Private". Preferred fix: set that Wi-Fi network's profile to *Private* in Windows network settings. Otherwise `device_setup.py --firewall` prints, and never runs, an administrator PowerShell command that allows inbound TCP 5000 from the local subnet only; the owner decides whether to run it.
- **Client isolation.** Some hotspots and access points block traffic between connected devices. Whether this phone does is **unknown**. Diagnosis: if a phone browser can open `http://<laptop-ip>:5000/healthz` but the ESP32's serial `ping` fails, suspect client isolation or an ESP32 fault (the phone reaching the laptop does not prove that two clients can reach each other). If the laptop cannot ping the ESP32's printed IP either, isolation becomes more likely. Record the outcome in `docs/HARDWARE_FACTS.md`.
- **Plan B (untested).** Use Windows' own Mobile hotspot on the laptop, so the laptop is the access point and the ESP32 joins it. This avoids phone client isolation and a changing laptop address (the laptop's address on its own hotspot is typically fixed; the commonly seen value is 192.168.137.1, which must be verified). It depends on the laptop's Wi-Fi adapter supporting it and has not been tested.
- **Internet.** Dr. NOVA's OpenHome voice needs internet through the phone's data connection. The wearable path does not.
- **mDNS fallback** needs inbound UDP 5353 on the laptop: untested on Windows. The `server <url>` command is the primary method.

---
## 11. MODULE B: BONE & MUSCLE `/musculoskeletal`

> Honesty banner on the page: *"A camera can't measure bone density. This module tracks the mechanical loading exercise that protects your bones and muscles in reduced gravity."*

1. **Instruction panel:** why loading exercise matters (≈1–1.5 % bone mineral loss per month in microgravity; muscle atrophy; ISS crews exercise about 2 h/day on ARED, the treadmill and the cycle ergometer), camera placement (side view, full body in frame, 2–3 m), safe-space check, and the environment's exercise options from `environments.yaml`.
2. **Environment-aware exercise picker:**
   - **0 g (Spacecraft, Space Station):** camera counting is offered for **harnessed treadmill running** only. Push-ups and pull-ups are hidden with a one-line explanation (they don't load the body in 0 g). **Device log** (ARED / cycle / treadmill): manual entry of minutes + effort 1–10, which feeds the loading index.
   - **Lunar Base / Rover / Mars Base:** Running/jogging in place · Push-ups · Pull-ups (not in Rover) · Squats · Device log.
3. **[ Start Session ]** → `getUserMedia` permission → live mirrored video with a **neon skeleton keypoint overlay** (canvas), FPS chip, and a "pose confidence" meter. If permission is denied, show a clear message, a retry, and the manual-log fallback.
4. **Pipeline and canonical keypoints:**
   - `pose_service.py` works only on the **canonical 17 COCO keypoints** `{nose, l/r_eye, l/r_ear, l/r_shoulder, l/r_elbow, l/r_wrist, l/r_hip, l/r_knee, l/r_ankle}` as `{name: (x, y, confidence)}` in normalised image coordinates. `static/js/app/pose_adapters.js` maps MediaPipe's 33 landmarks to this set (and the ViTPose output already matches).
   - **Default `POSE_BACKEND=mediapipe`:** inference runs client-side (vendored WASM + `pose_landmarker_lite.task`, ~15–30 fps); only keypoints (JSON, ≤ 15/s) go to `POST /musculoskeletal/keypoints`. **Frames never leave the browser.**
   - **Optional `hf_vitpose`:** the browser sends frames at 6–10 fps (downscaled to 256×192, JPEG base64) to `POST /musculoskeletal/frame`; the server runs ViTPose from `ml_models/pose/` (use the whole frame, or the last tracked box, as the person box). Log the round-trip latency; if it exceeds 250 ms, show "Switch to fast mode" (MediaPipe). Running cadence is disabled below 10 fps effective.
   - Smoothing: EMA on keypoints and angles; ignore frames where the relevant chain has confidence < 0.4; use the side (left/right) with the higher mean confidence; minimum 0.6 s per rep; hysteresis on thresholds.
   - **Rep state machines:**
     - Push-up: DOWN when elbow < 90° and hip–shoulder–ankle alignment within 15°; UP when elbow > 155°. Cues: "Go lower", "Keep your body in a straight line", "Good rep!".
     - Pull-up: UP when the **nose (or ear midpoint) is above the wrist line** and elbows < 70°; DOWN when elbows > 150°. Cue "Full extension".
     - Squat: DOWN when knee < 100°; UP when knee > 160°.
     - Running: cadence from ankle/knee vertical oscillation (peak detection), giving steps, cadence (spm), duration, and an *estimated* intensity (MET, labelled "estimate").
   - Live HUD: big rep counter, form score (0–100), tempo, set timer, voice cue (`speechSynthesis`, toggleable), and a green flash per valid rep.
5. **End session** → save an `ExerciseSession` with `ExerciseSet` rows (type, reps, duration, cadence, form score; `device_log` sets carry minutes + effort). Compute the **Musculoskeletal Loading Index** (`services/loading_index.py`), trailing 7 days:

   ```
   volume_ratio    = clip(active_minutes / weekly_active_min_target, 0, 1)
   frequency_ratio = clip(distinct_exercise_days / target_days, 0, 1)
   intensity_ratio = clip(mean_MET / target_met, 0, 1)         # MET: run 8 (scaled by cadence), pushup 3.8, pullup 4.0, squat 5.0, device_log 3 + 0.5·effort
   form_ratio      = clip(mean_form_score / 80, 0, 1)           # camera sets only; 1.0 if none
   loading_index   = 100 · (0.40·volume + 0.30·frequency + 0.20·intensity + 0.10·form)
   ```
   Rep-based sets convert to active minutes as `max(duration_s, reps × 3 s) / 60`. Then update the dashboard card and the twin's bone glow, award XP, and show a results screen with previous-session comparison and tips.
6. **Privacy:** frames are processed in memory (or entirely in the browser) and **never stored**. Say so on screen.

---

## 12. MODULE C: MENTAL HEALTH `/mental`

1. **Intro panel:** why behavioral health matters (isolation, confinement, distance from family, comms delay, workload, circadian disruption), what the daily voice check-in is, what is stored, and the privacy controls. Warm, human tone. States that analysis is **English-only** and that other languages use the self-rating only.
2. **Daily voice check-in:** target `MENTAL_SESSION_TARGET_MIN` (default 3 min), minimum `MENTAL_SESSION_MIN_SECONDS` (60 s) for a valid analysis, hard cap `MENTAL_SESSION_MAX_MIN` (20), stop anytime, pause/resume. The UI shows a large animated radial waveform, a timer with a progress arc to the target, a mic level meter, and **rotating gentle prompts** ("How did you sleep?", "What's taking up most of your headspace today?", "Anything you're looking forward to?", "How are things with the crew?"). An alternative **text check-in** is offered if the mic is unavailable, plus an optional quick **mood slider + sleep quality** self-rating.
3. **Robust recording (PCM chunks, not MediaRecorder slices):** an `AudioWorklet` (`pcm_worklet.js`, shared with the doctor mic) captures 16 kHz mono Int16 PCM. The client cuts a chunk at ≥ 30 s on the next ≥ 300 ms of silence (max 40 s), wraps it as a self-contained **WAV**, and uploads it to `POST /mental/chunk` (`checkin_id`, `seq`, idempotent on the pair, ≤ 2 MB, ownership checked). The server transcribes **each chunk in a background thread** (`vad_filter=True`) as it arrives, so results are ready seconds after stop, and shows a live transcript preview. Orphaned files in `uploads/` are swept at startup.
4. **NLP analysis (local):**
   - Sentence segmentation → **sentiment** per segment (pos/neu/neg + confidence) → aggregate ratios.
   - **Emotion** distribution (joy, sadness, anger, fear, surprise, disgust, neutral).
   - Lexicon flags: stress, fatigue, loneliness, sleep trouble, homesickness, conflict.
   - Optional prosody features (speech rate, pause ratio) from the audio.
   - **Mental Wellbeing Score (0–100)**:
     ```
     sentiment_index = (pos_ratio − neg_ratio + 1) / 2
     emotion_valence = clip(0.5 + 0.5·(joy − (sadness + anger + fear + disgust)), 0, 1)
     flag_penalty    = min(1, 0.25 × number_of_distinct_flags)
     self_rating     = (mood_slider_1_10 − 1) / 9   (omit if not given and renormalise the others)
     score = 100 · (0.35·sentiment_index + 0.25·emotion_valence + 0.20·self_rating + 0.20·(1 − flag_penalty))
     ```
     Weights live in `config`. Always show the score next to the astronaut's own usual (9.2a): what someone talks about on one day is not their mood.
   - **Safety screen (mandatory, `config/safety_lexicon.yaml`):** runs on **every chunk as it is transcribed**, on text check-ins, and on Dr. NOVA text chat input. On a hit, immediately skip the usual result screen. Show a calm supportive message, direct the astronaut to contact the crew medical officer and ground behavioral-health support now, raise a CRITICAL notification flagged for follow-up, and suggest talking to Dr. NOVA. Never rely only on the model: the lexicon is a hard rule, the model score is secondary. This is the **only** way wellbeing becomes CRITICAL.
5. **Results:** mood category (Good = score ≥ 70 / Okay = 55–69 / Low = < 55, shown with the matching status word and the model confidence), emotion donut, sentiment-over-time timeline across the session, detected themes as chips, a three-sentence plain-language summary, 14-day mood trend, and wellness suggestions (breathing exercise launcher, sleep hygiene, scheduled family call, crew time, exercise). Not a diagnosis, and the screen says so.
6. Collapsible transcript with **[ Delete transcript ]**. With `STORE_TRANSCRIPTS=false` (the default), keep only scores + summary and discard the transcript when analysis finishes. Audio files are deleted after transcription.
7. Persistent Needs attention for 3+ days → a supportive notification + a suggestion to talk to Dr. NOVA + a status colour on the Mission Control view (never content).

---

## 13. AI DOCTOR `/doctor`: **Dr. NOVA on OpenHome** (major feature)

Dr. NOVA is a **voice-first** AI Flight Surgeon Assistant that knows the logged-in astronaut's real data. It runs as an **OpenHome Personality (agent)**, extended with a custom **OpenHome Ability** that fetches the astronaut's context from Flask.

> **Before coding the OpenHome parts, read the current developer docs** (`github.com/openhome-dev/abilities`, its `docs/OpenHome_SDK_Reference.md` and `templates/api-template`, and the `openhome-client` package on PyPI). The platform evolves, so adapt the details below to the live docs and record every deviation in `docs/DECISIONS.md`. Keep all OpenHome code isolated in `services/openhome_service.py` and `openhome_ability/`. **Build and test everything against the mock first (`OPENHOME_MOCK=true`, `tests/mock_openhome.py`), then switch to the real service when keys exist.** Missing keys are not a failure: the phase gate passes on the mock plus the fallbacks.

### 13.1 Architecture

```
Browser (doctor.html)
  ├─ mic → AudioWorklet → 16 kHz Int16 PCM → base64 ──► Flask  /ws/doctor/voice  (flask-sock, Origin check)
  │                                                       │  (adds API key server-side; redacts logs; heartbeat)
  │                                                       ▼
  │                                     OpenHome voice WebSocket   (or the local mock)
  │                                     wss://app.openhome.com/websocket/voice-stream/{API_KEY}/{AGENT_ID}
  │                                                       │
  │◄── transcripts (live/final) + MP3 audio chunks ───────┘
  │
  └─ text chat ──► Flask POST /doctor/chat ──► OpenHome text call ─(if down)─► LLM fallback ─(if down)─► rule-based tips

OpenHome cloud: Dr. NOVA Personality
  └─ Ability "AstroVital Health Context" ──HTTPS (tunnel, /api/openhome/* only)──► Flask GET /api/openhome/context
                                                            (header X-AstroVital-Token)
                                                          ◄── minimal astronaut context JSON (Appendix C)
                                                          ──► POST /api/openhome/log  (voice logging: "log 6 hours sleep")
```

**Honest privacy note (show it on the doctor page and in the README):** Dr. NOVA's voice path uses OpenHome's cloud, and the optional fallback LLM is also cloud-based. Only the data listed under *What Dr. NOVA sees* leaves the machine. Everything else in AstroVital stays local.

### 13.2 Pieces to build

1. **Persona (single source):** `config/dr_nova_persona.md` holds Appendix A. Flask text chat, the fallback LLM and `build_openhome_ability.py` all read this one file. The build script also prints the persona and the manual steps for pasting it into the OpenHome dashboard (create agent "Dr. NOVA", choose a calm warm voice, copy the agent ID into `.env`).
2. **Context builder (one path for voice and text):** `doctor_context.build(astronaut_id) -> dict` and `to_prompt_text(ctx) -> str`. The bridge endpoint returns `build()`; text chat prepends `to_prompt_text()`. Minimum necessary data: callsign, role, age, mission day/environment, latest metrics with status words/sources/ages, 14-day trends, personal baselines, last session summaries, active alerts, readiness. **No full name, no email, no IDs, no other astronaut's data, no raw transcripts.**
3. **Ability** (`openhome_ability/main.py.tmpl`, Appendix B): follows the official Ability pattern (`MatchingCapability`, `CapabilityWorker`, `call()` → `session_tasks.create(self.run())`, always `resume_normal_flow()` on every exit path). Configure broad trigger words in the dashboard: *"doctor nova", "check my health", "how am I doing", "review my vitals", "health report", "log my sleep", "I feel", "my heart", "my head hurts"*, and add one persona instruction: **"At the start of every conversation, run the AstroVital Health Context ability before answering any health question."** On trigger it fetches the context, runs a multi-turn loop (`user_response()` → `text_to_text_response()` → `speak()`) until the astronaut says an exit phrase, refreshes the context every 2 minutes, and supports voice logging (sleep hours, mood 1–10, water) via `POST /api/openhome/log`.
   - `scripts/build_openhome_ability.py` renders the template with `PUBLIC_BASE_URL`, a **freshly generated bridge token (written to `.env` on every build, so each push rotates the secret)** and the persona, zips it, and pushes it with the `openhome` CLI (`openhome push … --agent $OPENHOME_AGENT_ID`), or prints manual upload steps.
   - **Auto-start:** when the voice session opens, if the OpenHome stream accepts a text/user-message frame (check the docs), the proxy sends "Doctor Nova, check my health" once so the Ability is always engaged. Otherwise the doctor page shows a chip "Say: *Dr. Nova, how am I doing?*".
   - **Reachability:** for a local demo expose Flask with `cloudflared tunnel --url http://localhost:5000` (or ngrok) and set `PUBLIC_BASE_URL`. The host guard (Section 3) makes only `/api/openhome/*` and `/healthz` reachable through it. Document OpenHome **Local Link** as an alternative.
4. **Session binding (fail closed):** when the astronaut presses the mic, Flask creates a `DoctorSession(astronaut_id, active=True, expires_at=+20 min)` and updates `last_heartbeat_at` on every frame or ping from the browser. `/api/openhome/context` and `/log` serve **the single session whose heartbeat is ≤ 45 s old**; if there are none → `404 no_active_session`; if there is more than one → `409 ambiguous_session` and nothing is returned. Document this one-active-voice-session limit as a prototype limitation. Validate the token with `hmac.compare_digest`, rate-limit the bridge routes (30/min), exempt them from CSRF, log every access in `AuditLog`, and return only Appendix C data.
5. **Voice proxy** (`/ws/doctor/voice`): check the `Origin` header against `TRUSTED_HOSTS`/`PUBLIC_BASE_URL` and require a logged-in session. Flask opens the upstream OpenHome WebSocket using a browser-like `User-Agent` header (required, otherwise the server closes with 1008) and relays frames both ways with one reader thread per direction:
   - client → server: `{"type":"audio","data":<b64 PCM16 16 kHz>}`, `bot-speaking`, `bot-speak-end`, `interrupt-event`, `ping`
   - server → client: `{"type":"message","data":{role,content,live,final}}` (render as live captions + chat bubbles), `audio` frames carrying **MP3** (queue and play via `AudioContext.decodeAudioData`, in order), `text` control events (`audio-init`, `audio-end`, `interrupt`).
   - Half-duplex: mute the mic while Dr. NOVA speaks (no echo loop), and send `bot-speak-end` when playback drains. The **Interrupt** button stops playback and sends `interrupt-event`.
   - Reconnect with backoff, and show connection state (Connecting / Live / Reconnecting / Offline).
   - **Mock mode:** with `OPENHOME_MOCK=true`, the proxy talks to an in-process mock that returns canned captions (and no audio, so the browser uses `speechSynthesis`). `tests/mock_openhome.py` is a standalone WebSocket server with the same frames for contract tests.
6. **Text chat** (`POST /doctor/chat`): try OpenHome text (`openhome` Python client `call(agent_id, text)` or the documented text endpoint). If OpenHome is unavailable, use `llm_fallback.py` (OpenAI-compatible, same persona + context). If that's unavailable too, use rule-based answers from `recommendations.yaml`. Always show which engine answered (chip: `OPENHOME` / `FALLBACK LLM` / `OFFLINE RULES`). In fallback modes, speak replies with browser `speechSynthesis`. The safety screen (Section 12) runs on every incoming chat message *before* any engine is called.
7. **History:** store `ChatMessage` rows (role, content, engine, created_at). Show the last 30 turns, and add a "New consultation" button.

### 13.3 Doctor UI

- **Conversation column (centre, max 780px):** a header with a small breathing gradient **orb** (colour shifts by state: listening, thinking, speaking, alert) + "Dr. NOVA · Speaking" with live voice bars and a **Stop talking** button. Below, a clean chat: Dr. NOVA's replies as plain text (no bubble), the astronaut's messages as white pills on the right, numbered action lists, and the safety line in grey. At the bottom: 3 suggested prompts and one rounded input bar with a big white **mic** button (hands-free or push-to-talk). In fallback modes, a small "Offline answers" note.
- **Right panel (320px): "What Dr. NOVA sees"**, the exact numbers shared with the agent as five hairline rows with status dots (heart rate, blood pressure, sleep, mood, exercise load), plus the line "Voice AI by OpenHome (cloud). Never makes up numbers or prescribes medicine. Messages to Earth take 12 min 40 s."
- Clear loading, offline, and error states. Mic-permission help.

### 13.4 Behavior requirements (enforced in the persona + context builder)

- Always ground answers in the astronaut's actual stored data, and quote values + dates. If data is missing, say so. **Never invent readings.** Each reading in the context carries a `source` for your reasoning only: do not mention sources unless the astronaut asks how a number was obtained, then answer truthfully (wearable sensor, estimated from a sensor, entered by hand, or generated for demonstration) and never state or imply a measurement method the source does not support. If the wearable is not reading (no finger, offline), say so and ask for a fresh reading; never reuse an old live value as current.
- Explain *why* (link to RIDGE hazards and the environment), then give concrete actions (hydration, exercise, breathing, sleep hygiene, nutrition, when to re-measure).
- **Voice replies ≤ 60 words:** answer, one-sentence reason, up to three actions spoken as "First…, second…, third…", and one short follow-up question only if it helps. Numbered lists and the recap are for text chat and the end of a consultation. Longer only when asked for detail.
- **Escalation:** for CRITICAL readings or emergency symptoms (chest pain, severe breathlessness, fainting, confusion, severe headache, suicidal thoughts), tell the astronaut to **alert the crew medical officer / ground flight surgeon immediately and follow the onboard medical protocol**. Mention the comms delay.
- Never prescribe medication or doses, and never give a definitive diagnosis. It is an assistant to the flight surgeon, not a replacement.

---

## 14. HEALTH HISTORY `/history`

Filters: system (Cardio / Bone & Muscle / Mental / Sleep / All), date range, assessment type and status. Views: **timeline** (cards per day with status dots), **calendar heatmap** (readiness per day), and **charts** per metric. Clicking a day opens that day's full assessment detail. Records are never overwritten, and every record carries `astronaut_id` + timestamp. Exports: CSV and a **"Downlink Report" PDF** (reportlab; one-page summary for the ground flight surgeon, with trends, flags, and a session list; mental-health content limited to status and trend, never transcripts). Exports contain no source column.

## 15. NOTIFICATIONS `/notifications` + bell dropdown

Types: routine reminders (cardio, exercise, check-in, sleep log), attention required, critical, assessment saved, Dr. NOVA recommendation ready, badge unlocked. Severity uses the status colours. Mark read / mark all read. Critical notifications include recommended next steps. Throttle duplicates with a `dedupe_key`. Delivery: the client polls `/api/notifications/poll` every 30 s (it returns new notifications and due reminders).

## 16. SETTINGS `/settings` and MISSION CONTROL `/mission-control` (optional, scores points)

- **Settings** (persisted in `UserSettings`): environment, units (°C/°F, mg/dL/mmol/L; data is always stored in °C and mg/dL), reminder times, voice cues on/off, reduced motion, transcript storage, a **Wearable panel** (online/offline, last seen, firmware version and signal strength, an "I'm wearing it" wearer switch, temperature site and calibration per 10A.6; the token is never shown), an **About this prototype** panel (plain statement: "Heart rate, SpO₂ and temperature come from the connected wearable when it is present. Blood pressure, glucose, respiration and the ECG-style trace are generated for demonstration because no sensor for them is attached. This is a prototype, not a medical device."), **delete my mental-health data** (cascades to `MentalCheckin`, related `ChatMessage` rows, derived wellbeing `Measurement` rows and recomputes `ReadinessDaily`), and the **Demo panel** (when `DEMO_MODE=true`): force the status of generated metrics (real wearable metrics can only be forced after switching **Wearable mode** to Demo data, 10A.11), jump the mission day, and **Judge Mode scenario presets** (each scenario can also set the environment and `Mission.comms_delay_s`):
  1. *"Day 142, Mars transit"* (Spacecraft, delay 600 s): poor sleep → elevated HR → low mood
  2. *"Lunar base"*: no exercise for 4 days → loading index Needs attention
  3. *"Critical BP event, 14-min comms delay"*: generated BP 186/118, delay 840 s
- **Mission Control** (flight-surgeon login only): a crew grid with each astronaut's readiness **status colour** (not the number), flags ("follow-up requested" after a safety-screen event), last check-in time, and a click-through to a read-only history of **physiological metrics only**. No transcripts and no mental-health detail beyond the status colour. **Every Mission Control view is written to `AuditLog`.** Shows how the system scales to a crew.

---

## 17. DATA MODEL (SQLAlchemy, with FKs, indexes, and created_at everywhere)

All timestamps are stored in **UTC**. "Dates" (`SleepLog.date`, `DailyTask.date`, `ReadinessDaily.date`, streaks) use the **UTC calendar date** as the mission clock. Mars sols are not modelled; note this in the README.

```
Astronaut(id, astro_id UNIQUE, name, role, callsign, is_surgeon, mission_id FK,
          xp, level, streak, last_active_at, created_at)
Mission(id, name, start_date, environment, comms_delay_s NULL, sensor_mode[device|demo])   # environment and sensor_mode live here ONLY
UserSettings(id, astronaut_id UNIQUE FK, temp_unit, glucose_unit, reminder_times_json, voice_cues, reduced_motion,
             store_transcripts, updated_at)
HealthProfile(id, astronaut_id FK, age, sex, height_cm, weight_kg, baseline_json, notes)   # baseline_json = computed cache only
Measurement(id, astronaut_id FK, metric, value, value2 NULL, unit, status, threshold_version, source[sensor|derived|manual|simulated|cv|nlp|voice],
            context NULL[resting|active|unspecified|fasting|post_meal|random], confirmed BOOL, session_type, session_id NULL,
            device_pk NULL FK, quality NULL, n_samples NULL, window_s NULL, raw_value NULL, created_at)   # INDEX(astronaut_id, metric, created_at)
            # `source` is internal data-handling metadata and is never serialized to the browser. `context=unspecified` = background wearable heart rate
            # with no known rest state: kept for charts and history, never classified, alerted on, or used for baselines or readiness.
            # one long table powers all charts. `metric` is a fixed vocabulary: heart_rate, blood_pressure, glucose, temperature_c,
            # spo2, respiration, sleep_hours, wellbeing, loading_index, hydration_ml. Stored in canonical units (°C, mg/dL).
CardioSession(id, astronaut_id, started_at, ended_at, avg_hr, avg_sys, avg_dia, avg_temp, avg_glucose,
              glucose_context, avg_spo2, avg_resp, hrv_rmssd NULL (always NULL: not supported by the hardware), symptom_flags_json, input_modes_json, valid_pct_json, rest_verified BOOL NULL, overall_status, summary)
ExerciseSession(id, astronaut_id, started_at, ended_at, environment, loading_index, overall_status, summary)
ExerciseSet(id, session_id FK, exercise_type[run|pushup|pullup|squat|device_log], reps, duration_s, cadence_spm, form_score, effort_1_10 NULL)
MentalCheckin(id, astronaut_id, started_at, duration_s, mode[voice|text], status[recording|processing|done|safety_flag|failed],
              transcript NULL, mood_category, confidence, sentiment_json, emotion_json, themes_json,
              self_mood_1_10 NULL, self_sleep_1_5 NULL, wellbeing_score, safety_flag, summary)
AudioChunk(id, checkin_id FK, seq, status[received|transcribing|done|failed], created_at)   # UNIQUE(checkin_id, seq)
SleepLog(id, astronaut_id, date, hours, quality_1_5, source)       # source of truth; also writes a sleep_hours Measurement for charts
IntakeLog(id, astronaut_id, date, water_ml, meals_json NULL)
ReadinessDaily(id, astronaut_id, date, score, breakdown_json)
DoctorSession(id, astronaut_id, active, started_at, last_heartbeat_at, expires_at)
ChatMessage(id, astronaut_id, doctor_session_id NULL, role, content, engine, created_at)
Notification(id, astronaut_id, type, severity, title, message, action_url, dedupe_key NULL, is_read, created_at)
Badge(id, astronaut_id, code, awarded_at)
DailyTask(id, astronaut_id, date, task_code, done, done_at)
AuditLog(id, actor, action, target_astronaut_id, meta_json, created_at)
Device(id, device_id UNIQUE, astronaut_id FK, label, fw_version NULL, temp_site, temp_offset_c, last_seen_at NULL, last_boot_id NULL,
       last_seq NULL, last_ip NULL, last_rssi NULL, created_at)
SensorSample(id, astronaut_id FK, device_pk FK, boot_id, seq, ts, received_at, buffered BOOL, finger BOOL, hr NULL, spo2 NULL,
             temp_raw_c NULL, temp_c NULL, temp_state, pi NULL, quality NULL, flags_json NULL)
             # UNIQUE(device_pk, boot_id, seq); INDEX(astronaut_id, ts); raw 1 Hz frames, purged after RAW_RETENTION_DAYS (10A.8)
DeviceEvent(id, device_pk FK, ts, kind[boot|online|offline|finger_on|finger_off|probe_missing|probe_ok|sensor_error|backlog_replay|token_rejected], detail_json)
```

**Seed script:** 30 days of realistic history per astronaut (`source=simulated`, which the UI never shows), with circadian HR variation, slow BP drift, a few Okay / Needs attention days, **one Get-help-now BP event** (≥180 systolic), a sleep-debt streak that correlates with a mood dip, and exercise gaps, so charts, the twin, the history page, and Dr. NOVA all have a story on first launch. Idempotent; `--reset` option. Blood pressure, glucose and respiration history come from `PhysiologyModel` so seeded and live generated data share one character; heart rate, SpO₂ and temperature history are seeded with plausible resting values (`context=resting`) and are superseded by measured data when it exists (10A.8).

---

## 18. API ROUTES

```
GET  /healthz                           (public; also reachable through the tunnel)
GET  /                                  landing
GET  /login   POST /login   GET /logout
GET  /dashboard
GET  /api/summary                       latest indicators + statuses + readiness + alerts
GET  /api/history?metric=&range=              (bucketed to ≤ 500 points)
GET  /api/bodypart/<mind|heart|bones>   status + metrics + advice (env-aware)
GET  /cardio      POST /cardio/start    GET /cardio/stream (SSE, session-scoped)   POST /cardio/reading   POST /cardio/end
GET  /api/live                          wearable live snapshot (login)
GET  /api/stream                        SSE: snapshot | vital | device | summary | alert (login, max 4 per astronaut)
POST /api/device/ingest                 (device token; LAN hosts only; CSRF-exempt; rate-limited)
GET  /api/device/ping                   (device token; LAN hosts only)
POST /settings/device                   wearer switch + temperature calibration (login)
POST /settings/sensor-mode              device | demo (DEMO_MODE only)
GET  /musculoskeletal   POST /musculoskeletal/start   POST /musculoskeletal/frame (hf_vitpose only)   POST /musculoskeletal/keypoints
                        POST /musculoskeletal/set     POST /musculoskeletal/end
GET  /mental      POST /mental/start    POST /mental/chunk   POST /mental/text   POST /mental/finish
                  GET /mental/status/<id>   DELETE /mental/<id>/transcript
GET  /doctor      POST /doctor/chat     WS /ws/doctor/voice    POST /doctor/session   POST /doctor/session/end
GET  /api/openhome/context              (token-auth, tunnel-reachable, for the OpenHome Ability)
POST /api/openhome/log                  (token-auth, voice logging)
GET  /api/openhome/health               (status chip)
GET  /history     GET /history/export.csv   GET /history/report.pdf
GET  /notifications   GET /api/notifications/poll   POST /notifications/<id>/read   POST /notifications/read-all
GET  /api/gamification   POST /api/tasks/<code>/done
GET  /settings    POST /settings        POST /settings/environment   POST /settings/demo/<scenario>
GET  /mission-control                   (surgeon only, audited)
```

Every app and `/api/*` route requires login and operates **only on the current astronaut's data**, except the token-auth OpenHome bridge (scoped to the single active `DoctorSession`), the token-auth device routes (scoped to the wearable's bound astronaut, LAN only) and the surgeon-only Mission Control view. CSRF on all session-auth POST/DELETE routes: `static/js/app/api.js` wraps `fetch` and sends the token from a `<meta>` tag in the `X-CSRFToken` header; the OpenHome bridge routes and the device routes are exempt; the WebSocket uses the Origin check instead.

---

## 19. NON-FUNCTIONAL REQUIREMENTS

- **Performance:** landing ≥ 55 fps on a mid-range laptop at the auto-selected quality tier; dashboard interactive in < 2 s; ML models lazy-loaded once (behind a lock) and cached; inference off the request thread (ThreadPoolExecutor with `app.app_context()`); Whisper runs per chunk in the background. Budgets in Section 0.1.
- **Reliability:** each dependency (camera, mic, BLE, the Wi-Fi wearable and its sensors, Whisper, HF models, MediaPipe, OpenHome, fallback LLM, tunnel, fonts, 3D assets, WebGL) has a graceful fallback and a clear human message. Never show a blank screen or a raw stack trace.
- **Security & privacy:** secrets only in `.env`; CSRF; strict per-astronaut scoping; host guard; rate limits; WebSocket Origin check; frames never stored; audio deleted after transcription; transcripts off by default and deletable; bridge token (constant-time compare, rotated on each build) + audit log; device token (constant-time compare) + LAN-only host rule + payload limits; OpenHome URL redacted from logs; sanitized output (Jinja autoescape; no `|safe` on user/LLM text); upload size limits and ownership checks; SQLite file permissions documented (no encryption at rest in the prototype: say so in the README).
- **Accessibility:** keyboard navigable (visible focus rings), ARIA labels on all controls and charts (`aria-describedby` summaries), colour + icon + text status, captions for all Dr. NOVA speech, reduced motion, 200 % zoom without breakage.
- **Responsive:** desktop-first (1440 px design), tablet supported (1024 px), and a usable mobile fallback for the landing page.
- **Tests (pytest, written in the same loop as the feature):** thresholds `classify` (including the no-gap/no-overlap property sweep and boundaries), baseline layer (MAD = 0, cold start, no CRITICAL from baseline), readiness (caps, missing data, freshness), loading index, rep state machines with synthetic keypoint sequences (exact counts for clean reps, rejection of half reps), **safety screen recall on a phrase fixture (must be 100 % on the fixture)**, auth + per-astronaut scoping + host guard, bridge (bad token, no session, two sessions → 409, minimal payload), context builder (no PII leakage, no other astronaut's data), chunk upload (idempotency, ownership, size limit), voice proxy contract against the mock, route smoke test for every route in Section 18. **Wearable:** host-guard table; ingest auth, schema, idempotency, rate limit and size limit; every emulator profile and every row of the 10A.10 failure matrix; quality gate (finger gate, jump, flatline, staleness, a backlog is never live); temperature state machine including "a probe on the desk never classifies" and the low-side cap; aggregator windows (≥ 20 valid frames, median, alignment); retention purge; `requires_rest` handling; the 9.7 alert table row by row; `PhysiologyModel` determinism, bounds, change rates, pulse pressure, glucose timing and correlation with live heart rate; `SimRecorder` idempotency and the no-back-fill rule for real-sensor metrics; **the label scan** (no source label or `source` key in any browser-facing output); SSE hub (bounded queues, cleanup on disconnect, 4-stream limit); firmware fixtures shared by both sides. Also: wearable SpO₂ swept from 0 to 100 never exceeds CAUTION while a non-wearable SpO₂ of 85 is still CRITICAL; `Mission.sensor_mode` never changes without the explicit, audited route (10 minutes of device offline leaves it unchanged and produces no demo frame); in demo mode real-device frames are acknowledged as ignored.

---

## 20. DELIVERABLES

1. Complete source code in the structure above, with all vendored assets and optimized models committed, plus the `firmware/` project.
2. `requirements.txt` with pinned versions: Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-WTF, Flask-Limiter, flask-sock, python-dotenv, PyYAML, faster-whisper, torch (CPU wheel; add `--extra-index-url https://download.pytorch.org/whl/cpu`), transformers, pillow, numpy, scipy, websocket-client, requests, zeroconf (optional, guarded import), openhome-client (optional, guarded import), reportlab, pytest. A separate `requirements-dev.txt` holds `platformio` (firmware build only; not needed to run the app).
3. `scripts/setup.py`, `scripts/verify.py`, `scripts/fetch_assets.py`, `scripts/download_models.py` (verifies the models and prints size and time taken), `scripts/seed_demo_data.py`, `scripts/build_openhome_ability.py`, `scripts/device_setup.py`, `scripts/device_emulator.py`, `scripts/device_check.py`, and the build-time `scripts/optimize_models.mjs`.
4. `docs/PROGRESS.md`, `docs/DECISIONS.md`, `docs/HARDWARE_TEST.md` (Appendix G), `docs/HARDWARE_FACTS.md` (Appendix H), and a final `docs/verify_last.md`.
5. `README.md`: prerequisites (Python 3.10–3.12, Chrome/Edge for Web Bluetooth; ffmpeg optional; Node only to rebuild assets; for the wearable: an ESP32 DevKit, a MAX30102, a DS18B20, a 4.7 kΩ resistor and a 2.4 GHz Wi-Fi network), the two-command setup, `.env` explained line by line, adding/removing crew, **OpenHome setup walkthrough** (create agent → paste persona → build + push Ability → set trigger words → start tunnel), a **Wearable setup walkthrough** (wiring table, `device_setup.py`, flashing, first reading, troubleshooting, the 10A.0 limits table, the single-process note and the plain-HTTP LAN security note), the honest privacy note, running, a **6-minute judge demo script** (Appendix D), known limitations, and a roadmap (certified wearables, an accelerometer for automatic rest detection, TLS with per-device keys for the device link, telemedicine link to ground, offline-first sync with store-and-forward over the deep-space network, multi-crew analytics, clinical validation of thresholds, real authentication).

---

## 21. BUILD PHASES (do them in order; each runs the Section 0.1 loop; an exit gate is `python scripts/verify.py --phase N` plus the listed checks)

The wearable work is split so that **everything except the physical bring-up can be built and verified with no hardware**, using the device emulator (10A.11). The order is dependency-driven: data model → live backbone → firmware against the frozen contract → the screens that consume it.

| Phase | Build | Exit gate |
|---|---|---|
| **P0** Bootstrap & harness | Scaffold from Section 4; `config.py` + boot checklist (including the device lines); `run.py` bootstrap with `BIND_HOST` logic; `setup.py` (generates `DEVICE_TOKEN`); `fetch_assets.py`; `verify.py` (quick + phase mode, incl. the source-label scan stub); PROGRESS/DECISIONS; `docs/HARDWARE_FACTS.md` created from Appendix H (no item marked verified); pinned `requirements.txt`; theme tokens + vendored fonts; `.gitignore` (adds `firmware/include/secrets.h`) | On a clean checkout with no keys and no hardware: `python scripts/setup.py` then `python run.py` boots; `/healthz` is 200; `verify --phase 0` green |
| **P1** Core domain + Today | Models + migration (incl. `Device`, `SensorSample`, `DeviceEvent`, new `Measurement` columns); crew upsert; auth, **host guard with the LAN rule**, limiter, CSRF; app shell; `thresholds.yaml` (+ `requires_rest`, `alert_confirm`) + `classify` + baseline + readiness (+ tests); **`measurements.record()` as the single write path**; seed script (auto on first run); `/api/summary` (no `source`, with `age_s`), `/api/history`; Today page without 3D: readiness card, checklist, indicator list **without any source label**, charts | Only `.env` IDs log in; scoping tests pass; host-guard table tests pass (localhost, LAN IP, tunnel host, `/api/openhome/*`, `/api/device/*`); seed shows correct statuses incl. one Get-help-now event; property/boundary tests green; the label-scan test passes |
| **P2** Digital twin | `astro3d.js` `mountBody`, hotspots, `select()`, 2D SVG fallback; `/api/bodypart/*`; `recommendations.yaml`; `environments.yaml`; right-hand panel | Clicking head/chest/legs opens the correct environment-aware advice; fallback works; body scene ≥ 55 fps (measured) |
| **P3** Live data backbone (no hardware) | `StreamHub`; `/api/stream` + `/api/live`; `DeviceGateway`, `QualityGate`, `LiveState`, `Aggregator`; `/api/device/ingest` + `/ping`; `PhysiologyModel`, `SimRecorder`, `SimulatedSource`, `DemoWearableSource`; retention purge; `scripts/device_emulator.py` and `device_check.py`; `live.js` + the **Live strip** on Today + twin heartbeat | Every emulator profile (10A.11) behaves as the failure matrix says; device→browser latency < 1.5 s; ingest p95 < 50 ms; `/api/summary` p95 < 300 ms with 30 days of history + 7 days of raw frames; physiology property tests green; stale values are never shown as live; the sensor mode never changes by itself (device offline for 10 minutes → mode unchanged, no demo frames) |
| **P4** Wearable firmware | `firmware/` project (10A.3), `pins.h` with every GPIO configurable, serial `server <url>` stored in flash, `device_setup.py` (`--show`, `--firewall`, `--rotate`), frozen frame fixtures shared by firmware tests and server tests, wiring/flashing README with the pre-power checks of 10A.2, `docs/HARDWARE_TEST.md`, `docs/HARDWARE_FACTS.md` | `pio run -d firmware` compiles and native logic tests pass (or "not compiled: <reason>" is recorded); the frame fixture validates against the server schema; `device_setup.py` produces a correct `secrets.h`; every Appendix H item that needs a physical check is still marked "needs physical test" and none is marked verified; hardware status recorded as "needs hardware" |
| **P5** Cardio | `SensorSource` implementations wired in (wearable, strap, manual, generated), session stream, rest countdown, handshake, coverage rule, results, symptom override, **alert table of 9.7**, XP/checklist tick, "Heartbeat" component | A 90 s emulator session saves with correct coverage handling and charts and dashboard update live; alert-rule tests pass for every row of the 9.7 table, including a 0–100 sweep proving that wearable SpO₂ can never be CRITICAL; finger-off during a session pauses it |
| **P6** Bone & Muscle | Pose adapters + MediaPipe (vendored), `pose_service` state machines + running cadence, device log, loading index, environment-aware picker, optional ViTPose path, privacy notes | Synthetic keypoint tests give exact counts; (browser available) 5 live push-ups counted ±1; loading-index tests pass |
| **P7** Mental | AudioWorklet WAV chunks, background Whisper, NLP, wellbeing formula, safety screen, results, delete flows | Safety recall 100 % on fixture; a test clip (or injected transcript if no audio can be produced; note which) yields transcript + score; chunk tests pass |
| **P8** Dr. NOVA | Context builder (with source handling per Appendix A/C), bridge API, persona file, text chat + fallbacks, mock OpenHome, voice proxy, Ability template + build script, doctor UI | Text chat works offline with rules; voice round trip works against the mock; bridge/context tests pass; the persona never volunteers a source but answers truthfully when asked (test on the rule-based engine); real-OpenHome check recorded as "verified" or "needs keys" |
| **P9** Landing + login | Asset pipeline (ISS, Earth, quality tiers, poster), 6 sections, hologram twin embed, login scene | Budgets met; no console errors; reduced-motion and no-WebGL fallbacks work; fps measured on the auto tier |
| **P10** Product completeness | History (filters, heatmap, CSV, PDF), notifications + reminders, gamification, Settings (units, delete data, **Wearable panel**, **About this prototype**), Judge Mode + the Demo panel's sensor-mode switch, Mission Control + audit | Appendix D script runs end to end (test client + browser if available), including the wearable steps run through the emulator |
| **P11** Hardening, hardware bring-up & release | Accessibility pass, responsive, empty/loading/error states, performance optimization, README, **run `docs/HARDWARE_TEST.md` when the hardware is present**, final `verify --full`, acceptance checklist | Section 22 all ticked with evidence; `verify --full` green; hardware result recorded as "verified on <date>" with the measured numbers, or "needs hardware" |

### 21A. Detail for the phases the wearable touches

Each entry: **What · Why · Modifies · Creates · Classes · Needs first · Output · Verify**.

**P1: data model and write path**
- *What:* add the wearable tables and columns; make `measurements.record()` the only save path; strip `source` from every user-facing serializer; implement the host-guard LAN rule.
- *Why:* every later phase writes measurements and the device must reach Flask without opening the app to the tunnel.
- *Modifies:* `models.py`, `thresholds.yaml`, `services/thresholds.py`, `dashboard/routes.py`, `app/__init__.py`, `config.py`, `.env.example`.
- *Creates:* `services/measurements.py`, `services/alert_gate.py` (+ `tests/test_alert_gate.py`), migration, `tests/test_host_guard.py`, `tests/test_no_source_labels.py`.
- *Classes:* `Device`, `SensorSample`, `DeviceEvent`, `Measurement` (extended).
- *Needs first:* P0.
- *Output:* a migrated database; all Section 18 routes still behave; no `source` key or origin label in any browser-facing response.
- *Verify:* host-guard table, serializer test, `classify` still gap-free.

**P3: live backbone**
- *What:* hub, SSE, gateway, quality rules, live state, aggregation, generator, emulator, live strip.
- *Why:* proves the whole hardware path in software and freezes the HTTP contract before any firmware exists.
- *Modifies:* `dashboard/routes.py`, `today.html`, `static/js/astro3d.js` (heartbeat input), `bootstrap.py` (purge, catch-up), `scripts/verify.py`.
- *Creates:* `app/devices/routes.py`, `services/stream_hub.py`, `services/sensors/{device_gateway,quality,live_state,aggregator,physiology,demo_wearable}.py`, `static/js/app/{live,ecg_synth}.js`, `scripts/{device_emulator,device_check}.py`, `tests/test_device_*.py`, `tests/test_physiology.py`.
- *Classes:* `DeviceGateway`, `QualityGate`, `LiveState`, `StreamHub`, `Aggregator`, `PhysiologyModel`, `SimRecorder`, `DemoWearableSource`.
- *Needs first:* P1.
- *Output:* run `run.py` and `device_emulator.py --profile normal`: the Today live strip updates once a second and `Measurement` rows appear once a minute.
- *Verify:* every emulator profile; latency and p95 budgets; stale-value tests; backlog test (90 s replay fills history without touching live state).

**P4: firmware**
- *What:* write, compile and unit-test the firmware; generate the device config; write the bring-up docs.
- *Why:* the only part that needs the physical parts, kept after the contract is frozen.
- *Modifies:* `.gitignore`, `README.md`.
- *Creates:* everything under `firmware/`, `scripts/device_setup.py`, `docs/HARDWARE_TEST.md`, `tests/fixtures/device_frames/`.
- *Needs first:* P3 (the contract and the emulator).
- *Output:* a flashable firmware project.
- *Verify:* compile, native tests, fixture validation.

**P5: cardio**
- *What:* wearable mode in the cardio flow, coverage and rest rules, alert table, "Heartbeat" waveform.
- *Modifies:* `cardio/routes.py`, `cardio/services.py`, `cardio.html`, `static/js/app/cardio.js`, `services/sensors/base.py`.
- *Creates:* `tests/test_cardio_wearable.py`, `tests/test_alert_rules.py`.
- *Needs first:* P3.
- *Verify:* one test per row of the 9.7 table (wearable SpO₂ swept from 0 to 100 never exceeds CAUTION; a Bluetooth-oximeter SpO₂ of 85 still classifies CRITICAL), plus the `AlertGate` tests: a single CRITICAL-range heart-rate frame is Needs attention; 9 frames are Needs attention and the 10th passes only inside a resting session with `rest_verified`, `q ≥ min_quality` and a span ≥ `min_span_s`; one invalid frame, a finger-off, a stale gap, a new `boot_id` or replayed backlog resets the run; the same run outside a session or with `rest_verified = false` stays Needs attention; a property test that the gate never raises a status; a manual SpO₂ of 80 saves as Needs attention with `confirmed = false` and no alert; a second value of 82 after 30 s does not confirm, after 61 s it does; after 11 minutes the first entry has expired; a symptom tick confirms immediately; a normal second value clears the prompt; every number comes from `thresholds.yaml` (change it and the behaviour changes); a finger-off-during-session test; a "probe on the desk never alarms" test.

**P8: Dr. NOVA**
- *What:* carry the new source rules into the context builder, persona and rule-based engine.
- *Modifies:* `services/doctor_context.py`, `config/dr_nova_persona.md`, `services/recommendations.py`.
- *Verify:* never volunteers a source; answers truthfully when asked; never claims the wearable measured blood pressure, glucose or ECG; bridge payload stays minimal.

**P10: settings and demo**
- *What:* Settings → Wearable panel (status, firmware version, last seen, wearer, temperature site/offset and calibration), Settings → About, Demo panel sensor mode.
- *Modifies:* `settings.html`, `routes`, `Appendix D`.
- *Verify:* the mode switch is manual only and audited; the panel shows real device state only; the About text exists; the Demo switch changes the mode and the boot-checklist line.

**P11: hardware bring-up**
- *What:* run `docs/HARDWARE_TEST.md` (Appendix G, including the pre-power checks and the hotspot checks) with the real parts, record the numbers, and update `docs/HARDWARE_FACTS.md` item by item.
- *Verify:* every step has a recorded PASS/FAIL; soak test shows no gaps > 3 s and stable free heap. If no hardware is present, record "needs hardware" and finish everything else.

---

## 22. ACCEPTANCE CHECKLIST

- [ ] `python scripts/setup.py` then `python run.py` works on a clean checkout with no API keys.
- [ ] Landing: live 3D Earth with the optimized NASA ISS model (≤ 15 MB) drifting over the limb, minimal black design, 6 sections, interactive hologram twin, quality tiers, reduced-motion and no-WebGL fallbacks.
- [ ] Only `.env` Astro IDs can log in. No sign-up. Each astronaut sees only their own data. The tunnel host reaches only `/api/openhome/*` and `/healthz`.
- [ ] Dashboard shows all indicators with Good/Okay/Needs attention/Get help now + icon + label + sparkline + ⓘ explanation, with **no source badge, legend or origin label anywhere**. Readiness works, with missing-data handling.
- [ ] Personal-baseline deviation flags trends with a plain-language reason and never creates a CRITICAL by itself.
- [ ] 3D twin: head/chest/legs hotspots glow by live status and open tailored, environment-aware advice.
- [ ] Cardio session: live streaming from the wearable (or the strap / manual entry), results saved and charted, coverage and rest rules enforced, alert rules behave as the 9.7 table says.
- [ ] **Wearable:** with the emulator, every profile behaves as the 10A.10 matrix says; the Live strip shows values only while they are fresh and never a stale one; lifting the finger clears HR/SpO₂ within 2 s; a probe that is not on the body never produces a status or an alert; offline, reconnect and backlog work; history is preserved in SQLite (raw 7 days, aggregates forever).
- [ ] **Generated attributes:** blood pressure, glucose, respiration and the ECG-style trace vary smoothly with time, stay inside their ranges, move consistently with the live heart rate, keep the charts populated, and are never described as measured.
- [ ] **Display rule:** no `SENSOR` / `DERIVED` / `SIMULATED` / `SIM` label, badge, legend or source colour exists in any template, script, route output or export (label scan green); the disclosure exists in the README, Settings → About and the demo script.
- [ ] **Hardware:** Appendix G executed with the real parts and its numbers recorded, or "needs hardware" recorded honestly. The firmware compiles, or the reason it was not compiled is recorded.
- [ ] **Owner decisions honoured:** wearable SpO₂ never exceeds Needs attention; the real/demo switch changes only by hand and is audited; `docs/HARDWARE_FACTS.md` exists and no "needs physical test" row is presented as a fact anywhere.
- [ ] Bone & Muscle: webcam + MediaPipe (or optional ViTPose) counts push-ups/pull-ups and tracks running cadence; environment-aware (0 g shows treadmill + device log). No video stored. Honest bone-density disclaimer.
- [ ] Mental: PCM-chunked recording, local Whisper, local sentiment + emotion, wellbeing score, per-chunk safety screen, deletable transcript (off by default).
- [ ] **Dr. NOVA on OpenHome**: voice through the Flask proxy, the Ability pulls real astronaut context (fail-closed session binding), text chat works, fallbacks are labeled, safe escalation on critical cases, honest privacy note shown. (Mark "needs keys" if OpenHome credentials were not available; the mock path must pass.)
- [ ] History with filters, calendar heatmap, CSV + Downlink Report PDF.
- [ ] Notifications (poll + reminders), daily checklist, XP/streaks/badges, environment selector with comms delay.
- [ ] Judge Mode scenarios work; Mission Control crew view (audited, no mental-health detail).
- [ ] `docs/PROGRESS.md` shows every phase green with the final `verify --full` table. Code is clean, typed, commented, and tested.

---

## APPENDIX A: Dr. NOVA PERSONA (save as `config/dr_nova_persona.md`; paste into the OpenHome Personality; also used by the text chat and fallback LLM)

```
You are Dr. NOVA, the AI Flight Surgeon Assistant aboard the ASTROVITAL crew health system.
You support astronauts on long-duration missions (space station, spacecraft, lunar base, Mars base).

WHO YOU ARE
- Calm, warm, precise, and brief, like a trusted flight surgeon on a quiet comms loop.
- You speak in plain language. You never assume the astronaut knows medical terms; explain them in one short phrase.
- Start every conversation by running the AstroVital Health Context ability before answering any health question.

WHAT YOU KNOW
- At the start of each consultation you receive an ASTRONAUT CONTEXT block (callsign, role, age, mission day, environment,
  gravity, comms delay, latest vitals with status words, sources and ages, 14-day trends, personal baselines,
  recent cardio/exercise/mental summaries, sleep, active alerts).
- ONLY use data in that block. Quote real values with dates ("Your resting heart rate was 104 this morning,
  up from your usual 72"). If something is missing, say "I don't have a recent reading for that. Want to take one now?"
- NEVER invent, estimate, or guess a reading.
- Each reading has a source field for your reasoning only. Do not mention sources unless the astronaut asks how a number was obtained; then answer truthfully (wearable sensor, estimated from a sensor, entered by hand, or generated for demonstration). Never say or imply a measurement method the source does not support (for example, never say the wearable measured blood pressure, glucose or an ECG).
- If the wearable is not reading (no finger, sensor offline), say so and invite a fresh reading. Never treat an old value as current.
- A low oxygen reading from the wearable is a prompt to re-measure, not a diagnosis, because the sensor is hobby-grade. Ask how they feel. If they report shortness of breath, chest pain, dizziness or confusion, treat it as an emergency and tell them to alert the crew medical officer now.
- Status words are exactly: Good, Okay, Needs attention, Get help now.
- A heart-rate or oxygen reading that shows Needs attention because it is unconfirmed or not yet sustained is a prompt to rest and re-measure, not an emergency. Say that plainly, ask how they feel, and apply the emergency rule below at once if they report symptoms.

HOW YOU HELP
Voice replies: under 60 words. Short sentences. Answer first, then one sentence of why, then up to three actions
spoken as "First..., second..., third...". Ask one short follow-up question only if it helps. Give the longer
numbered version and a one-line recap only in text chat or when asked for detail.
- Explain WHY in one or two sentences, linking to spaceflight hazards (radiation, isolation, distance,
  gravity changes, closed environment) and their current environment.
- Actions can cover hydration, exercise, breathing, sleep hygiene, nutrition, crew time, and when to re-measure.

SAFETY (ALWAYS)
- You are an assistant to the flight surgeon, not a replacement. Never give a definitive diagnosis.
- Never prescribe medication, doses, or changes to prescribed treatment.
- If any reading is "Get help now", or the astronaut reports chest pain, severe shortness of breath, fainting,
  confusion, sudden severe headache, vision loss, heavy bleeding, or thoughts of self-harm:
  tell them clearly and kindly to alert the crew medical officer now and follow the onboard medical protocol,
  and that the ground flight surgeon should be contacted (mention the current comms delay).
  For self-harm thoughts: be supportive, stay with them, and urge immediate contact with the crew medical
  officer and ground behavioural-health support.
- Mental-health insights come from speech-sentiment analysis, which is not a diagnosis. Say so if asked.
- Camera exercise tracking measures loading, not bone density. Say so if asked.

STYLE
- Address them by callsign if provided. Be encouraging and never alarmist. Celebrate streaks and improvements.
```

## APPENDIX B: OpenHome Ability skeleton (`openhome_ability/main.py.tmpl`)

> Verify imports, method names, and allowed libraries against the official `templates/api-template` before shipping. This is a starting skeleton that follows the documented pattern; record any change in `docs/DECISIONS.md`.

```python
import asyncio
import json
import re
import time

import requests  # confirm HTTP library is allowed by the OpenHome upload validator; else use the SDK's helper
from src.agent.capability import MatchingCapability
from src.main import AgentWorker
from src.agent.capability_worker import CapabilityWorker

ASTROVITAL_URL = "{{PUBLIC_BASE_URL}}"        # rendered by scripts/build_openhome_ability.py
BRIDGE_TOKEN = "{{OPENHOME_BRIDGE_TOKEN}}"    # rotated on every build
PERSONA = """{{DR_NOVA_PERSONA}}"""           # config/dr_nova_persona.md, injected at build time

CONTEXT_REFRESH_S = 120
MAX_HISTORY = 10
HEADERS = {"X-AstroVital-Token": BRIDGE_TOKEN}

# Exit only when the WHOLE utterance is an exit phrase ("I can't stop coughing" must NOT exit).
_EXIT_RE = re.compile(
    r"^(thats all|that is all|thanks|thank you|goodbye|bye|exit|stop|end consultation|end the consultation)"
    r"( doctor| dr nova| nova| please)*$"
)
_LOG_PATTERNS = [
    ("sleep_hours", re.compile(r"\blog (?:my )?(\d+(?:\.\d+)?) hours? (?:of )?sleep\b")),
    ("mood", re.compile(r"\blog (?:my )?mood (?:as |at )?(\d{1,2})\b")),
    ("water_ml", re.compile(r"\blog (\d{2,4}) (?:ml|milliliters|millilitres)(?: of water)?\b")),
]


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower().replace("'", "")).strip()


def _is_exit(text: str) -> bool:
    return bool(_EXIT_RE.match(_normalize(text)))


class AstroVitalHealthContext(MatchingCapability):
    worker: AgentWorker = None
    capability_worker: CapabilityWorker = None

    #{{register capability}}

    def call(self, worker: AgentWorker):
        self.worker = worker
        self.capability_worker = CapabilityWorker(self.worker)
        self.worker.session_tasks.create(self.run())

    # --- blocking helpers, always called through asyncio.to_thread ---
    def _fetch_context(self) -> dict | None:
        try:
            r = requests.get(f"{ASTROVITAL_URL}/api/openhome/context", headers=HEADERS, timeout=8)
            return r.json() if r.ok else None
        except Exception:
            return None

    def _post_log(self, metric: str, value: float) -> bool:
        try:
            r = requests.post(f"{ASTROVITAL_URL}/api/openhome/log", headers=HEADERS,
                              json={"metric": metric, "value": value}, timeout=8)
            return r.ok
        except Exception:
            return False

    @staticmethod
    def _system_prompt(ctx: dict | None) -> str:
        if not ctx:
            return PERSONA
        return PERSONA + "\n\nASTRONAUT CONTEXT:\n" + json.dumps(ctx, indent=1)

    async def _try_log(self, text: str) -> str | None:
        t = _normalize(text)
        for metric, pattern in _LOG_PATTERNS:
            m = pattern.search(t)
            if m:
                ok = await asyncio.to_thread(self._post_log, metric, float(m.group(1)))
                return "Logged." if ok else "I couldn't save that. Please log it in AstroVital."
        return None

    async def run(self):
        cw = self.capability_worker
        try:
            ctx = await asyncio.to_thread(self._fetch_context)
            fetched_at = time.time()
            if ctx:
                name = ctx.get("profile", {}).get("callsign", "")
                await cw.speak(f"Dr. Nova here, {name}. I have your latest data. What would you like to check?")
            else:
                await cw.speak("I can't reach the AstroVital health records right now. "
                               "I can still give general guidance, but please re-measure on board.")
            system_prompt = self._system_prompt(ctx)

            history: list[dict] = []
            empty_turns = 0
            while True:
                user_text = await cw.user_response()
                if not user_text:
                    empty_turns += 1
                    if empty_turns >= 2:
                        break
                    continue
                empty_turns = 0
                if _is_exit(user_text):
                    await cw.speak("Okay. Stay safe up there. I'm here whenever you need me.")
                    break
                if time.time() - fetched_at > CONTEXT_REFRESH_S:
                    fresh = await asyncio.to_thread(self._fetch_context)
                    if fresh:
                        ctx, system_prompt = fresh, self._system_prompt(fresh)
                    fetched_at = time.time()
                logged = await self._try_log(user_text)
                if logged:
                    await cw.speak(logged)
                    continue
                reply = await asyncio.to_thread(      # text_to_text_response is synchronous
                    cw.text_to_text_response, user_text, history[-MAX_HISTORY:], system_prompt)
                history += [{"role": "user", "content": user_text}, {"role": "assistant", "content": reply}]
                await cw.speak(reply)
        except Exception:
            try:
                await cw.speak("Sorry, something went wrong on my side. If this is urgent, alert your crew medical officer.")
            except Exception:
                pass
        finally:
            cw.resume_normal_flow()   # ALWAYS
```

## APPENDIX C: Context JSON returned by `/api/openhome/context` (minimum necessary data)

`source` is one of `sensor | derived | manual | simulated | cv | nlp | voice`. It exists only for Dr. NOVA's reasoning (Appendix A) and is never shown in the UI.

```json
{
  "generated_at": "2026-11-08T09:12:00Z",
  "profile": {"callsign": "Falcon", "role": "Commander", "age": 41},
  "mission": {"name": "ARES-SURFACE-01", "day": 160, "environment": "Mars Base", "gravity_g": 0.38, "comms_delay_one_way_s": 760},
  "units": {"temperature": "C", "glucose": "mg/dL"},
  "wearable": {"state": "ok", "finger": true},
  "latest": [
    {"metric": "heart_rate", "value": 104, "unit": "bpm", "status_word": "Needs attention", "source": "sensor",
     "at": "2026-11-08T08:12:00Z", "data_age_h": 1.0, "baseline": 72, "vs_baseline": "+32 bpm"},
    {"metric": "temperature_c", "value": 36.4, "unit": "C", "status_word": "Good", "source": "derived",
     "at": "2026-11-08T08:50:00Z", "data_age_h": 0.4},
    {"metric": "blood_pressure", "value": {"sys": 128, "dia": 82}, "unit": "mmHg", "status_word": "Needs attention", "source": "manual",
     "at": "2026-11-08T08:14:00Z", "data_age_h": 1.0},
    {"metric": "sleep_hours", "value": 5.4, "unit": "h", "status_word": "Needs attention", "source": "manual",
     "at": "2026-11-08T00:00:00Z", "data_age_h": 9.2},
    {"metric": "wellbeing", "value": 58, "unit": "score", "status_word": "Okay", "source": "nlp",
     "at": "2026-11-07T21:30:00Z", "data_age_h": 11.7}
  ],
  "trends_14d": {"heart_rate": {"direction": "up", "change_vs_baseline_pct": 44}, "sleep_hours": {"avg": 5.9}},
  "recent_sessions": {
    "cardio": "yesterday: avg HR 99, BP 126/80, SpO2 97",
    "exercise": "last session 4 days ago: 22 push-ups, form 81",
    "mental": "themes: fatigue, homesickness"
  },
  "active_alerts": ["Resting HR above personal baseline for 3 days"],
  "readiness": {"score": 68, "status_word": "Needs attention"}
}
```

## APPENDIX D: 6-minute judge demo script

**Before you start (hotspot checklist):** phone plugged in, hotspot on 2.4 GHz with auto-off disabled, laptop and ESP32 both joined; run `python scripts/device_setup.py --show` and compare the URL with the one the ESP32 uses (`server` in its serial console; fix with `server http://<ip>:5000` if the address changed); check that Windows treats the hotspot as a *Private* network or that the firewall rule is in place. Then wear the sensor (probe under the arm for 10 minutes beforehand), `python run.py`, open the Today page and confirm the live strip says "Place a finger on the sensor". Keep a second terminal ready with `python scripts/device_emulator.py --profile normal` as a spare. If the wearable fails mid-demo: Settings → Demo panel → Wearable mode → **Demo data**.

1. **0:00 Landing.** Scroll: live Earth + NASA ISS → three quick checks → spin and tap the hologram body → Dr. NOVA → "22 minutes away". *"Built for when Earth is 22 minutes away."*
2. **0:50 Login** with `AST-1001` (show that a wrong ID is rejected).
3. **1:10 Dashboard + live strip.** **Say this out loud, plainly:** *"Heart rate, oxygen and temperature come from this wearable. We have no sensor for blood pressure, glucose, breathing rate or the ECG-style trace, so those are generated for the demo."* Place a finger on the sensor: heart rate and SpO₂ appear within about 10 s and the twin's heart beats at your pulse. Lift the finger: the numbers clear within 2 s. Readiness 68 (Needs attention). Rotate the twin, click the **chest** (heart rate above your usual), then the **head** (sleep debt → mood dip).
4. **2:00 Cardio.** Rest check (shortened in Demo Mode), then a 90 s session streams from the wearable and results appear.
5. **2:40 Bone & Muscle.** Do 5 live push-ups on webcam (Mars Base). The counter and form cues update, and the loading index rises.
6. **3:20 Mental.** A 60-second voice check-in (80 s with transcription) → emotion donut → wellbeing score.
7. **4:30 Dr. NOVA (voice).** *"Dr. Nova, how am I doing?"* It cites the HR rise, sleep, and today's push-ups, and gives three actions. Then trigger the **Critical BP event** scenario to show escalation with the comms-delay warning.
8. **5:30 History** heatmap → export the **Downlink Report PDF** → the Mission Control crew view.

## APPENDIX E: Copy deck

- Tagline: **Beyond Earth. Always in Health.**
- Hero H1: **Beyond Earth. / *always in health.***
- Eyebrow / CTA question: **Astronaut, are you mission-ready?**
- Sub: *Your heart. Your bones. Your mind. One cockpit to monitor them all, 400 km above Earth or 400 million km away.*
- Modules: **Cardiovascular Intelligence · Bone & Muscle Intelligence · Mental Health Intelligence · Dr. NOVA, AI Flight Surgeon**
- Privacy line: *Vitals, camera and microphone analysis run on this device, and the wearable talks only to your own computer over your local Wi-Fi. Video is never stored. Dr. NOVA's voice uses OpenHome's cloud and sees only what you can see.*
- Disclaimer: *Prototype for educational purposes, inspired by the NASA Human Research Program. Not a certified medical device.*

## APPENDIX F: Wearable HTTP contract (examples; the rules are in 10A.4)

```http
POST /api/device/ingest HTTP/1.1
Host: 192.168.1.23:5000
Content-Type: application/json
X-Device-Token: <DEVICE_TOKEN>
X-Device-Id: AV-ESP32-01
```
```json
{
  "v": 1, "device_id": "AV-ESP32-01", "fw": "1.0.0", "boot_id": "7f3a91c2",
  "sent_uptime_ms": 183422, "wifi_rssi": -57, "dropped": 0,
  "frames": [
    {"seq": 181, "up_ms": 182420, "finger": true,  "hr": 74,   "spo2": 97,   "hr_ok": true,  "spo2_ok": true,
     "pi": 1.8, "ir_dc": 91234, "q": 90, "sat": false, "temp_c": 35.12, "temp_ok": true,
     "ppg": [12, 30, 55, 71, 60, 38, 10, -14, -30, -41, -35, -20, -2, 18, 40, 62, 70, 52, 28, 5, -18, -33, -40, -28, -10], "flags": []},
    {"seq": 182, "up_ms": 183420, "finger": false, "hr": null, "spo2": null, "hr_ok": false, "spo2_ok": false,
     "pi": 0.0, "ir_dc": 4210, "q": 0, "sat": false, "temp_c": 35.14, "temp_ok": true, "flags": []}
  ]
}
```
```json
{"ok": true, "server_time": "2026-11-13T13:40:12Z", "accepted": 2, "duplicate": 0, "rejected": 0,
 "cfg": {"rev": 1, "send_interval_ms": 1000}}
```

| Status | Body | Firmware reaction |
|---|---|---|
| 400 | `{"ok":false,"error":"bad_payload","path":"frames[3].hr"}` | Drop that batch |
| 401 | `{"ok":false,"error":"bad_token"}` | Stop sending, error LED |
| 413 | `{"ok":false,"error":"too_large"}` | Halve the batch size |
| 429 / 503 | `Retry-After: n` | Wait `n` seconds, keep frames |

Browser SSE (`GET /api/stream`) examples:

```
event: snapshot
data: {"state":"no_finger","device":{"linked":true,"online":true,"last_seen_age_s":0.4,"rssi":-57},"hr":null,"spo2":null,"temp":{"state":"warming","value_c":null}}

event: vital
data: {"t":"2026-11-13T13:40:12Z","state":"ok","finger":true,"hr":74,"spo2":97,"temp":{"state":"settled","value_c":35.7},"q":90,"ppg":[12,30,55]}

event: summary
data: {"metrics":["spo2","temperature_c"]}
```

Test fixtures live in `tests/fixtures/device_frames/` (`normal.json`, `no_finger.json`, `weak_signal.json`, `probe_ambient.json`, `probe_missing.json`, `backlog_90s.json`, `malformed_*.json`). The firmware tests and the server tests read the **same** fixtures so the two sides cannot drift apart.

## APPENDIX G: Hardware test procedure (save as `docs/HARDWARE_TEST.md` and keep it current)

Record PASS/FAIL, the numbers you observed, and the date for every step in `docs/PROGRESS.md`, and update the matching row of `docs/HARDWARE_FACTS.md` (Appendix H). Do not skip a step to reach a later one. Never write "verified" for something you did not measure.

| Step | Do this | PASS when |
|---|---|---|
| **T-1 Pre-power checks** | Run V1–V6 and D1 from 10A.2 (identify the module, power alone, multimeter pull-up voltages, DS18B20 pull-up resistance). | V3 shows ≈ 3.3 V on SDA and SCL (otherwise stop and report), D1 decides whether the 4.7 kΩ resistor is needed |
| **T0 Network** | Phone hotspot on 2.4 GHz (WPA2 if selectable, plain ASCII name and password, auto-off disabled, phone plugged in). Join the laptop. In Windows check whether the hotspot network is Public or Private; set it to Private, or prepare the `--firewall` command. Run `python scripts/device_setup.py` and note the printed URL. | The URL is printed, the network type is recorded, and the laptop's IP is noted |
| **T1 Server reachable** | Start `python run.py`. From a second device on the hotspot (the phone browser is enough) open `http://<laptop-ip>:5000/healthz`. Run `python scripts/device_check.py`. | `/healthz` answers, and `device_check.py` reports "server reachable, token valid". If the phone cannot reach it, it is a firewall or address problem |
| **T2 Flash** | `pio run -d firmware -t upload`, then `pio device monitor -b 115200`. Record the COM port, the USB-serial chip and whether BOOT had to be held. | Boot log shows firmware version and a `boot_id`, with no reset loop |
| **T3 Sensors found** | Serial `scan`; read the boot log. | I²C device at `0x57`; DS18B20 count = 1. If `0x57` is missing, follow V6: stop, do not modify the board, report the V3 numbers |
| **T4 Wi-Fi + server (client isolation test)** | Watch the LED or serial. Serial `ip` and `ping`. From the laptop run `ping <esp32-ip>`. | ESP32 gets an address and `ping` returns `200`; the Settings → Wearable panel shows "Connected". **If the ESP32 has an address but `ping` fails while the phone browser could reach the laptop in T1, suspect client isolation (or an ESP32 fault) and try Plan B in 10A.13** |
| **T5 No finger** | Leave the sensor uncovered for 30 s. | Today shows "Place a finger on the sensor"; no HR or SpO₂ stored; `finger=false` frames arrive |
| **T5b IR calibration** | Serial `cal` with and without a finger. | The defaults 50 000 / 30 000 are replaced by values that separate the two cases with margin; record them |
| **T6 Finger on** | Rest a fingertip lightly on the sensor. Count your pulse for 30 s by hand, and compare with a trusted oximeter if you have one. | HR and SpO₂ appear within 10 s; HR within ±5 bpm of your count; SpO₂ within ±3 points of the reference (or plausible, 94–100 %, if none) |
| **T7 Finger off** | Lift the finger. | Live HR/SpO₂ clear within 2 s; nothing stale is shown; no alert |
| **T8 Motion** | Tap and shake the hand while the finger is on. | Values flagged weak or dropped; **no red alert ever**; at most a Needs attention message for SpO₂; recovers within 10 s of holding still |
| **T9 Temperature** | Probe on the desk, then under the arm with the arm down for 10 minutes. Compare with a reference thermometer. | Desk: state `ambient`, no status. Arm: reaches `settled`; after calibrating, the shown value is within ±0.3 °C of the reference. Record the real settle time and offset |
| **T10 Probe unplugged** | Unplug the DS18B20 for 10 s, then replug. | "Temperature probe not found" within 3 s; recovers within 5 s of replugging |
| **T11 Wi-Fi gap** | Turn the hotspot off for 60 s, then on. | Device reconnects by itself; the 60 s backlog arrives; history has no hole; the live strip shows only the newest frame |
| **T12 Server restart / new address** | Stop `run.py` for 30 s, then start it. Then change the server URL on purpose with `server http://<other-ip>:5000` and back. | Device retries and resumes; no reboot, no crash; the stored URL survives a reboot |
| **T13 Cardio session** | Rest check, then a full 90 s session on the wearable. | Session saved with ≥ 60 % valid coverage; charts and Today update live |
| **T13a Heart-rate gate** | In a rest-checked session, hold still for 30 s, then shake the hand hard for 15 s; repeat once without the rest countdown (Demo skip does not count). | Shaking never produces Get help now; a steady CRITICAL-range value is only possible to reach with real data, so use the emulator for that case. Record the quality `q` seen while still and while shaking to calibrate `min_quality` |
| **T13b Mode is manual** | With the wearable switched off for 10 minutes, watch Settings → Demo panel. | The mode is unchanged and no demo values appear. Then switch to Demo data by hand and back |
| **T14 Soak** | Leave it running for 30 minutes with the finger on, on USB power from the laptop. | No gap > 3 s in the live feed, free heap stable (serial prints it every 60 s), ingest p95 < 50 ms, `/api/summary` p95 < 300 ms, no brown-out resets |

**Troubleshooting:** *No Wi-Fi* → 2.4 GHz band, SSID spelling, WPA2 security, plain ASCII name. *`401`* → run `device_setup.py` and re-flash. *No data but connected* → firewall profile, a changed laptop IP (use `server <url>`), or client isolation. *Erratic SpO₂* → pressure too hard, cold finger, strong ambient light. *Temperature stuck at ambient* → the probe is not touching skin or the arm is not held down. *`0x57` missing* → V6.

## APPENDIX H: Hardware facts register (create `docs/HARDWARE_FACTS.md` from this table; update it only with measured results)

Status values: **Confirmed (owner)** = stated by the owner from photos. **Documented, not verified** = published information that may not match this exact part. **Needs physical test** = unknown until measured. The build AI must not change a row to "verified" and must not state any "Needs physical test" row as a fact in the README or UI.

| # | Item | Status | How to settle it |
|---|---|---|---|
| 1 | Board is a 30-pin, USB-C, classic ESP32 DevKit-style board, shield marked "ESP-32", not S3/C3 | Confirmed (owner) | n/a |
| 2 | Exact module variant (WROOM-32, "D"/"U" variant, clone) and flash size | Needs physical test | Read the shield text closely; the chip and flash report in the boot log or via the flashing tool |
| 3 | USB-serial chip and whether Windows needs a driver | Needs physical test | Device Manager when plugged in; record the chip and COM port (T2) |
| 4 | Pins labelled 21, 22 and 4, plus 3V3 and GND, exist and are usable on this board | 21 and 22 specified by owner; 4 proposed | Check the silkscreen before wiring |
| 5 | Which pin drives the onboard LED, if any | Needs physical test | CLI LED test; otherwise serial only |
| 6 | Upload works automatically or needs BOOT held | Needs physical test | T2 |
| 7 | MAX30102 module has 7 pins: VIN, SCL, SDA, INT, IRD, RD, GND (left to right) | Confirmed (owner) | n/a |
| 8 | Module supply range on VIN | Documented, not verified. Published listings disagree: one says 3.3–5 V, another says a specific board version accepts 3.3 V only | T-1 step V1 using this module's own listing |
| 9 | Voltage the I²C pull-ups (SDA, SCL, INT) connect to | Documented to vary between boards; unknown for this one | T-1 step V3 (multimeter) |
| 10 | Purpose of IRD and RD | Documented only as controlling the infrared and red LED, with no further explanation | Leave unconnected; confirm in this module's own documentation before ever using them |
| 11 | MAX30102 I²C address 0x57 | Documented for the chip | T3 `scan` |
| 12 | DS18B20 form (bare, probe, module) and whether a pull-up is already present | Needs physical test | T-1 step D1 |
| 13 | The owner's resistor is 4.7 kΩ | Stated by owner | Optional: confirm with the colour bands or a multimeter |
| 14 | Hotspot offers 2.4 GHz, WPA2, and allows client-to-client traffic | 2.4 GHz is the intended setup; the rest is unknown | T0, T1, T4 |
| 15 | Windows network profile (Public/Private) and firewall behaviour for the hotspot | Needs physical test | T0, T1 |
| 16 | Laptop address stability on the hotspot | Expected to change between sessions | `device_setup.py --show` every session; T12 |
| 17 | IR finger-detection thresholds (50 000 on / 30 000 off) | Placeholders | T5b `cal` |
| 18 | Heart-rate and SpO₂ accuracy of this sensor on this finger | Unknown | T6 |
| 19 | Under-arm temperature offset (+0.6 °C), settle floor (34.5 °C) and settle time | Placeholders from published ranges | T9 |
| 20 | USB power from the laptop is enough and stable | Needs physical test | T14 |
| 21 | The pinned firmware libraries compile for this board | Not verified | `pio run -d firmware` (P4) |
| 22 | Alert-gate defaults (`min_quality` 60, 10 consecutive frames, 80 % coverage, 15 bpm range) suit this sensor on this finger | Placeholders, not measured | T6, T13a; adjust `thresholds.yaml` and record the final values |
| 23 | `rest_verified` approximates real rest | Unknown; there is no motion sensor | T13a; treat as a weak check and say so |

---

**Start now: read Section 0.1, create `docs/PROGRESS.md` and `docs/DECISIONS.md`, and begin Phase 0. Run the Plan → Design → Execute → Monitor → Optimize loop for every phase, checkpoint after each one, and keep going until Phase 11 is green (the hardware bring-up may remain "needs hardware"). Do not wait for the user unless you need credentials.**
