# Last verify result

- Mode: `--phase 3`
- When: 2026-11-14 13:46 UTC
- Python: 3.13.5 · commit `cc01454`
- Result: **RED: 29 passed, 1 failed, 0 skipped, 0 informational**

| # | Check | Result | Detail |
|---|---|---|---|
| 1 | Python version | PASS | 3.13.5 |
| 2 | Core packages | PASS | all importable |
| 3 | ML packages | PASS | all importable |
| 4 | Project layout | PASS | 36 required files present |
| 5 | .env.example keys | PASS | 61 keys present |
| 6 | Requirements pinned | PASS | every package uses == |
| 7 | Secrets git-ignored | PASS | .env, firmware/include/secrets.h and local data |
| 8 | Vendored assets match the manifest | PASS | 16 files, checksums match |
| 9 | Hardware facts register | PASS | 23 rows, none marked verified |
| 10 | pytest | PASS | 256 passed in 34.77s |
| 11 | App boots (clean database, no keys) | PASS | /healthz answered after 2.3 s |
| 12 | First byte under 500 ms | PASS | worst of 5: / 24 ms, /healthz 16 ms, /login 26 ms |
| 13 | Boot log clean | PASS | no traceback, no unexpected warning |
| 14 | Boot checklist printed | PASS | database and listening lines present |
| 15 | Database file created | PASS | created in the instance folder |
| 16 | Route smoke test (anonymous + every crew member) | PASS | 14 GET routes x 5 users, no 5xx, protected routes protected |
| 17 | Label scan: rendered pages and JSON | PASS | no source label or source key (30 JSON responses) |
| 18 | Forbidden patterns | PASS | no CDN URL, /safe, console.log, print( or secret |
| 19 | Secrets stay in .env | PASS | 3 secret value(s) checked against the source tree |
| 20 | Label scan: templates, scripts, styles | FAIL | app/static/js/app/cardio.js: a 'source' key |
| 21 | JS module size (400 KB each) | PASS | 14 module(s), largest 15 KB |
| 22 | Landing JS + CSS (1.5 MB) | PASS | 32 KB |
| 23 | node --check | PASS | 14 module(s) parse |
| 24 | /api/summary p95 under 300 ms | PASS | p95 13 ms over 40 requests (30 days of history) |
| 25 | Digital twin assets | PASS | astronaut.glb 845 KB, 3D twin + SVG fallback present |
| 26 | Emulator profiles (10A.11) | PASS | 15 profiles |
| 27 | Ingest p95 under 50 ms | PASS | p95 32.9 ms over 60 batches (real HTTP) |
| 28 | Device-to-browser under 1.5 s | PASS | worst 33 ms, median 31 ms |
| 29 | Live server log clean | PASS | no traceback, no unexpected warning |
| 30 | /api/summary p95 with 7 days of raw frames | PASS | p95 16 ms (604,800 raw frames + 30 days of history) |
