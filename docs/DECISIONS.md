# DECISIONS

Deviations from `PROMPT.md` and choices it left open. Newest at the bottom.

## Phase 0

| # | Decision | Why |
|---|---|---|
| D1 | **Python 3.13.5 is the build and test interpreter.** | It is the only Python on the build machine. The prompt recommends 3.10–3.12 and lists 3.13 as "tested last". Every pinned package, including torch, transformers and faster-whisper, installed and loaded on 3.13. 3.10–3.12 are untested here. |
| D2 | **`setup.py` installs into a project virtual environment (`.venv`), and `run.py` re-runs itself inside it.** `--no-venv` installs into the current Python instead. | Installing torch and Flask into the system Python can break other projects. The two-command path (`python scripts/setup.py`, `python run.py`) still works without activating anything, through `scripts/_bootstrap_env.py`. An already-active virtual environment is used as is. |
| D3 | **`requirements.txt` includes two files: `requirements-core.txt` and `requirements-ml.txt`.** | `pip install -r requirements.txt` still installs everything. Splitting lets `setup.py` treat the web packages as required and the ML packages as best-effort, so a failed 200 MB torch download does not stop the app from starting (rule 5: degraded but working). |
| D4 | **`torch` is pinned as `2.15.0` with the CPU wheel index as an extra index.** | The `+cpu` build is picked from the PyTorch index where it exists; on Windows the PyPI wheel is CPU-only as well. |
| D5 | **`openhome-client` is not pinned yet.** | The prompt says to read the live OpenHome docs first. It is added (guarded import) in Phase 8 once the package and its API are confirmed. |
| D6 | **`platformio` is listed unpinned in `requirements-dev.txt`.** | It is pinned in Phase 4 after the firmware compiles with a known version. It is not needed to run the app. |
| D7 | **`PORT` was added to `.env.example`** (default 5000). | `verify.py` boots the app on a free port so it never collides with a running instance. |
| D8 | **Two internal overrides: `ASTROVITAL_ENV_FILE` and `ASTROVITAL_INSTANCE_DIR`.** Not in `.env.example`. | Tests and `verify.py` boot against a throwaway folder with no `.env`, which proves the "clean checkout, no keys" gate without touching the real database or uploads. |
| D9 | **Vendored assets are described by `scripts/assets_manifest.json` (URL, destination, SHA-256).** `fetch_assets.py` saves a download only when the checksum matches; hosts are allow-listed. | Reproducible and safe re-fetching with the standard library only. `.gitattributes` stops git from rewriting line endings of vendored files, which would break the checksums. |
| D10 | **Fonts: Geist and Geist Mono as variable fonts (`@fontsource-variable/*` 5.3.0), Instrument Serif italic only (`@fontsource/instrument-serif` 5.3.0), latin subset.** | One 29 KB file covers every Geist weight the design uses (200–500). Instrument Serif is used only as the grey italic second line. Licences (OFL 1.1) are vendored next to the fonts. |
| D11 | **The landing page at `/` is a still placeholder in Phase 0** (headline, one sentence, CSS horizon; no buttons). | Rule 2: nothing visible may be dead. Login does not exist until Phase 1, and the WebGL scene is Phase 9. |
| D12 | **The boot checklist only names a fix script that exists.** | `scripts/device_setup.py` arrives in Phase 4; until then "No wearable seen yet" is shown without a fix. A test enforces this. |
| D13 | **`python-dotenv` reads `KEY=   # comment` as the comment text.** `config.clean_env_value` treats a value starting with `#` as empty. | The `.env.example` in the prompt uses that pattern for every empty key. |
| D14 | **Session cookie `Secure` is off.** | The app is served over plain HTTP on localhost. Marked with a `# SECURITY NOTE`; production needs HTTPS. |
| D15 | **Sentiment and emotion models are stored as `pytorch_model.bin`.** | Neither repository publishes `model.safetensors`. `download_models.py` prefers safetensors when a repository has it. TensorFlow and Flax weights are not downloaded. |

## Phase 1 (and the crew UI mockups)

The owner supplied `ASTROVITAL UI Mockups.pdf` (10 screens) as the visual reference. Where the mockups and PROMPT.md disagree on *look*, the mockups win; where they conflict with a hard rule (no source labels, no sign-up, honesty), PROMPT.md wins.

| # | Decision | Why |
|---|---|---|
| D16 | **Left icon rail instead of the top pill nav.** Labels show on hover/focus and stay open via the menu button; on phones the rail becomes a bottom bar. | The mockups use a rail on every app screen. Icon-only navigation is hard to learn, so every item has a visible label on hover, an accessible name, and an "always show labels" toggle. |
| D17 | **Headline second line in grey Geist, not Instrument Serif italic.** Instrument Serif was removed from the vendored fonts. | Every mockup screen uses a grey sans second line. |
| D18 | **No Bootstrap.** Layout uses CSS Grid and Flexbox. | The owner's stated stack is Flask, Jinja2, HTML, CSS and vanilla JS. Bootstrap's grid would only add weight and specificity fights. |
| D19 | **Per-system scores on Today (Heart, Mind, Bones & muscle) plus Overall**, as in the mockup. Each system score uses the readiness formula and caps on its own subsystems, so Overall is always consistent with the cards. Labels follow one vocabulary everywhere: Heart, Mind, Bones & muscle. | Mockup page 8. The mockup's "Mental / Physical health" labels were unified with the twin, nav and landing words. |
| D20 | **The Dr. NOVA card uses a white pill, not the mockup's blue button.** | Blue means "Okay" in the status system. Colour stays reserved for status. |
| D21 | **A wrong Astro ID re-renders the form with status 200** (not 401). | A 401 adds a console error in the browser; the page already shows the message and the shake. |
| D22 | **`/api/alerts`** (not in Section 18) feeds the red alert bar on pages other than Today. | The bar must appear on every page; building the full summary there is wasteful. |
| D23 | **The host guard lists LAN networks explicitly** (10/8, 172.16/12, 192.168/16, 127/8, 169.254/16, ::1, fc00::/7, fe80::/10). | Python's `ipaddress.is_private` also returns True for documentation ranges such as 203.0.113.0/24, which must count as public. |
| D24 | **Three.js is vendored as one esbuild bundle** (`static/vendor/three/three.bundle.min.js`, three 0.186.1 + GLTFLoader, MeshoptDecoder, RoomEnvironment, SkeletonUtils), built by `scripts/vendor_build/build.mjs`. | three 0.186 ships no minified build; the unminified core alone is 1.4 MB. Built output is committed; Node is build-time only. |
| D25 | **Library versions are pinned to releases at least two weeks old**: three 0.186.1, GSAP 3.15.0, Chart.js 4.6.1, chartjs-plugin-annotation 3.1.0, lucide-static 1.62.0, @mediapipe/tasks-vision 1.1.1. | Fresh releases are more likely to be pulled or broken. |
| D26 | **MediaPipe ships only the SIMD WebAssembly build.** | Every current desktop browser supports WASM SIMD; the non-SIMD build would add 12.6 MB. Without SIMD the Body page falls back to the manual device log. |
| D27 | **Icons are a 84-symbol Lucide sprite** built from `lucide-static` into `static/vendor/lucide/sprite.svg`. | One cached 27 KB file instead of the 1 MB full sprite. |
| D28 | **Daily tasks are ticked by the module that finishes them**, not inside `measurements.record()`. | Keeps the write path pure; XP is awarded once per task per day by `gamification.complete_task`. |
| D29 | **The demo blood-pressure emergency is the evening reading 18 days ago** and settles by the next morning. | The end-of-day readiness then shows the dip in History, matching the mockup's "Oct 21 · blood pressure spike". |

## Phase 2

| # | Decision | Why |
|---|---|---|
| D30 | **Humanoid: three.js r186 `Xbot.glb`** (Mixamo rig, idle clip kept, meshopt-compressed to 845 KB as `static/models/astronaut.glb`). | The model the brief suggests; Mixamo characters are free to use. Bones found by regex: `mixamorigHead`, `mixamorigSpine2`, `mixamorigLeftLeg`, `mixamorigHips` (exposed as `twin.bones`). |
| D31 | **The 2D SVG body paints first and is swapped for WebGL once the model loads.** | No empty stage while the glb downloads, and the same component is the no-WebGL fallback. |
| D32 | **Body FPS was not measured during the build.** | The in-app browser pane was hidden, which pauses `requestAnimationFrame`. Recorded as a known limitation; measure with the pane visible (`twin.fps`). |
| D33 | **The NASA ISS source is Draco-compressed.** It is decoded at build time (`draco3dgltf`, build-only) and re-encoded with meshopt, so the runtime needs only `MeshoptDecoder`. Result: 11.0 MB, 697,619 vertices, 109 WebP textures (≤ 1024 px); 309 detail meshes (`Details`, `Handrails`, …) removed. | Spec budget ≤ 15 MB and ≈ 780k vertices, no Draco at runtime. |
| D34 | **`sharp` is pinned to one version (0.34.4) in the build tools**, with a `postinstall` step that removes the copy nested under `ndarray-pixels`. | Two libvips builds in one Node process corrupt each other ("colourspace: parameter space not set"). |
| D35 | **Earth textures come from three.js r186 examples** (NASA-derived): day and night 4096, clouds from the blue channel of `earth_bump_roughness_clouds_4096`, specular 2048. Shipped as WebP in 2K and 4K tiers plus a generated star field. | Same imagery family as Blue Marble / Black Marble with a stable, pinned source. |

## Phases 3–6

| # | Decision | Why |
|---|---|---|
| D36 | **Wrong *types* in a device batch → 400 with a field path; well-typed but implausible values (NaN, out of range) → that frame is counted as `rejected`.** | Reconciles 10A.4/10A.5 ("wrong types → 400", "a bad frame does not fail the others") with Appendix F's `400 … path: frames[3].hr`. |
| D37 | **The flatline signature includes `ir_dc` and `pi`, not only hr/spo2/ppg.** | With `SEND_PPG=0` a smoothed integer heart rate easily stays identical for 15 s on a healthy signal; the raw IR level of a live optical sensor never repeats exactly, a stuck one does. |
| D38 | **Stream events are queued on the SQLAlchemy session and published after commit** (one process-wide hook; each event carries its hub). | A browser refetching `/api/summary` on a `summary` event must see the committed row. Rollbacks drop the events. |
| D39 | **`LiveMonitor`, a daemon thread started by `run.py`**, detects devices going offline, drives the demo wearable and runs the hourly purge. | "No scheduler dependency"; tests call `live_monitor.tick()` directly. |
| D40 | **Demo wearable = virtual device `AV-DEMO-01`** bound to the same astronaut as the real wearable, fed through the same `DeviceGateway`; its rows are `source = simulated`. Real-device frames in demo mode get `{"ignored": true}`. | Section 10A.11; real and generated readings never mix. |
| D41 | **Synthetic frames (`app/services/sensors/synthetic.py`) are shared** by the demo wearable, `scripts/device_emulator.py`, the tests and the committed fixtures in `tests/fixtures/device_frames/`. | One definition of a firmware-shaped frame. A test also checks that the firmware's JSON keys equal the fixture's keys. |
| D42 | **Background wearable aggregates stay `context = unspecified`;** the heart check stores its own resting averages at the end of the session. | Avoids double resting rows; Section 10A.1 keeps background heart rate out of statuses, readiness and baselines. |
| D43 | **Session heart rate uses a dedicated gate origin (`wearable_session`)**: CRITICAL only if a qualifying 10-frame run happened during the rest-verified session. | Section 9.7 last paragraph. |
| D44 | **Firmware pins:** espressif32 6.12.0 (Arduino core 2.x), SparkFun MAX3010x 1.1.2, OneWire 2.3.8, DallasTemperature 4.0.5, ArduinoJson 7.4.3. The spec's `quality.{h,cpp}` is named `signal_quality.{h,cpp}`. Compiles: RAM 16.1 %, flash 76.4 %. Native logic tests (6) pass with MSYS2 gcc. | Versions verified by compiling. Hardware: needs hardware. |
| D45 | **The heart-check reading API uses `via: "strap" | "hand"`** instead of a `source` field. | Section 0 rule 3 forbids a `source` key in browser code. |
| D46 | **Extra routes: `POST /cardio/measure` (end of rest) and `POST /cardio/pause`.** | Section 10 needs a rest phase and Pause/Resume; Section 18 lists only start/stream/reading/end. |
| D47 | **Bluetooth strap heart rate is treated like a hand entry** for alerts (immediate), since 9.7's fast path names only SpO₂ and glucose. | The strap reading is the astronaut's own deliberate measurement. |
| D48 | **Pose counters use an EMA on the joint angle and need ≥ 0.6 s per rep;** pull-ups count only after returning to straight arms (> 150°). The optional ViTPose route answers 409 in fast mode and 503 until the model is downloaded. | Section 11. Live camera counting could not be tested here (no camera); synthetic keypoint tests cover the state machines. |
| D49 | **The loading index is forced to "Needs attention" after 3 days without exercise** (`force_caution_after_days_without_exercise`). | thresholds.yaml; drives the "Lunar base: no exercise for 4 days" scenario. |

## Phases 7–8

| # | Decision | Why |
|---|---|---|
| D50 | **Whisper reads our own 16 kHz mono WAV chunks directly (numpy), not through PyAV.** | faster-whisper 1.2.1 calls `av.open(metadata_errors=…)`, which PyAV 19 removed. Decoding our known format avoids the dependency; other formats still go through PyAV. |
| D51 | **Wellbeing weights, prompts, theme words and suggestions live in `config/mental.yaml`;** the crisis lexicon in `config/safety_lexicon.yaml` (23-phrase fixture, recall 100 %). | Section 12: "weights live in config"; the safety screen is a hard rule, not a model. |
| D52 | **A safety hit records wellbeing as "Get help now" through the symptom override, with one critical notification** (the write path's own notification is skipped for this row). | The only way wellbeing becomes CRITICAL (Section 12); avoids a duplicate alert. |
| D53 | **OpenHome protocol taken from the official `openhome-client` 0.1.1 source**: voice stream URL with key and agent id, single `Origin: https://app.openhome.com`, browser User-Agent, `transcribed` frames for text input, `audio-init`/`audio-end` lifecycle, `ack`, `ping`, `interrupt-event`. There is no separate REST text endpoint: text chat opens the stream in text-only mode, waits for the greeting and sends one `transcribed` turn. | Section 13 asks to adapt to the live docs. |
| D54 | **Ability rules from `openhome-dev/abilities/validate_ability.py`** (no print/open/assert/eval/asyncio.sleep, register tag, `resume_normal_flow`) are re-implemented in `scripts/build_openhome_ability.py`; the downloaded validator is not executed. | Running a downloaded script is not allowed in this build environment. |
| D55 | **The Ability reads optional overrides from OpenHome Settings → API Keys** (`astrovital_url`, `astrovital_bridge_token`) before the rendered constants. | OpenHome's documented way to keep secrets out of ability code; rendering still works without it. |
| D56 | **Practice mode (`OPENHOME_MOCK=true`) answers with the offline rules engine**, transcribing microphone audio locally with Whisper after a pause. Captions only; the browser reads them aloud. The engine chip says OFFLINE RULES. | Offline-first demo; honest about which engine answered. |
| D57 | **"New consultation" hides earlier messages instead of deleting them.** | Section 13.2.7 stores chat history; deletion would lose it. |
| D58 | **Voice works for one astronaut at a time** (the bridge serves the single session with a heartbeat in the last 45 s; two → 409). | Fail-closed session binding (Section 13.2.4). |

## Phases 9–10

| # | Decision | Why |
|---|---|---|
| D59 | **"Delete my mental-health data" also deletes every Dr. NOVA chat message**, plus check-ins, wellbeing readings and the wellbeing, safety and low-mood notifications; readiness is recomputed for every affected day. | Section 16 says "related ChatMessage rows". A conversation about sleep or stress is mental-health content and cannot be split reliably, so the privacy-safe reading is all of it. Heart, exercise and sleep data stay. |
| D60 | **Display units are converted on output; typed temperature and blood sugar are converted back on input.** Storage stays °C and mg/dL. The preference is read once per request (`app/services/units.py`). Outside a logged-in request (OpenHome context, scripts) the stored units are used. | Section 16: "data is always stored in °C and mg/dL". |
| D61 | **Demo-panel readings use an internal `scenario` origin, and the generated-data recorder holds its own writes for 30 minutes after one.** | Without the hold, the next 5-minute generated slot would replace a forced "Get help now" blood pressure before a judge sees it. |
| D62 | **The mission-day jump is stored on `Mission.day_override`** (new migration `c4e1f2a9b310`); it wins over `MISSION_DAY_OVERRIDE` and the calendar until reset. | The Demo panel must change the day at runtime; the `.env` value is read only at start. |
| D63 | **Wearable panel shows only the configured physical wearable, never the virtual `AV-DEMO-01`.** The wearer switch moves both, so demo data follows the wearer. The calibration offset is computed from the live settled reading (`reference − raw`, limit ±2 °C). | Section 16: "the panel shows real device state only"; 10A.6 calibration. |
| D64 | **Mission Control shows readiness and per-system status as colours with a word label, never the score**, flags "Follow-up requested" for a safety-screen event in the last 7 days, and the crew page lists physiological metrics only (no wellbeing, sleep or check-ins). Every page view writes an `AuditLog` row. | Section 16. |
| D65 | **The bell polls `/api/notifications/poll` every 30 s; the first poll of a browser session only sets the count, later polls toast up to two new items.** | Avoids a burst of old toasts on every login while still surfacing new reminders and alerts. |
| D66 | **The hero poster is a scene-only capture** (`?poster=1` hides the copy) made with headless Edge + SwiftShader at 1600×900 and saved as WebP (42 KB). The intro animation has a 3 s fallback that completes it if GSAP's ticker is paused. | A browser without WebGL still sees Earth and the ISS; a background tab never leaves the hero buttons invisible. |
| D67 | **`text_call` waits up to 1.5 s for `audio-end` after the final reply before closing.** | Closing on the reply cut the agent off mid-utterance and made the protocol acknowledgements racy. |
