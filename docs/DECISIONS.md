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
