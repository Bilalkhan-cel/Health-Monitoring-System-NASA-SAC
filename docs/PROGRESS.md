# PROGRESS

Current: P2 · loop 0/3 · step: PLAN

| Phase | Status | Loops | Gate |
|---|---|---|---|
| P0 Bootstrap & harness | done (2026-11-14) | 1 | green: 23 passed, 0 failed |
| P1 Core domain + Today | done (2026-11-14) | 1 | green: 24 passed, 0 failed |
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
OpenHome status: **needs keys** (no API key or agent id in `.env`).

## Phase 0 checkpoint (2026-11-14)

- **Built:** validated config with boot checklist, app factory (`/` placeholder, `/healthz`, error pages),
  `run.py`, theme tokens with self-hosted fonts, `setup.py`, `fetch_assets.py`, `download_models.py`,
  `verify.py`, 54 tests, the docs.
- **How to test:** `python scripts/setup.py`, then `python run.py`, then open http://localhost:5000.
  Gate: `python scripts/verify.py --phase 0`.
- **Verify results:** see "Last verify result" below. Also checked by hand:
  - Fresh clone into an empty folder → `python scripts/setup.py --skip-ml` → exit 0 → `python run.py`
    → `/healthz` answered 200 → `verify --phase 0` green there (22 passed, ML packages informational).
  - Full `python scripts/setup.py` on the build machine: packages installed, `.env` created with three
    generated secrets, fonts present, all three models downloaded (937 MB) and loaded with
    `local_files_only=True`.
  - Browser: landing page at desktop and 375 px width, 404 page. Fonts loaded (Geist, Geist Mono,
    Instrument Serif), no console errors, no horizontal scroll.
- **Optimize loop, what improved:**
  - `run.py` started with a system Python that already had Flask skipped the project environment and
    would have used unpinned packages. Now any script started outside a virtual environment re-runs
    inside `.venv` when it exists.
  - The boot title used a `·` that turned into a broken character when output was piped on Windows.
    Now plain ASCII; the checklist marks already fall back to `[ok]` / `[--]` / `[!!]`.
- **Next phase:** P1 (models, auth, host guard, thresholds, readiness, `measurements.record()`, seed,
  `/api/summary`, the Today page without 3D).

## Current phase plan

P1 not planned yet. Start with the PLAN step: read the P1 row of Section 21, Section 21A "P1", and
Sections 3, 5, 7, 8, 9.1–9.4a, 9.6, 9.7, 17.

## Design notes

Phase 0 interfaces (stable, later phases extend them):

- `config.load_config(values=None) -> Config` (frozen dataclass). Never raises on optional values:
  problems become `Config.warnings`. `build_checklist(config, ...) -> list[CheckLine(state, text, fix)]`,
  `render_checklist(lines, unicode=bool) -> list[str]`.
- `app.create_app(config=None, testing=False) -> Flask`; `app.get_config(app) -> Config`.
- `app.bootstrap.run(app) -> BootReport(db_ready, crew_loaded, wearable_last_seen_s, sensor_mode, uploads_swept)`.
  P1 fills `crew_loaded`; P3 fills `wearable_last_seen_s` and `sensor_mode`.
- `GET /healthz` → `{"ok": true, "server": "astrovital", "version": "...", "server_time": "...Z"}`.
- Errors: HTML page for browsers, `{"ok": false, "error": "..."}` for `/api/*`.
- `scripts/verify.py`: `Check(name, status, detail)`, statuses PASS / FAIL / SKIP / INFO; `PHASES[n]` holds
  the gate for phase n; a phase with no gate fails. Add new routes to `PUBLIC_ROUTES` (and, from P1, a
  per-crew-member route list) so the smoke test covers them.

## Last verify result

`python scripts/verify.py --phase 0` on 2026-11-14, Python 3.13.5: **GREEN: 23 passed, 0 failed,
0 skipped, 0 informational**. Full table: `docs/verify_last.md`.

| Check | Result |
|---|---|
| pytest | 54 passed |
| App boots (clean database, no keys) | `/healthz` answered after 2.3 s |
| First byte under 500 ms | `/` 26 ms, `/healthz` 16 ms (worst of 5) |
| Boot log | no traceback, no unexpected warning |
| Forbidden patterns, label scans, secrets scan | clean |
| Vendored assets | 6 files, checksums match |
| JS + CSS budgets | no JS yet; landing CSS 8 KB |
| Hardware facts register | 23 rows, none marked verified |

## Known limitations

- Built and tested only on Windows 10 with Python 3.13.5. Python 3.10–3.12, macOS and Linux are untested.
- The landing page is a still placeholder; the 3D scene is Phase 9. No JavaScript ships yet, so
  `node --check` and the JS size budget have nothing to measure.
- The host guard (Section 3) is Phase 1. Until then only `/`, `/healthz` and static files exist, but with
  `DEVICE_ENABLED=true` the app listens on `0.0.0.0`; use `python run.py --host 127.0.0.1` to stay local.
- The firmware has not been written or compiled (Phase 4). Hardware: needs hardware.
- OpenHome: needs keys. Nothing OpenHome-related is built yet (Phase 8).

## Next action

Begin Phase 1 with the PLAN step and write the P1 plan into "Current phase plan" above.
