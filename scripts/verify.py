"""The Monitor step of the build loop: phase gates, budgets and smoke tests.

    python scripts/verify.py --quick      setup sanity (used by scripts/setup.py)
    python scripts/verify.py --phase N    cumulative gate for phases 0..N
    python scripts/verify.py --full       every defined phase plus the performance budgets

Exits non-zero when a check fails and writes the result table to
``docs/verify_last.md`` (``--quick`` only prints).
"""

from __future__ import annotations

import argparse
import http.client
import json
import importlib.util
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap_env import ROOT, ensure_environment  # noqa: E402

ensure_environment()
sys.path.insert(0, str(ROOT))

PASS, FAIL, SKIP, INFO = "PASS", "FAIL", "SKIP", "INFO"

APP_DIR = ROOT / "app"
STATIC_DIR = APP_DIR / "static"
TEMPLATE_DIR = APP_DIR / "templates"
VENDOR_DIR = STATIC_DIR / "vendor"

# Budgets (Section 0.1 of PROMPT.md)
JS_MODULE_MAX_BYTES = 400 * 1024
LANDING_JS_CSS_MAX_BYTES = int(1.5 * 1024 * 1024)
FIRST_BYTE_MAX_MS = 500
BOOT_TIMEOUT_S = 40

CORE_PACKAGES = ("flask", "flask_sqlalchemy", "flask_migrate", "flask_wtf", "flask_limiter", "flask_sock",
                 "dotenv", "yaml", "requests", "websocket", "reportlab", "PIL")
ML_PACKAGES = ("torch", "transformers", "faster_whisper", "numpy", "scipy")

PHASE0_FILES = (
    "run.py", "config.py", "requirements.txt", "requirements-core.txt", "requirements-ml.txt",
    "requirements-dev.txt", ".env.example", ".gitignore", "README.md", "PROMPT.md",
    "app/__init__.py", "app/extensions.py", "app/bootstrap.py", "app/landing/routes.py",
    "app/models.py", "app/security.py", "app/auth/routes.py", "app/dashboard/routes.py",
    "app/services/thresholds.py", "app/services/readiness.py", "app/services/alert_gate.py",
    "app/services/measurements.py", "config/thresholds.yaml", "config/environments.yaml",
    "migrations/env.py",
    "app/templates/base.html", "app/templates/landing.html", "app/static/css/theme.css",
    "scripts/setup.py", "scripts/verify.py", "scripts/fetch_assets.py", "scripts/download_models.py",
    "scripts/assets_manifest.json",
    "docs/PROGRESS.md", "docs/DECISIONS.md", "docs/HARDWARE_FACTS.md",
)

ENV_KEYS = (
    "FLASK_SECRET_KEY", "FLASK_DEBUG", "DATABASE_URL", "PUBLIC_BASE_URL", "TRUSTED_HOSTS", "BIND_HOST",
    "REGISTERED_ASTRONAUTS", "FLIGHT_SURGEON_IDS", "MISSION_NAME", "MISSION_START_DATE", "MISSION_DAY_OVERRIDE",
    "DEFAULT_ENVIRONMENT", "OPENHOME_API_KEY", "OPENHOME_AGENT_ID", "OPENHOME_VOICE_WS", "OPENHOME_BRIDGE_TOKEN",
    "OPENHOME_ENABLED", "OPENHOME_MOCK", "FALLBACK_LLM_API_KEY", "FALLBACK_LLM_BASE_URL", "FALLBACK_LLM_MODEL",
    "WHISPER_MODEL_SIZE", "WHISPER_MODEL_PATH", "WHISPER_COMPUTE_TYPE", "NLP_SENTIMENT_PATH", "NLP_EMOTION_PATH",
    "POSE_BACKEND", "POSE_MODEL_PATH", "MENTAL_SESSION_TARGET_MIN", "MENTAL_SESSION_MIN_SECONDS",
    "MENTAL_SESSION_MAX_MIN", "CARDIO_SESSION_SECONDS", "STORE_TRANSCRIPTS", "DEVICE_ENABLED", "DEVICE_TOKEN",
    "DEVICE_ID", "DEVICE_WEARER_ID", "DEVICE_AUTO_REGISTER", "DEVICE_HOSTS", "DEVICE_LAN_IP", "DEVICE_RATE_LIMIT",
    "SENSOR_MODE", "ZEROCONF_ENABLED", "LIVE_STALE_S", "DEVICE_OFFLINE_S", "BACKLOG_LIVE_MAX_S", "FINGER_SETTLE_S",
    "MIN_SIGNAL_QUALITY", "AGG_WINDOW_S", "AGG_MIN_VALID", "RAW_RETENTION_DAYS", "TEMP_SITE", "TEMP_OFFSET_C",
    "TEMP_CONTACT_MIN_C", "TEMP_SETTLE_MIN_RAW_C", "TEMP_SETTLE_SLOPE_C_PER_MIN", "SIM_RECORD_INTERVAL_MIN",
    "MEAL_TIMES", "DEMO_MODE", "SEED_DAYS", "SEED_ON_FIRST_RUN",
)

# Routes timed for the first-byte budget.
PUBLIC_ROUTES = (("/", 200), ("/healthz", 200), ("/login", 200))


@dataclass(frozen=True)
class Check:
    """Outcome of one verification step."""

    name: str
    status: str
    detail: str = ""


# ── text scanners (pure functions, unit-tested) ───────────

_REMOTE_URL = re.compile(r"""(?:https?:)?//[A-Za-z0-9.-]+\.[A-Za-z]{2,}[^\s"'<>)]*""")
_ALLOWED_URL_PREFIXES = ("http://www.w3.org/",)
_SAFE_FILTER = re.compile(r"\|\s*safe\b")
_CONSOLE_LOG = re.compile(r"\bconsole\.(log|debug)\s*\(")
_PRINT_CALL = re.compile(r"(?<![\w.])print\s*\(")
_SECRET_SHAPES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
)
_SOURCE_TAGS = re.compile(r"\b(SENSOR|DERIVED|SIMULATED|SIM)\b")
_SOURCE_WORDS = re.compile(r"\b(simulated|demo data)\b", re.IGNORECASE)
_SOURCE_KEY_JS = re.compile(r"""(?:\.source\b|["']source["']\s*:|\bsource\s*:)""")
# Only these may mention generated data in words (Settings → About and the Demo panel).
LABEL_EXEMPT_FILES = ("settings.html", "settings_about.html", "settings_demo.html")


def scan_forbidden(text: str, kind: str) -> list[str]:
    """Return forbidden patterns found in one file. ``kind`` is html | css | js | py."""
    problems: list[str] = []
    if kind in ("html", "css", "js"):
        for match in _REMOTE_URL.finditer(text):
            if not match.group(0).startswith(_ALLOWED_URL_PREFIXES):
                problems.append(f"remote URL {match.group(0)[:60]}")
    if kind == "html" and _SAFE_FILTER.search(text):
        problems.append("|safe filter")
    if kind == "js" and _CONSOLE_LOG.search(text):
        problems.append("console.log left in")
    if kind == "py" and _PRINT_CALL.search(text):
        problems.append("print( in app code")
    for shape in _SECRET_SHAPES:
        if shape.search(text):
            problems.append("something shaped like a secret")
    return problems


def scan_source_labels(text: str, *, exempt_words: bool = False, is_js: bool = False) -> list[str]:
    """Return source labels found in browser-facing text (Section 0 rule 3)."""
    problems = [f"source tag '{match.group(1)}'" for match in _SOURCE_TAGS.finditer(text)]
    if not exempt_words:
        problems += [f"word '{match.group(1).lower()}'" for match in _SOURCE_WORDS.finditer(text)]
    if is_js and _SOURCE_KEY_JS.search(text):
        problems.append("a 'source' key")
    return problems


def find_source_keys(payload: object, path: str = "$") -> list[str]:
    """Return the JSON paths of every ``source`` key in a decoded payload."""
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "source":
                found.append(f"{path}.source")
            found += find_source_keys(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            found += find_source_keys(value, f"{path}[{index}]")
    return found


_LOG_LINE = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+ (WARNING|ERROR|CRITICAL) (\S+) (.*)$")


def scan_log(text: str, allowed: Iterable[str] = ()) -> list[str]:
    """Return tracebacks and unexpected WARNING/ERROR lines from captured output."""
    problems: list[str] = []
    allowed = tuple(allowed)
    for line in text.splitlines():
        if "Traceback (most recent call last)" in line:
            problems.append("traceback")
            continue
        match = _LOG_LINE.match(line)
        if match and not any(fragment in line for fragment in allowed):
            problems.append(f"{match.group(1)} {match.group(2)}: {match.group(3)[:80]}")
    return problems


def unpinned_requirements(text: str) -> list[str]:
    """Return requirement lines that are not pinned with ``==``."""
    loose = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line and not line.startswith("-") and "==" not in line:
            loose.append(line)
    return loose


# ── helpers ───────────────────────────────────────────────

def _app_files(suffixes: tuple[str, ...]) -> list[Path]:
    files = []
    for path in APP_DIR.rglob("*"):
        if path.is_file() and path.suffix in suffixes and VENDOR_DIR not in path.parents \
                and "__pycache__" not in path.parts:
            files.append(path)
    return sorted(files)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _throwaway_env(instance_dir: Path, port: int | None = None) -> dict[str, str]:
    """Environment for a clean boot: no .env, no keys, empty database, loopback only."""
    env = dict(os.environ)
    env.update({
        "ASTROVITAL_ENV_FILE": str(instance_dir / "no-such.env"),
        "ASTROVITAL_INSTANCE_DIR": str(instance_dir),
        "BIND_HOST": "127.0.0.1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
    })
    for key in ENV_KEYS:
        if key not in ("BIND_HOST",):
            env.pop(key, None)
    if port is not None:
        env["PORT"] = str(port)
    return env


def _make_test_client(instance_dir: Path):
    from app import create_app
    from config import load_config

    values = {"ASTROVITAL_INSTANCE_DIR": str(instance_dir), "FLASK_SECRET_KEY": "verify-only", "BIND_HOST": "127.0.0.1"}
    app = create_app(load_config(values), testing=True)
    return app.test_client()


def _first_byte_ms(port: int, path: str) -> float:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        started = time.perf_counter()
        connection.request("GET", path)
        response = connection.getresponse()
        response.read(1)
        elapsed = (time.perf_counter() - started) * 1000
        response.read()
        return elapsed
    finally:
        connection.close()


# ── quick checks ──────────────────────────────────────────

def check_python() -> Check:
    version = sys.version_info
    label = f"{version.major}.{version.minor}.{version.micro}"
    if (3, 10) <= version[:2] <= (3, 13):
        return Check("Python version", PASS, label)
    return Check("Python version", FAIL, f"{label} is outside 3.10 to 3.13")


def check_packages() -> list[Check]:
    def missing(names: Iterable[str]) -> list[str]:
        return [name for name in names if importlib.util.find_spec(name) is None]

    core, ml = missing(CORE_PACKAGES), missing(ML_PACKAGES)
    return [
        Check("Core packages", FAIL if core else PASS, "missing: " + ", ".join(core) if core else "all importable"),
        Check("ML packages", INFO if ml else PASS,
              "missing (fallbacks in use): " + ", ".join(ml) if ml else "all importable"),
    ]


def check_env_file() -> Check:
    from config import clean_env_value, read_env

    env_path = ROOT / ".env"
    if not env_path.exists():
        return Check(".env", FAIL, "missing: run python scripts/setup.py")
    values = read_env(env_path, overrides={})
    empty = [key for key in ("FLASK_SECRET_KEY", "DEVICE_TOKEN") if not clean_env_value(values.get(key))]
    if empty:
        return Check(".env", FAIL, "empty: " + ", ".join(empty) + " (run python scripts/setup.py)")
    return Check(".env", PASS, "present, secrets generated")


def check_config() -> list[Check]:
    from config import fonts_present, hf_model_found, load_config, whisper_model_found, FONT_FILES

    try:
        config = load_config()
    except Exception as error:  # noqa: BLE001 (config must never raise; report if it does)
        return [Check("Config loads", FAIL, f"{type(error).__name__}: {error}")]
    checks = [Check("Config loads", PASS, f"{len(config.astronauts)} astronauts, {len(config.surgeons)} flight surgeon")]
    if config.warnings:
        checks.append(Check("Config warnings", INFO, "; ".join(config.warnings)))
    fonts = fonts_present(config)
    checks.append(Check("Fonts", PASS if len(fonts) == len(FONT_FILES) else INFO,
                        f"{len(fonts)}/{len(FONT_FILES)} present" +
                        ("" if len(fonts) == len(FONT_FILES) else " (system fonts in use)")))
    models = {
        "whisper": whisper_model_found(config),
        "sentiment": hf_model_found(config.nlp_sentiment_path),
        "emotion": hf_model_found(config.nlp_emotion_path),
    }
    absent = [name for name, found in models.items() if not found]
    checks.append(Check("ML models", INFO if absent else PASS,
                        "missing (fallbacks in use): " + ", ".join(absent) if absent else "all present"))
    return checks


def check_app_healthz() -> Check:
    with tempfile.TemporaryDirectory(prefix="astrovital-verify-", ignore_cleanup_errors=True) as temp:
        try:
            response = _make_test_client(Path(temp)).get("/healthz")
        except Exception as error:  # noqa: BLE001
            return Check("App starts", FAIL, f"{type(error).__name__}: {error}")
    ok = response.status_code == 200 and response.get_json().get("ok") is True
    return Check("App starts", PASS if ok else FAIL, f"/healthz answered {response.status_code}")


def quick_checks() -> list[Check]:
    checks = [check_python(), *check_packages()]
    if any(check.status == FAIL for check in checks):
        return checks
    return [*checks, check_env_file(), *check_config(), check_app_healthz()]


# ── phase 0 checks ────────────────────────────────────────

def check_layout() -> Check:
    missing = [name for name in PHASE0_FILES if not (ROOT / name).exists()]
    return Check("Project layout", FAIL if missing else PASS,
                 "missing: " + ", ".join(missing) if missing else f"{len(PHASE0_FILES)} required files present")


def check_env_example() -> Check:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    present = set(re.findall(r"^([A-Z0-9_]+)=", text, flags=re.MULTILINE))
    missing = [key for key in ENV_KEYS if key not in present]
    return Check(".env.example keys", FAIL if missing else PASS,
                 "missing: " + ", ".join(missing) if missing else f"{len(ENV_KEYS)} keys present")


def check_requirements_pinned() -> Check:
    loose: list[str] = []
    for name in ("requirements-core.txt", "requirements-ml.txt"):
        loose += unpinned_requirements((ROOT / name).read_text(encoding="utf-8"))
    return Check("Requirements pinned", FAIL if loose else PASS,
                 "not pinned: " + ", ".join(loose) if loose else "every package uses ==")


def check_gitignore() -> Check:
    targets = [".env", "firmware/include/secrets.h", "instance/astrovital.db", "ml_models/whisper/base/model.bin"]
    git = shutil.which("git")
    if not git or not (ROOT / ".git").exists():
        return Check("Secrets git-ignored", SKIP, "git not available")
    exposed = [target for target in targets
               if subprocess.call([git, "check-ignore", "-q", target], cwd=ROOT) != 0]
    tracked = subprocess.run([git, "ls-files", ".env"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if tracked:
        exposed.append(".env is tracked by git")
    return Check("Secrets git-ignored", FAIL if exposed else PASS,
                 "not ignored: " + ", ".join(exposed) if exposed else ", ".join(targets[:2]) + " and local data")


def check_pytest() -> Check:
    result = subprocess.run([sys.executable, "-m", "pytest"], cwd=ROOT, capture_output=True, text=True)
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    summary = lines[-1] if lines else "no output"
    if result.returncode == 0:
        return Check("pytest", PASS, summary)
    failures = [line for line in lines if line.startswith(("FAILED", "ERROR"))][:5]
    return Check("pytest", FAIL, "; ".join(failures) or summary)


def check_boot() -> list[Check]:
    """Start ``run.py`` as a real process on a clean database and probe it."""
    checks: list[Check] = []
    temp = Path(tempfile.mkdtemp(prefix="astrovital-boot-"))
    port = _free_port()
    log_path = temp / "boot.log"
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen([sys.executable, str(ROOT / "run.py")], cwd=ROOT,
                                   env=_throwaway_env(temp, port), stdout=log_file, stderr=subprocess.STDOUT)
        try:
            started, booted = time.monotonic(), False
            while time.monotonic() - started < BOOT_TIMEOUT_S and process.poll() is None:
                try:
                    _first_byte_ms(port, "/healthz")
                    booted = True
                    break
                except OSError:
                    time.sleep(0.25)
            boot_seconds = time.monotonic() - started
            if not booted:
                checks.append(Check("App boots (clean database, no keys)", FAIL,
                                    f"no answer on /healthz within {BOOT_TIMEOUT_S} s"))
            else:
                checks.append(Check("App boots (clean database, no keys)", PASS,
                                    f"/healthz answered after {boot_seconds:.1f} s"))
                timings = {path: max(_first_byte_ms(port, path) for _ in range(5)) for path, _ in PUBLIC_ROUTES}
                slow = {path: ms for path, ms in timings.items() if ms > FIRST_BYTE_MAX_MS}
                detail = ", ".join(f"{path} {ms:.0f} ms" for path, ms in timings.items())
                checks.append(Check(f"First byte under {FIRST_BYTE_MAX_MS} ms", FAIL if slow else PASS,
                                    f"worst of 5: {detail}"))
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
    output = log_path.read_text(encoding="utf-8", errors="replace")
    problems = scan_log(output)
    checks.append(Check("Boot log clean", FAIL if problems else PASS,
                        "; ".join(problems[:4]) if problems else "no traceback, no unexpected warning"))
    has_checklist = "Database ready" in output and "Listening on 127.0.0.1" in output
    checks.append(Check("Boot checklist printed", PASS if has_checklist else FAIL,
                        "database and listening lines present" if has_checklist else "checklist lines not found"))
    db_file = temp / "astrovital.db"
    checks.append(Check("Database file created", PASS if db_file.exists() else FAIL,
                        "created in the instance folder" if db_file.exists() else "astrovital.db not found"))
    shutil.rmtree(temp, ignore_errors=True)
    return checks


PUBLIC_ENDPOINTS = {"landing.index", "landing.healthz", "auth.login", "static"}
SAMPLE_ARGS = {"system": "heart", "code": "hydration", "scenario": "mars_transit", "id": 1, "checkin_id": 1,
               "notification_id": 1, "astro_id": "AST-1002"}
TOKEN_ROUTES = ("/api/device/", "/api/openhome/")
STREAM_ENDPOINTS = {"devices.events", "cardio.stream"}  # Server-Sent Events: opened, never read to the end


def _seeded_client(instance: Path):
    from app import bootstrap, create_app
    from app.extensions import db
    from config import load_config

    values = {"ASTROVITAL_INSTANCE_DIR": str(instance), "FLASK_SECRET_KEY": "verify-only",
              "BIND_HOST": "127.0.0.1", "OPENHOME_MOCK": "true", "SEED_ON_FIRST_RUN": "true"}
    example = ROOT / ".env.example"
    from config import read_env

    merged = {**read_env(example, overrides={}), **values}
    app = create_app(load_config(merged), testing=True)
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        db.create_all()
        bootstrap.prepare_data(app, seed=True)
    return app


def _dispose(app) -> None:
    """Release the SQLite file so Windows can delete the temporary folder."""
    from app.extensions import db

    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def _get_routes(app) -> list[tuple[str, str]]:
    """Every GET route as (endpoint, path) with sample values for its arguments."""
    from flask import url_for

    routes = []
    with app.test_request_context():
        for rule in app.url_map.iter_rules():
            if "GET" not in rule.methods or rule.endpoint == "static" or rule.rule.startswith("/ws/"):
                continue
            try:
                path = url_for(rule.endpoint, **{arg: SAMPLE_ARGS.get(arg, 1) for arg in rule.arguments})
            except Exception:  # noqa: BLE001 (a route with an argument we cannot fill)
                continue
            routes.append((rule.endpoint, path))
    return sorted(set(routes))


def check_route_smoke() -> list[Check]:
    """Every GET route, anonymously and as every crew member: no 5xx, protected routes stay protected."""
    with tempfile.TemporaryDirectory(prefix="astrovital-smoke-", ignore_cleanup_errors=True) as temp:
        app = _seeded_client(Path(temp))
        config = app.extensions["astrovital_config"]
        routes = _get_routes(app)
        problems, label_hits, payloads = [], [], 0
        anonymous = app.test_client()
        for endpoint, path in routes:
            response = anonymous.get(path, buffered=endpoint not in STREAM_ENDPOINTS)
            response.close() if endpoint in STREAM_ENDPOINTS else None
            if response.status_code >= 500:
                problems.append(f"anonymous {path} gave {response.status_code}")
            elif endpoint in PUBLIC_ENDPOINTS:
                if response.status_code != 200:
                    problems.append(f"anonymous {path} gave {response.status_code}")
            elif path.startswith(TOKEN_ROUTES):
                if response.status_code not in (401, 403, 404, 405):
                    problems.append(f"anonymous {path} gave {response.status_code} without a token")
            elif response.status_code not in (302, 401):
                problems.append(f"anonymous {path} gave {response.status_code}, expected a login redirect")
        crew_ids = [member.astro_id for member in (*config.astronauts, *config.surgeons)]
        for astro_id in crew_ids:
            client = app.test_client()
            client.post("/login", data={"astro_id": astro_id})
            for endpoint, path in routes:
                if path.startswith(TOKEN_ROUTES):
                    continue
                if endpoint in STREAM_ENDPOINTS:
                    response = client.get(path, buffered=False)
                    if response.status_code >= 500:
                        problems.append(f"{astro_id} {path} gave {response.status_code}")
                    response.close()
                    continue
                response = client.get(path)
                if response.status_code >= 500 or b"Traceback" in response.data:
                    problems.append(f"{astro_id} {path} gave {response.status_code}")
                    continue
                if response.is_json:
                    payloads += 1
                    label_hits += [f"{path} {hit}" for hit in find_source_keys(response.get_json())]
                elif response.mimetype == "text/html":
                    label_hits += [f"{path}: {hit}" for hit in scan_source_labels(response.get_data(as_text=True),
                                                                                   exempt_words="/settings" in path)]
        missing_page = anonymous.get("/no-such-page")
        if missing_page.status_code != 404:
            problems.append(f"/no-such-page gave {missing_page.status_code}")
        _dispose(app)
    return [
        Check("Route smoke test (anonymous + every crew member)", FAIL if problems else PASS,
              "; ".join(problems[:5]) if problems
              else f"{len(routes)} GET routes x {len(crew_ids) + 1} users, no 5xx, protected routes protected"),
        Check("Label scan: rendered pages and JSON", FAIL if label_hits else PASS,
              "; ".join(label_hits[:4]) if label_hits else f"no source label or source key ({payloads} JSON responses)"),
    ]


def check_summary_speed() -> Check:
    """/api/summary p95 with 30 days of seeded history."""
    with tempfile.TemporaryDirectory(prefix="astrovital-perf-", ignore_cleanup_errors=True) as temp:
        client = _seeded_client(Path(temp)).test_client()
        client.post("/login", data={"astro_id": "AST-1001"})
        timings = []
        for _ in range(40):
            started = time.perf_counter()
            client.get("/api/summary")
            timings.append((time.perf_counter() - started) * 1000)
        _dispose(client.application)
    p95 = sorted(timings)[int(len(timings) * 0.95) - 1]
    return Check("/api/summary p95 under 300 ms", PASS if p95 < 300 else FAIL,
                 f"p95 {p95:.0f} ms over 40 requests (30 days of history)")


def check_forbidden_patterns() -> Check:
    kinds = {".html": "html", ".css": "css", ".js": "js", ".py": "py"}
    problems = []
    for path in _app_files(tuple(kinds)):
        for problem in scan_forbidden(path.read_text(encoding="utf-8"), kinds[path.suffix]):
            problems.append(f"{_rel(path)}: {problem}")
    return Check("Forbidden patterns", FAIL if problems else PASS,
                 "; ".join(problems[:5]) if problems else "no CDN URL, |safe, console.log, print( or secret")


def check_secrets_not_in_source() -> Check:
    """No real secret from the local .env may appear in a file that git would track."""
    from config import clean_env_value, read_env

    env_path = ROOT / ".env"
    if not env_path.exists():
        return Check("Secrets stay in .env", SKIP, "no .env on this machine")
    values = read_env(env_path, overrides={})
    secret_names = ("FLASK_SECRET_KEY", "OPENHOME_API_KEY", "OPENHOME_BRIDGE_TOKEN", "FALLBACK_LLM_API_KEY",
                    "DEVICE_TOKEN")
    secrets_found = {name: clean_env_value(values.get(name)) for name in secret_names}
    secrets_found = {name: value for name, value in secrets_found.items() if len(value) >= 12}
    leaks = []
    for folder in ("app", "scripts", "tests", "docs", "config", "openhome_ability", "firmware"):
        base = ROOT / folder
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix in (".woff2", ".glb", ".pyc", ".png", ".jpg", ".webp", ".task"):
                continue
            if path.name == "secrets.h":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            leaks += [f"{name} in {_rel(path)}" for name, value in secrets_found.items() if value in text]
    return Check("Secrets stay in .env", FAIL if leaks else PASS,
                 "; ".join(leaks[:4]) if leaks else f"{len(secrets_found)} secret value(s) checked against the source tree")


def check_label_scan_files() -> Check:
    """Templates, scripts and styles must not carry a source label (Section 0 rule 3)."""
    problems = []
    for path in _app_files((".html", ".js", ".css")):
        exempt = path.name in LABEL_EXEMPT_FILES
        hits = scan_source_labels(path.read_text(encoding="utf-8"), exempt_words=exempt, is_js=path.suffix == ".js")
        problems += [f"{_rel(path)}: {hit}" for hit in hits]
    return Check("Label scan: templates, scripts, styles", FAIL if problems else PASS,
                 "; ".join(problems[:5]) if problems else "no source label")


def check_budgets() -> list[Check]:
    scripts = [path for path in _app_files((".js",))]
    heavy = [f"{_rel(path)} {path.stat().st_size // 1024} KB" for path in scripts
             if path.stat().st_size > JS_MODULE_MAX_BYTES]
    largest = max((path.stat().st_size for path in scripts), default=0)
    landing_files = [STATIC_DIR / "css" / "theme.css", STATIC_DIR / "css" / "landing.css"]
    landing_files += [path for path in scripts if path.name in ("astro3d.js", "landing.js") or "3d" in path.parts]
    landing_bytes = sum(path.stat().st_size for path in landing_files if path.exists())
    return [
        Check("JS module size (400 KB each)", FAIL if heavy else PASS,
              "; ".join(heavy) if heavy else f"{len(scripts)} module(s), largest {largest // 1024} KB"),
        Check("Landing JS + CSS (1.5 MB)", FAIL if landing_bytes > LANDING_JS_CSS_MAX_BYTES else PASS,
              f"{landing_bytes / 1024:.0f} KB"),
    ]


def check_assets() -> Check:
    import fetch_assets

    assets = fetch_assets.load_manifest()
    stale = [asset.dest for asset in assets if not fetch_assets.is_current(asset)]
    return Check("Vendored assets match the manifest", FAIL if stale else PASS,
                 "missing or changed: " + ", ".join(stale) if stale else f"{len(assets)} files, checksums match")


def check_node_syntax() -> Check:
    node = shutil.which("node")
    scripts = _app_files((".js",))
    if not node:
        return Check("node --check", SKIP, "Node.js not installed")
    if not scripts:
        return Check("node --check", PASS, "no JS modules yet")
    broken = []
    for path in scripts:
        result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
        if result.returncode != 0:
            broken.append(_rel(path))
    return Check("node --check", FAIL if broken else PASS,
                 "syntax errors: " + ", ".join(broken) if broken else f"{len(scripts)} module(s) parse")


def check_hardware_facts() -> Check:
    path = ROOT / "docs" / "HARDWARE_FACTS.md"
    if not path.exists():
        return Check("Hardware facts register", FAIL, "docs/HARDWARE_FACTS.md is missing")
    rows = [line for line in path.read_text(encoding="utf-8").splitlines() if re.match(r"^\|\s*\d+\s*\|", line)]
    claimed = [row.split("|")[1].strip() for row in rows if re.search(r"\|\s*\**verified", row, re.IGNORECASE)]
    if len(rows) != 23:
        return Check("Hardware facts register", FAIL, f"expected 23 rows, found {len(rows)}")
    return Check("Hardware facts register", FAIL if claimed else PASS,
                 "rows marked verified without a test: " + ", ".join(claimed) if claimed
                 else "23 rows, none marked verified")


def check_twin_assets() -> Check:
    """Phase 2: the humanoid, the twin modules and the 2D fallback exist."""
    model = STATIC_DIR / "models" / "astronaut.glb"
    needed = [model, STATIC_DIR / "js" / "3d" / "twin.js", STATIC_DIR / "js" / "3d" / "twin2d.js",
              STATIC_DIR / "js" / "astro3d.js", ROOT / "config" / "recommendations.yaml"]
    missing = [_rel(path) for path in needed if not path.exists()]
    if missing:
        return Check("Digital twin assets", FAIL, "missing: " + ", ".join(missing))
    header = model.read_bytes()[:4]
    return Check("Digital twin assets", PASS if header == b"glTF" else FAIL,
                 f"astronaut.glb {model.stat().st_size // 1024} KB, 3D twin + SVG fallback present")


def check_iss_budget() -> Check:
    """Phase 9 budget: optimized ISS glb at most 15 MB."""
    model = STATIC_DIR / "models" / "iss.glb"
    if not model.exists():
        return Check("ISS model (15 MB)", FAIL, "app/static/models/iss.glb missing")
    size = model.stat().st_size
    return Check("ISS model (15 MB)", PASS if size <= 15 * 1024 * 1024 else FAIL, f"{size / 1048576:.1f} MB")


def _start_server(temp: Path, extra: dict[str, str]) -> tuple[subprocess.Popen, int, Path]:
    port = _free_port()
    env = _throwaway_env(temp, port)
    env.update(extra)
    log_path = temp / "server.log"
    handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, str(ROOT / "run.py")], cwd=ROOT, env=env, stdout=handle,
                               stderr=subprocess.STDOUT)
    started = time.monotonic()
    while time.monotonic() - started < BOOT_TIMEOUT_S and process.poll() is None:
        try:
            _first_byte_ms(port, "/healthz")
            break
        except OSError:
            time.sleep(0.25)
    return process, port, log_path


def _stop_server(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def _login_session(base: str, astro_id: str):
    import requests

    browser = requests.Session()
    page = browser.get(f"{base}/login", timeout=5).text
    marker = 'name="csrf_token" value="'
    token = page.split(marker)[1].split('"')[0]
    browser.post(f"{base}/login", data={"astro_id": astro_id, "csrf_token": token}, timeout=5)
    return browser


def check_live_path() -> list[Check]:
    """Phase 3: a real server, the device over HTTP, and an SSE client in the browser's place."""
    import threading

    import requests

    from app.services.sensors.synthetic import SyntheticWearable

    token = "verify-device-token-0123456789"
    crew = "AST-1001:Cmdr. Sara Whitman:Commander:Falcon"
    checks: list[Check] = []
    with tempfile.TemporaryDirectory(prefix="astrovital-live-", ignore_cleanup_errors=True) as temp:
        process, port, log_path = _start_server(Path(temp), {
            "DEVICE_TOKEN": token, "REGISTERED_ASTRONAUTS": crew, "DEVICE_WEARER_ID": "AST-1001",
            "SEED_ON_FIRST_RUN": "false", "FLASK_SECRET_KEY": "verify-only", "ZEROCONF_ENABLED": "false"})
        base = f"http://127.0.0.1:{port}"
        try:
            browser = _login_session(base, "AST-1001")
            received: list[tuple[float, str]] = []
            stop = threading.Event()

            def listen() -> None:
                with browser.get(f"{base}/api/stream", stream=True, timeout=30) as response:
                    for line in response.iter_lines(decode_unicode=True):
                        if stop.is_set():
                            return
                        if line and line.startswith("event: "):
                            received.append((time.perf_counter(), line[7:]))

            threading.Thread(target=listen, daemon=True).start()
            time.sleep(0.5)
            wearable = SyntheticWearable(seed=4)
            headers = {"X-Device-Token": token, "X-Device-Id": "AV-ESP32-01", "Content-Type": "application/json"}
            device = requests.Session()
            ingest_ms: list[float] = []
            latencies: list[float] = []
            for _ in range(60):
                body = json.dumps(wearable.batch([wearable.frame()]))
                before = sum(1 for _, name in received if name == "vital")
                sent = time.perf_counter()
                response = device.post(f"{base}/api/device/ingest", data=body, headers=headers, timeout=5)
                ingest_ms.append((time.perf_counter() - sent) * 1000)
                if response.status_code != 200:
                    checks.append(Check("Device ingest over HTTP", FAIL, f"got {response.status_code}"))
                    return checks
                deadline = time.perf_counter() + 2
                while time.perf_counter() < deadline:
                    vitals = [at for at, name in received if name == "vital"]
                    if len(vitals) > before:
                        latencies.append((vitals[-1] - sent) * 1000)
                        break
                    time.sleep(0.005)
            stop.set()
            p95 = sorted(ingest_ms)[int(len(ingest_ms) * 0.95) - 1]
            checks.append(Check("Ingest p95 under 50 ms", PASS if p95 < 50 else FAIL,
                                f"p95 {p95:.1f} ms over {len(ingest_ms)} batches (real HTTP)"))
            if len(latencies) < 50:
                checks.append(Check("Device-to-browser under 1.5 s", FAIL,
                                    f"only {len(latencies)} of 60 frames reached the SSE client"))
            else:
                worst = max(latencies)
                median_ms = sorted(latencies)[len(latencies) // 2]
                checks.append(Check("Device-to-browser under 1.5 s", PASS if worst < 1500 else FAIL,
                                    f"worst {worst:.0f} ms, median {median_ms:.0f} ms"))
        finally:
            _stop_server(process)
        problems = scan_log(log_path.read_text(encoding="utf-8", errors="replace"))
        checks.append(Check("Live server log clean", FAIL if problems else PASS,
                            "; ".join(problems[:3]) if problems else "no traceback, no unexpected warning"))
    return checks


def check_summary_with_raw_frames() -> Check:
    """/api/summary p95 with 30 days of history plus 7 days of raw 1 Hz frames."""
    from datetime import datetime, timedelta, timezone

    from app.extensions import db
    from app.models import Astronaut, Device, SensorSample

    with tempfile.TemporaryDirectory(prefix="astrovital-raw-", ignore_cleanup_errors=True) as temp:
        app = _seeded_client(Path(temp))
        with app.app_context():
            device = Device.query.filter_by(device_id="AV-ESP32-01").first()
            astronaut = db.session.get(Astronaut, device.astronaut_id)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            start = now - timedelta(days=7)
            table = SensorSample.__table__
            batch: list[dict] = []
            for i in range(7 * 86400):
                moment = start + timedelta(seconds=i)
                batch.append({"astronaut_id": astronaut.id, "device_pk": device.id, "boot_id": "a0", "seq": i,
                              "ts": moment, "received_at": moment, "buffered": False, "finger": True, "hr": 72.0,
                              "spo2": 98.0, "temp_state": "settled", "quality": 90.0})
                if len(batch) == 20000:
                    db.session.execute(table.insert(), batch)
                    batch = []
            if batch:
                db.session.execute(table.insert(), batch)
            db.session.commit()
            count = SensorSample.query.count()
            astro_id = astronaut.astro_id
        client = app.test_client()
        client.post("/login", data={"astro_id": astro_id})
        client.get("/api/summary")
        timings = []
        for _ in range(30):
            started = time.perf_counter()
            client.get("/api/summary")
            timings.append((time.perf_counter() - started) * 1000)
        _dispose(app)
    p95 = sorted(timings)[int(len(timings) * 0.95) - 1]
    return Check("/api/summary p95 with 7 days of raw frames", PASS if p95 < 300 else FAIL,
                 f"p95 {p95:.0f} ms ({count:,} raw frames + 30 days of history)")


def check_emulator_profiles() -> Check:
    import device_emulator

    expected = ("normal", "no_finger", "finger_flap", "weak_signal", "spike", "flatline", "probe_missing",
                "probe_ambient", "probe_warming", "wifi_gap", "duplicate", "bad_token", "malformed", "flood",
                "restart")
    missing = [name for name in expected if name not in device_emulator.PROFILES]
    return Check("Emulator profiles (10A.11)", FAIL if missing else PASS,
                 "missing: " + ", ".join(missing) if missing else f"{len(device_emulator.PROFILES)} profiles")


def _pio() -> tuple[str | None, dict[str, str]]:
    """PlatformIO executable and environment (uses the project's build cache when present)."""
    candidates = [ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("pio.exe" if os.name == "nt" else "pio")]
    found = next((str(path) for path in candidates if path.exists()), None) or shutil.which("pio")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    cache = ROOT / "build_sources" / "platformio"
    if cache.exists():
        env["PLATFORMIO_CORE_DIR"] = str(cache)
    msys = Path("C:/msys64/ucrt64/bin")
    if msys.exists():
        env["PATH"] = f"{msys}{os.pathsep}{env.get('PATH', '')}"
    return found, env


def check_firmware() -> list[Check]:
    """Phase 4: the firmware compiles and its pure-logic tests pass (or the reason is recorded)."""
    pio, env = _pio()
    if pio is None:
        return [Check("Firmware compiles", SKIP, "firmware not compiled: PlatformIO not installed "
                                                 "(pip install -r requirements-dev.txt)")]
    secrets = ROOT / "firmware" / "include" / "secrets.h"
    temporary = not secrets.exists()
    if temporary:
        secrets.write_text((ROOT / "firmware" / "include" / "secrets.example.h").read_text(encoding="utf-8"),
                           encoding="utf-8")
    try:
        build = subprocess.run([pio, "run", "-d", str(ROOT / "firmware"), "-e", "esp32dev"], capture_output=True,
                               text=True, env=env, timeout=1200)
    except subprocess.TimeoutExpired:
        build = None
    finally:
        if temporary:
            secrets.unlink(missing_ok=True)
    checks = []
    if build is None:
        checks.append(Check("Firmware compiles", FAIL, "build timed out"))
    else:
        usage = [line.strip() for line in build.stdout.splitlines() if line.strip().startswith(("RAM:", "Flash:"))]
        checks.append(Check("Firmware compiles", PASS if build.returncode == 0 else FAIL,
                            "; ".join(usage) if build.returncode == 0 else build.stdout.strip().splitlines()[-1][:200]))
    compiler = shutil.which("g++", path=env.get("PATH")) or shutil.which("clang++", path=env.get("PATH"))
    if compiler is None:
        checks.append(Check("Firmware logic tests (native)", SKIP, "no host C++ compiler on PATH"))
    else:
        tests = subprocess.run([pio, "test", "-d", str(ROOT / "firmware"), "-e", "native"], capture_output=True,
                               text=True, env=env, timeout=600)
        summary = next((line for line in reversed(tests.stdout.splitlines()) if "test cases" in line), "")
        checks.append(Check("Firmware logic tests (native)", PASS if tests.returncode == 0 else FAIL,
                            summary.strip("= ") or tests.stdout.strip().splitlines()[-1][:200]))
    return checks


def check_module_files(phase: int) -> Check:
    needed = {
        5: ["app/cardio/routes.py", "app/templates/cardio.html", "app/static/js/app/cardio.js",
            "app/static/js/app/ecg_synth.js", "app/static/js/app/ble.js", "app/static/js/app/charts.js"],
        6: ["app/musculoskeletal/routes.py", "app/services/pose_service.py", "app/services/loading_index.py",
            "app/static/js/app/exercise.js", "app/static/js/app/pose_adapters.js",
            "app/static/vendor/mediapipe/vision_bundle.mjs", "app/static/vendor/mediapipe/pose_landmarker_lite.task",
            "app/static/vendor/mediapipe/wasm/vision_wasm_internal.wasm"],
    }[phase]
    missing = [name for name in needed if not (ROOT / name).exists()]
    label = {5: "Heart check files", 6: "Bone & Muscle files (incl. MediaPipe)"}[phase]
    return Check(label, FAIL if missing else PASS, "missing: " + ", ".join(missing) if missing
                 else f"{len(needed)} files present")


PHASES: dict[int, list[Callable[[], Check | list[Check]]]] = {
    0: [
        check_python, check_packages, check_layout, check_env_example, check_requirements_pinned,
        check_gitignore, check_assets, check_hardware_facts, check_pytest, check_boot, check_route_smoke,
        check_forbidden_patterns, check_secrets_not_in_source, check_label_scan_files, check_budgets,
        check_node_syntax,
    ],
    1: [check_summary_speed],
    2: [check_twin_assets],
    3: [check_emulator_profiles, check_live_path, check_summary_with_raw_frames],
    4: [check_firmware],
    5: [lambda: check_module_files(5)],
    6: [lambda: check_module_files(6)],
}


def run_checks(functions: Iterable[Callable[[], Check | list[Check]]]) -> list[Check]:
    results: list[Check] = []
    for function in functions:
        try:
            outcome = function()
        except Exception as error:  # noqa: BLE001 (a crashing check is a failed check)
            outcome = Check(function.__name__, FAIL, f"check crashed: {type(error).__name__}: {error}")
        results += outcome if isinstance(outcome, list) else [outcome]
    return results


def phase_checks(up_to: int) -> list[Check]:
    results: list[Check] = []
    for phase in range(up_to + 1):
        if phase not in PHASES:
            results.append(Check(f"Phase {phase} gate", FAIL, "this phase has no gate yet (not built)"))
            continue
        results += run_checks(PHASES[phase])
    return results


# ── reporting ─────────────────────────────────────────────

def _git_commit() -> str:
    git = shutil.which("git")
    if not git:
        return "unknown"
    result = subprocess.run([git, "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return result.stdout.strip() or "unknown"


def summarise(checks: list[Check]) -> str:
    counts = {status: sum(check.status == status for check in checks) for status in (PASS, FAIL, SKIP, INFO)}
    verdict = "GREEN" if counts[FAIL] == 0 else "RED"
    return (f"{verdict}: {counts[PASS]} passed, {counts[FAIL]} failed, "
            f"{counts[SKIP]} skipped, {counts[INFO]} informational")


def write_report(mode: str, checks: list[Check]) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Last verify result",
        "",
        f"- Mode: `{mode}`",
        f"- When: {now}",
        f"- Python: {sys.version.split()[0]} · commit `{_git_commit()}`",
        f"- Result: **{summarise(checks)}**",
        "",
        "| # | Check | Result | Detail |",
        "|---|---|---|---|",
    ]
    for index, check in enumerate(checks, start=1):
        lines.append(f"| {index} | {check.name} | {check.status} | {check.detail.replace('|', '/')} |")
    path = ROOT / "docs" / "verify_last.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def print_checks(checks: list[Check]) -> None:
    for check in checks:
        sys.stdout.write(f"  {check.status:4}  {check.name}" + (f": {check.detail}" if check.detail else "") + "\n")
    sys.stdout.write(f"\n  {summarise(checks)}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the AstroVital build.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--quick", action="store_true", help="setup sanity check")
    group.add_argument("--phase", type=int, metavar="N", help="cumulative gate for phases 0..N")
    group.add_argument("--full", action="store_true", help="every defined phase plus performance budgets")
    args = parser.parse_args(argv)

    if args.phase is not None:
        mode, checks = f"--phase {args.phase}", phase_checks(args.phase)
    elif args.full:
        mode, checks = "--full", phase_checks(max(PHASES))
    else:
        mode, checks = "--quick", run_checks([quick_checks])

    sys.stdout.write(f"AstroVital verify {mode}\n")
    print_checks(checks)
    if mode != "--quick":
        sys.stdout.write(f"  Report written to {_rel(write_report(mode, checks))}\n")
    return 1 if any(check.status == FAIL for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
