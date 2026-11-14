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
