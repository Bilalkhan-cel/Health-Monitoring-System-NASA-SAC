# AstroVital

**Beyond Earth. Always in Health.**

Astronaut health monitoring, self-assessment and an AI flight doctor (Dr. NOVA, powered by OpenHome).
A prototype for educational purposes, inspired by the NASA Human Research Program.
**Not a certified medical device.**

> Build status: **Phase 0 of 11** (bootstrap and test harness). The app starts and serves a placeholder
> landing page; crew login and the health modules arrive in the next phases. Progress is tracked in
> [docs/PROGRESS.md](docs/PROGRESS.md), and the full specification is [PROMPT.md](PROMPT.md).

## Run it

You need Python 3.10–3.13 (built and tested on 3.13) and an internet connection for the first setup.

```bash
python scripts/setup.py
```

```bash
python run.py
```

Then open http://localhost:5000.

`scripts/setup.py` is safe to run again at any time. It:

1. creates a virtual environment in `.venv` (your system Python is left alone);
2. installs the pinned packages;
3. creates `.env` from `.env.example` and generates the secrets;
4. fetches the fonts and the local ML models (about 1 GB, stored in `ml_models/`);
5. runs a quick self-check.

If a download fails, setup says so and carries on: the app still starts and uses its fallbacks.
Options: `--skip-models`, `--skip-ml`, `--no-venv`.

No API key is needed to start. `run.py` prints a checklist that shows what is ready and how to fix
anything that is missing.

## Other commands

| Command | What it does |
|---|---|
| `python scripts/verify.py --quick` | Setup sanity check |
| `python scripts/verify.py --phase 0` | Full gate for the phases built so far; writes `docs/verify_last.md` |
| `python scripts/fetch_assets.py` | Re-fetch missing fonts (checksum-verified) |
| `python scripts/download_models.py` | Re-download and verify the ML models |

## Notes

- Everything runs on this computer. Models load from `ml_models/` with no network access.
- The app runs as a single process (`threaded=True`, no reloader).
- Secrets live only in `.env`, which is git-ignored.
- Hardware status: the ESP32 wearable has not been tested yet. See [docs/HARDWARE_FACTS.md](docs/HARDWARE_FACTS.md).
- Decisions and deviations from the specification: [docs/DECISIONS.md](docs/DECISIONS.md).
