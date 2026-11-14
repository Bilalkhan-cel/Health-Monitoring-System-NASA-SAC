# PROGRESS

Current: P0 · loop 1/3 · step: MONITOR

| Phase | Status | Loops | Gate |
|---|---|---|---|
| P0 Bootstrap & harness | in progress | 1 | pending |
| P1 Core domain + Today | not started | | |
| P2 Digital twin | not started | | |
| P3 Live data backbone | not started | | |
| P4 Wearable firmware | not started | | |
| P5 Cardio | not started | | |
| P6 Bone & Muscle | not started | | |
| P7 Mental | not started | | |
| P8 Dr. NOVA | not started | | |
| P9 Landing + login | not started | | |
| P10 Product completeness | not started | | |
| P11 Hardening, hardware bring-up & release | not started | | |

Hardware status: **needs hardware** (nothing tested on the physical ESP32; see `docs/HARDWARE_FACTS.md`).

## Current phase plan

**P0: bootstrap and harness.**

- Files: `config.py`, `run.py`, `app/{__init__,extensions,bootstrap}.py`, `app/landing/routes.py`,
  `app/templates/{base,landing,error}.html`, `app/static/css/{theme,landing}.css`, vendored fonts,
  `scripts/{setup,verify,fetch_assets,download_models,_bootstrap_env}.py`, `scripts/assets_manifest.json`,
  `requirements*.txt`, `.env.example`, `.gitignore`, `.gitattributes`, `docs/*`, `tests/*`.
- Acceptance: on a clean checkout with no keys and no hardware, `python scripts/setup.py` then
  `python run.py` boots; `/healthz` is 200; `python scripts/verify.py --phase 0` is green.
- Top risks: (1) Python 3.13 is newer than the recommended range; (2) a large download failing must not
  block the app; (3) Windows console encoding breaking the boot checklist.
- Smallest slice: `load_config()` → `create_app()` → `/healthz` 200 from a real `run.py` process.

## Design notes

- `config.load_config(values=None) -> Config` (frozen dataclass). Never raises on optional values:
  problems become `Config.warnings`. `build_checklist(config, ...) -> list[CheckLine(state, text, fix)]`,
  `render_checklist(lines, unicode=bool) -> list[str]`.
- `app.create_app(config=None, testing=False) -> Flask`; `app.get_config(app) -> Config`.
- `app.bootstrap.run(app) -> BootReport(db_ready, crew_loaded, wearable_last_seen_s, sensor_mode, uploads_swept)`.
- `GET /healthz` → `{"ok": true, "server": "astrovital", "version": "...", "server_time": "...Z"}`.
- Errors: HTML page for browsers, `{"ok": false, "error": "..."}` for `/api/*`.
- `scripts/verify.py`: `Check(name, status, detail)`, statuses PASS / FAIL / SKIP / INFO; `PHASES[n]` holds
  the gate for phase n; a phase with no gate fails.
- UI states in P0: landing placeholder (static), error page (404 / 405 / 429 / 500).

## Last verify result

Pending.

## Known limitations

None recorded yet.

## Next action

Run `python scripts/verify.py --phase 0`, fix what fails, then checkpoint.
