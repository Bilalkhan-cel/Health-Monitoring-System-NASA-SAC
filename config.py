"""Load and validate the environment (.env) into one typed ``Config`` object.

Nothing in here raises on a bad or missing optional value: every problem becomes
a readable warning and a safe default, so the app always boots. The boot
checklist (``build_checklist``) turns the result into the lines ``run.py`` prints.
"""

from __future__ import annotations

import ipaddress
import os
import secrets
import socket
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Literal, Mapping

from dotenv import dotenv_values

BASE_DIR = Path(__file__).resolve().parent
VERSION = "0.1.0"

ENVIRONMENTS: tuple[str, ...] = ("Spacecraft", "Space Station", "Rover", "Lunar Base", "Mars Base")
WHISPER_SIZES: tuple[str, ...] = ("tiny", "base", "small")
POSE_BACKENDS: tuple[str, ...] = ("mediapipe", "hf_vitpose")
SENSOR_MODES: tuple[str, ...] = ("device", "demo")
TEMP_SITES: tuple[str, ...] = ("axilla", "skin")

FONT_FILES: tuple[str, ...] = (
    "geist-latin-wght-normal.woff2",
    "geist-mono-latin-wght-normal.woff2",
    "instrument-serif-latin-400-italic.woff2",
)

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class CrewMember:
    """One pre-registered crew account parsed from ``.env``."""

    astro_id: str
    name: str
    role: str
    callsign: str
    is_surgeon: bool = False


@dataclass(frozen=True)
class CheckLine:
    """One line of the boot checklist."""

    state: Literal["ok", "missing", "notice"]
    text: str
    fix: str = ""


def clean_env_value(value: str | None) -> str:
    """Normalise a raw .env value.

    ``KEY=      # comment`` is parsed by python-dotenv as the comment text, so a
    value that starts with ``#`` is treated as empty.
    """
    if value is None:
        return ""
    value = value.strip()
    return "" if value.startswith("#") else value


def parse_crew(raw: str, *, is_surgeon: bool = False) -> tuple[list[CrewMember], list[str]]:
    """Parse ``ID:Full Name:Role:Callsign`` entries separated by commas.

    Malformed or duplicate entries are skipped and reported, never raised.
    """
    members: list[CrewMember] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for entry in (part.strip() for part in raw.split(",")):
        if not entry:
            continue
        fields = [field.strip() for field in entry.split(":")]
        if len(fields) != 4 or not all(fields):
            warnings.append(f"Skipped crew entry '{entry}': expected ASTRO_ID:Full Name:Role:Callsign")
            continue
        astro_id = fields[0].upper()
        if astro_id in seen:
            warnings.append(f"Skipped crew entry '{entry}': {astro_id} is listed twice")
            continue
        seen.add(astro_id)
        members.append(CrewMember(astro_id, fields[1], fields[2], fields[3], is_surgeon))
    return members, warnings


class _Env:
    """Typed reader over an environment mapping that collects warnings."""

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = values
        self.warnings: list[str] = []

    def str(self, key: str, default: str = "") -> str:
        value = clean_env_value(self._values.get(key))
        return value or default

    def bool(self, key: str, default: bool) -> bool:
        value = self.str(key).lower()
        if not value:
            return default
        if value in _TRUE:
            return True
        if value in _FALSE:
            return False
        self.warnings.append(f"{key}='{value}' is not true/false; using {str(default).lower()}")
        return default

    def int(self, key: str, default: int, lo: int | None = None, hi: int | None = None) -> int:
        return int(self._number(key, default, lo, hi, int))

    def float(self, key: str, default: float, lo: float | None = None, hi: float | None = None) -> float:
        return float(self._number(key, default, lo, hi, float))

    def opt_int(self, key: str) -> int | None:
        value = self.str(key)
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            self.warnings.append(f"{key}='{value}' is not a whole number; ignoring it")
            return None

    def choice(self, key: str, default: str, options: Iterable[str]) -> str:
        value = self.str(key, default)
        lookup = {option.lower(): option for option in options}
        if value.lower() in lookup:
            return lookup[value.lower()]
        self.warnings.append(f"{key}='{value}' is not one of {', '.join(lookup.values())}; using {default}")
        return default

    def csv(self, key: str, default: str = "") -> tuple[str, ...]:
        return tuple(part.strip() for part in self.str(key, default).split(",") if part.strip())

    def _number(self, key, default, lo, hi, cast):
        value = self.str(key)
        if not value:
            return default
        try:
            number = cast(value)
        except ValueError:
            self.warnings.append(f"{key}='{value}' is not a number; using {default}")
            return default
        if (lo is not None and number < lo) or (hi is not None and number > hi):
            self.warnings.append(f"{key}={value} is outside {lo}..{hi}; using {default}")
            return default
        return number


@dataclass(frozen=True)
class Config:
    """Every setting the app reads, already validated."""

    base_dir: Path
    instance_dir: Path
    uploads_dir: Path
    # Flask
    secret_key: str
    secret_key_generated: bool
    debug: bool
    database_url: str
    public_base_url: str
    trusted_hosts: tuple[str, ...]
    bind_host: str
    port: int
    # Crew
    astronauts: tuple[CrewMember, ...]
    surgeons: tuple[CrewMember, ...]
    # Mission
    mission_name: str
    mission_start_date: date
    mission_day_override: int | None
    default_environment: str
    # OpenHome (Dr. NOVA)
    openhome_api_key: str
    openhome_agent_id: str
    openhome_voice_ws: str
    openhome_bridge_token: str
    openhome_enabled: bool
    openhome_mock: bool
    fallback_llm_api_key: str
    fallback_llm_base_url: str
    fallback_llm_model: str
    # Local ML
    whisper_model_size: str
    whisper_model_path: Path
    whisper_compute_type: str
    nlp_sentiment_path: Path
    nlp_emotion_path: Path
    pose_backend: str
    pose_model_path: Path
    mental_session_target_min: int
    mental_session_min_seconds: int
    mental_session_max_min: int
    cardio_session_seconds: int
    store_transcripts: bool
    # Wearable
    device_enabled: bool
    device_token: str
    device_id: str
    device_wearer_id: str
    device_auto_register: bool
    device_hosts: tuple[str, ...]
    device_lan_ip: str
    device_rate_limit: str
    sensor_mode: str
    zeroconf_enabled: bool
    live_stale_s: float
    device_offline_s: float
    backlog_live_max_s: float
    finger_settle_s: float
    min_signal_quality: int
    agg_window_s: int
    agg_min_valid: int
    raw_retention_days: int
    temp_site: str
    temp_offset_c: float
    temp_contact_min_c: float
    temp_settle_min_raw_c: float
    temp_settle_slope_c_per_min: float
    sim_record_interval_min: int
    meal_times: tuple[str, ...]
    # Demo
    demo_mode: bool
    seed_days: int
    seed_on_first_run: bool
    # Validation output
    warnings: tuple[str, ...] = ()

    # ── derived values ────────────────────────────────────
    @property
    def mission_day(self) -> int:
        """Mission day shown in the UI (Day 1 = the start date, UTC calendar)."""
        if self.mission_day_override is not None:
            return self.mission_day_override
        today = datetime.now(timezone.utc).date()
        return max(1, (today - self.mission_start_date).days + 1)

    @property
    def fonts_dir(self) -> Path:
        return self.base_dir / "app" / "static" / "vendor" / "fonts"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def openhome_configured(self) -> bool:
        return bool(self.openhome_api_key and self.openhome_agent_id)

    def secret_values(self) -> tuple[str, ...]:
        """Values that must never appear in a log line."""
        candidates = (
            self.secret_key,
            self.openhome_api_key,
            self.openhome_bridge_token,
            self.fallback_llm_api_key,
            self.device_token,
        )
        return tuple(value for value in candidates if len(value) >= 8)

    def flask_mapping(self) -> dict[str, object]:
        """Settings in the shape ``Flask.config`` expects."""
        mapping: dict[str, object] = {
            "SECRET_KEY": self.secret_key,
            "DEBUG": self.debug,
            "SQLALCHEMY_DATABASE_URI": self.database_url,
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "SESSION_COOKIE_HTTPONLY": True,
            "SESSION_COOKIE_SAMESITE": "Lax",
            # SECURITY NOTE: the app is served over plain HTTP on localhost, so the
            # cookie cannot be Secure here. Production must sit behind HTTPS and set it.
            "SESSION_COOKIE_SECURE": False,
            "WTF_CSRF_TIME_LIMIT": None,
            "MAX_CONTENT_LENGTH": 4 * 1024 * 1024,
            "RATELIMIT_STORAGE_URI": "memory://",
            "RATELIMIT_HEADERS_ENABLED": True,
        }
        if self.is_sqlite:
            mapping["SQLALCHEMY_ENGINE_OPTIONS"] = {
                "connect_args": {"check_same_thread": False, "timeout": 5},
            }
        return mapping


def _resolve(base_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base_dir / path)


def _parse_date(env: _Env, key: str, default: date) -> date:
    value = env.str(key)
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        env.warnings.append(f"{key}='{value}' is not a YYYY-MM-DD date; using {default.isoformat()}")
        return default


def _parse_meal_times(env: _Env) -> tuple[str, ...]:
    default = ("07:30", "12:30", "18:30")
    times = env.csv("MEAL_TIMES", ",".join(default))
    for item in times:
        try:
            datetime.strptime(item, "%H:%M")
        except ValueError:
            env.warnings.append(f"MEAL_TIMES entry '{item}' is not HH:MM; using {','.join(default)}")
            return default
    return times or default


def _valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def read_env(env_file: Path | None = None, overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    """Merge ``.env`` with the process environment (the process wins)."""
    values: dict[str, str] = {}
    if env_file is not None and env_file.exists():
        values.update({key: value or "" for key, value in dotenv_values(env_file).items()})
    values.update(os.environ if overrides is None else overrides)
    return values


def load_config(
    values: Mapping[str, str] | None = None,
    *,
    base_dir: Path = BASE_DIR,
    env_file: Path | None = None,
) -> Config:
    """Build a validated ``Config``.

    ``values`` replaces both ``.env`` and the process environment (used by tests).
    """
    if values is None:
        # ASTROVITAL_ENV_FILE and ASTROVITAL_INSTANCE_DIR let tests and verify.py run
        # against a throwaway environment without touching the real .env or database.
        override = clean_env_value(os.environ.get("ASTROVITAL_ENV_FILE"))
        default_file = Path(override) if override else base_dir / ".env"
        values = read_env(env_file if env_file is not None else default_file)
    env = _Env(values)

    instance_override = env.str("ASTROVITAL_INSTANCE_DIR")
    instance_dir = _resolve(base_dir, instance_override or "instance")
    uploads_dir = (instance_dir / "uploads") if instance_override else (base_dir / "uploads")
    database_url = env.str("DATABASE_URL") or f"sqlite:///{(instance_dir / 'astrovital.db').as_posix()}"

    secret_key = env.str("FLASK_SECRET_KEY")
    secret_key_generated = not secret_key
    if secret_key_generated:
        secret_key = secrets.token_hex(32)

    astronauts, crew_warnings = parse_crew(env.str("REGISTERED_ASTRONAUTS"))
    surgeons, surgeon_warnings = parse_crew(env.str("FLIGHT_SURGEON_IDS"), is_surgeon=True)
    env.warnings.extend(crew_warnings + surgeon_warnings)
    astronaut_ids = {member.astro_id for member in astronauts}
    clashing = [member.astro_id for member in surgeons if member.astro_id in astronaut_ids]
    if clashing:
        env.warnings.append(f"Flight surgeon ID(s) {', '.join(clashing)} also appear in REGISTERED_ASTRONAUTS; ignored")
        surgeons = [member for member in surgeons if member.astro_id not in astronaut_ids]

    device_enabled = env.bool("DEVICE_ENABLED", True)
    bind_host = env.str("BIND_HOST") or ("0.0.0.0" if device_enabled else "127.0.0.1")
    if not _valid_ip(bind_host) and bind_host != "localhost":
        env.warnings.append(f"BIND_HOST='{bind_host}' is not an IP address; using 127.0.0.1")
        bind_host = "127.0.0.1"

    device_lan_ip = env.str("DEVICE_LAN_IP")
    if device_lan_ip and not _valid_ip(device_lan_ip):
        env.warnings.append(f"DEVICE_LAN_IP='{device_lan_ip}' is not an IP address; auto-detecting instead")
        device_lan_ip = ""

    device_wearer_id = env.str("DEVICE_WEARER_ID", "AST-1001").upper()
    if device_enabled and astronauts and device_wearer_id not in astronaut_ids:
        env.warnings.append(f"DEVICE_WEARER_ID={device_wearer_id} is not in REGISTERED_ASTRONAUTS")

    return Config(
        base_dir=base_dir,
        instance_dir=instance_dir,
        uploads_dir=uploads_dir,
        secret_key=secret_key,
        secret_key_generated=secret_key_generated,
        debug=env.bool("FLASK_DEBUG", False),
        database_url=database_url,
        public_base_url=env.str("PUBLIC_BASE_URL", "http://localhost:5000").rstrip("/"),
        trusted_hosts=tuple(host.lower() for host in env.csv("TRUSTED_HOSTS", "localhost,127.0.0.1")),
        bind_host=bind_host,
        port=env.int("PORT", 5000, 1, 65535),
        astronauts=tuple(astronauts),
        surgeons=tuple(surgeons),
        mission_name=env.str("MISSION_NAME", "ARES-SURFACE-01"),
        mission_start_date=_parse_date(env, "MISSION_START_DATE", date(2026, 6, 1)),
        mission_day_override=env.opt_int("MISSION_DAY_OVERRIDE"),
        default_environment=env.choice("DEFAULT_ENVIRONMENT", "Mars Base", ENVIRONMENTS),
        openhome_api_key=env.str("OPENHOME_API_KEY"),
        openhome_agent_id=env.str("OPENHOME_AGENT_ID"),
        openhome_voice_ws=env.str(
            "OPENHOME_VOICE_WS", "wss://app.openhome.com/websocket/voice-stream/{api_key}/{agent_id}"
        ),
        openhome_bridge_token=env.str("OPENHOME_BRIDGE_TOKEN"),
        openhome_enabled=env.bool("OPENHOME_ENABLED", True),
        openhome_mock=env.bool("OPENHOME_MOCK", False),
        fallback_llm_api_key=env.str("FALLBACK_LLM_API_KEY"),
        fallback_llm_base_url=env.str("FALLBACK_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        fallback_llm_model=env.str("FALLBACK_LLM_MODEL", "gpt-4o-mini"),
        whisper_model_size=env.choice("WHISPER_MODEL_SIZE", "base", WHISPER_SIZES),
        whisper_model_path=_resolve(base_dir, env.str("WHISPER_MODEL_PATH", "ml_models/whisper")),
        whisper_compute_type=env.str("WHISPER_COMPUTE_TYPE", "int8"),
        nlp_sentiment_path=_resolve(base_dir, env.str("NLP_SENTIMENT_PATH", "ml_models/sentiment")),
        nlp_emotion_path=_resolve(base_dir, env.str("NLP_EMOTION_PATH", "ml_models/emotion")),
        pose_backend=env.choice("POSE_BACKEND", "mediapipe", POSE_BACKENDS),
        pose_model_path=_resolve(base_dir, env.str("POSE_MODEL_PATH", "ml_models/pose")),
        mental_session_target_min=env.int("MENTAL_SESSION_TARGET_MIN", 3, 1, 60),
        mental_session_min_seconds=env.int("MENTAL_SESSION_MIN_SECONDS", 60, 5, 3600),
        mental_session_max_min=env.int("MENTAL_SESSION_MAX_MIN", 20, 1, 120),
        cardio_session_seconds=env.int("CARDIO_SESSION_SECONDS", 90, 10, 3600),
        store_transcripts=env.bool("STORE_TRANSCRIPTS", False),
        device_enabled=device_enabled,
        device_token=env.str("DEVICE_TOKEN"),
        device_id=env.str("DEVICE_ID", "AV-ESP32-01"),
        device_wearer_id=device_wearer_id,
        device_auto_register=env.bool("DEVICE_AUTO_REGISTER", False),
        device_hosts=tuple(host.lower() for host in env.csv("DEVICE_HOSTS")),
        device_lan_ip=device_lan_ip,
        device_rate_limit=env.str("DEVICE_RATE_LIMIT", "120/minute"),
        sensor_mode=env.choice("SENSOR_MODE", "device", SENSOR_MODES),
        zeroconf_enabled=env.bool("ZEROCONF_ENABLED", True),
        live_stale_s=env.float("LIVE_STALE_S", 5.0, 1, 600),
        device_offline_s=env.float("DEVICE_OFFLINE_S", 10.0, 1, 3600),
        backlog_live_max_s=env.float("BACKLOG_LIVE_MAX_S", 30.0, 1, 3600),
        finger_settle_s=env.float("FINGER_SETTLE_S", 8.0, 0, 120),
        min_signal_quality=env.int("MIN_SIGNAL_QUALITY", 50, 0, 100),
        agg_window_s=env.int("AGG_WINDOW_S", 60, 10, 3600),
        agg_min_valid=env.int("AGG_MIN_VALID", 20, 1, 3600),
        raw_retention_days=env.int("RAW_RETENTION_DAYS", 7, 1, 365),
        temp_site=env.choice("TEMP_SITE", "axilla", TEMP_SITES),
        temp_offset_c=env.float("TEMP_OFFSET_C", 0.6, -2.0, 2.0),
        temp_contact_min_c=env.float("TEMP_CONTACT_MIN_C", 30.0, 10, 45),
        temp_settle_min_raw_c=env.float("TEMP_SETTLE_MIN_RAW_C", 34.5, 10, 45),
        temp_settle_slope_c_per_min=env.float("TEMP_SETTLE_SLOPE_C_PER_MIN", 0.1, 0.01, 5),
        sim_record_interval_min=env.int("SIM_RECORD_INTERVAL_MIN", 5, 1, 60),
        meal_times=_parse_meal_times(env),
        demo_mode=env.bool("DEMO_MODE", True),
        seed_days=env.int("SEED_DAYS", 30, 1, 365),
        seed_on_first_run=env.bool("SEED_ON_FIRST_RUN", True),
        warnings=tuple(env.warnings),
    )


# ── boot checklist ────────────────────────────────────────

def detect_lan_ip(config: Config) -> str:
    """Best guess at this computer's LAN address (no packet is sent)."""
    if config.device_lan_ip:
        return config.device_lan_ip
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def fonts_present(config: Config) -> list[str]:
    return [name for name in FONT_FILES if (config.fonts_dir / name).is_file()]


def whisper_model_found(config: Config) -> bool:
    return (config.whisper_model_path / config.whisper_model_size / "model.bin").is_file()


def hf_model_found(path: Path) -> bool:
    return (path / "config.json").is_file()


def _format_age(seconds: float) -> str:
    if seconds < 90:
        return f"{int(seconds)} s"
    if seconds < 5400:
        return f"{int(seconds // 60)} min"
    return f"{int(seconds // 3600)} h"


def build_checklist(
    config: Config,
    *,
    db_ready: bool = True,
    crew_loaded: int | None = None,
    wearable_last_seen_s: float | None = None,
    sensor_mode: str | None = None,
) -> list[CheckLine]:
    """Describe what is ready and what is missing, with the fix for each gap."""
    lines: list[CheckLine] = []
    add = lines.append

    if db_ready:
        add(CheckLine("ok", f"Database ready ({'SQLite' if config.is_sqlite else 'external'})"))
    else:
        add(CheckLine("missing", "Database could not be opened", "check DATABASE_URL in .env"))

    crew_count = len(config.astronauts) if crew_loaded is None else crew_loaded
    if crew_count:
        surgeons = f", {len(config.surgeons)} flight surgeon" if config.surgeons else ""
        add(CheckLine("ok", f"Crew loaded ({crew_count} astronauts{surgeons})"))
    else:
        add(CheckLine("missing", "No crew in .env", "set REGISTERED_ASTRONAUTS; nobody can log in"))

    if config.secret_key_generated:
        add(CheckLine("notice", "FLASK_SECRET_KEY is empty: using a temporary key (logins reset on restart)",
                      "run python scripts/setup.py"))

    found_fonts = fonts_present(config)
    if len(found_fonts) == len(FONT_FILES):
        add(CheckLine("ok", f"Fonts found ({len(found_fonts)})"))
    else:
        add(CheckLine("missing", "Fonts missing: using system fonts", "run python scripts/fetch_assets.py"))

    if whisper_model_found(config):
        add(CheckLine("ok", f"Whisper model found ({config.whisper_model_size})"))
    else:
        add(CheckLine("missing", "Whisper model missing: voice check-in falls back to text",
                      "run python scripts/download_models.py"))

    nlp_ready = hf_model_found(config.nlp_sentiment_path) and hf_model_found(config.nlp_emotion_path)
    if nlp_ready:
        add(CheckLine("ok", "Sentiment and emotion models found"))
    else:
        add(CheckLine("missing", "Sentiment/emotion models missing: mood uses the self-rating only",
                      "run python scripts/download_models.py"))

    if not config.openhome_enabled:
        add(CheckLine("notice", "OpenHome is switched off: Dr. NOVA runs in fallback mode"))
    elif config.openhome_mock:
        add(CheckLine("notice", "OpenHome mock mode: Dr. NOVA uses the local mock"))
    elif config.openhome_configured:
        add(CheckLine("ok", "OpenHome key and agent id set"))
    else:
        add(CheckLine("missing", "OpenHome key missing: Dr. NOVA runs in fallback mode",
                      "add OPENHOME_API_KEY and OPENHOME_AGENT_ID to .env"))

    listening = f"Listening on {config.bind_host}:{config.port}"
    if config.device_enabled:
        add(CheckLine("ok", f"{listening}, wearable URL http://{detect_lan_ip(config)}:{config.port}"))
        if config.device_token:
            add(CheckLine("ok", "DEVICE_TOKEN set"))
        else:
            add(CheckLine("missing", "DEVICE_TOKEN missing: the wearable cannot connect",
                          "run python scripts/setup.py"))
        if wearable_last_seen_s is not None:
            add(CheckLine("ok", f"Wearable {config.device_id} last seen {_format_age(wearable_last_seen_s)} ago"))
        else:
            setup_script = config.base_dir / "scripts" / "device_setup.py"
            fix = "run python scripts/device_setup.py" if setup_script.exists() else ""
            add(CheckLine("missing", "No wearable seen yet", fix))
    else:
        add(CheckLine("ok", f"{listening} (wearable support is switched off)"))

    mode = sensor_mode or config.sensor_mode
    if mode == "demo":
        add(CheckLine("notice", "Sensor mode: DEMO DATA"))
    else:
        add(CheckLine("ok", "Sensor mode: device"))

    for warning in config.warnings:
        add(CheckLine("notice", warning))
    return lines


def render_checklist(lines: Iterable[CheckLine], *, unicode: bool = True) -> list[str]:
    """Turn checklist lines into printable text (ASCII marks when needed)."""
    marks = {"ok": "✓", "missing": "✗", "notice": "!"} if unicode else {"ok": "[ok]", "missing": "[--]", "notice": "[!!]"}
    arrow = "→" if unicode else "->"
    rendered = []
    for line in lines:
        text = f"{marks[line.state]} {line.text}"
        if line.fix:
            text += f" {arrow} {line.fix}"
        rendered.append(text)
    return rendered
