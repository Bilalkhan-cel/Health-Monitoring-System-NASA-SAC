"""Config loading, validation and the boot checklist."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from config import (
    BASE_DIR,
    build_checklist,
    clean_env_value,
    load_config,
    parse_crew,
    read_env,
    render_checklist,
)


def test_loads_with_an_empty_environment():
    config = load_config({})
    assert config.port == 5000
    assert config.secret_key_generated and len(config.secret_key) == 64
    assert config.astronauts == ()
    assert config.database_url.endswith("/instance/astrovital.db")
    assert config.sensor_mode == "device"


def test_comment_only_value_counts_as_empty():
    assert clean_env_value("# setup.py generates one") == ""
    assert clean_env_value("  value  ") == "value"
    assert clean_env_value(None) == ""


def test_env_example_is_valid_and_complete():
    values = read_env(BASE_DIR / ".env.example", overrides={})
    config = load_config(values)
    assert config.warnings == ()
    assert [member.astro_id for member in config.astronauts] == ["AST-1001", "AST-1002", "AST-1003"]
    assert [member.callsign for member in config.surgeons] == ["Hippocrates"]
    assert config.surgeons[0].is_surgeon
    assert config.mission_day == 160
    assert config.default_environment == "Mars Base"
    assert config.secret_key_generated, "the example file must not ship a secret"
    assert config.device_token == "" and config.openhome_api_key == ""
    assert config.meal_times == ("07:30", "12:30", "18:30")
    assert config.temp_offset_c == 0.6


def test_process_environment_overrides_the_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("PORT=5000\nMISSION_NAME=FROM-FILE\n", encoding="utf-8")
    monkeypatch.setenv("PORT", "6001")
    values = read_env(env_file)
    assert values["PORT"] == "6001"
    assert values["MISSION_NAME"] == "FROM-FILE"


def test_bind_host_follows_the_wearable_setting():
    assert load_config({"DEVICE_ENABLED": "true"}).bind_host == "0.0.0.0"
    assert load_config({"DEVICE_ENABLED": "false"}).bind_host == "127.0.0.1"
    assert load_config({"DEVICE_ENABLED": "true", "BIND_HOST": "127.0.0.1"}).bind_host == "127.0.0.1"


def test_invalid_bind_host_falls_back_to_loopback():
    config = load_config({"BIND_HOST": "not an address"})
    assert config.bind_host == "127.0.0.1"
    assert any("BIND_HOST" in warning for warning in config.warnings)


def test_parse_crew_accepts_four_fields_and_uppercases_ids():
    members, warnings = parse_crew("ast-1001:Sara Whitman:Commander:Falcon")
    assert warnings == []
    assert members[0].astro_id == "AST-1001" and members[0].callsign == "Falcon"
    assert not members[0].is_surgeon


def test_parse_crew_skips_malformed_and_duplicate_entries():
    raw = "AST-1:A:Role:One, broken-entry, AST-2:B:Role, AST-1:C:Role:Again, , AST-3::Role:Three"
    members, warnings = parse_crew(raw)
    assert [member.astro_id for member in members] == ["AST-1"]
    assert len(warnings) == 4


def test_surgeon_id_that_is_also_an_astronaut_is_ignored():
    config = load_config({"REGISTERED_ASTRONAUTS": "AST-1:A:Role:One", "FLIGHT_SURGEON_IDS": "AST-1:A:Surgeon:One"})
    assert config.surgeons == ()
    assert any("also appear" in warning for warning in config.warnings)


def test_bad_values_become_warnings_and_defaults():
    config = load_config({
        "PORT": "abc", "LIVE_STALE_S": "-4", "DEFAULT_ENVIRONMENT": "Pluto", "DEMO_MODE": "maybe",
        "MISSION_START_DATE": "soon", "MEAL_TIMES": "breakfast", "SENSOR_MODE": "auto", "MISSION_DAY_OVERRIDE": "x",
    })
    assert config.port == 5000
    assert config.live_stale_s == 5.0
    assert config.default_environment == "Mars Base"
    assert config.demo_mode is True
    assert config.mission_start_date == date(2026, 6, 1)
    assert config.meal_times == ("07:30", "12:30", "18:30")
    assert config.sensor_mode == "device"
    assert config.mission_day_override is None
    assert len(config.warnings) == 8


def test_mission_day_is_computed_from_the_start_date():
    today = datetime.now(timezone.utc).date()
    config = load_config({"MISSION_START_DATE": today.isoformat()})
    assert config.mission_day == 1


def test_relative_model_paths_resolve_inside_the_project():
    config = load_config({})
    assert config.whisper_model_path == BASE_DIR / "ml_models" / "whisper"
    assert config.nlp_emotion_path.is_absolute()


def test_instance_override_moves_uploads_too(tmp_path):
    config = load_config({"ASTROVITAL_INSTANCE_DIR": str(tmp_path / "inst")})
    assert config.uploads_dir == tmp_path / "inst" / "uploads"
    assert load_config({}).uploads_dir == BASE_DIR / "uploads"


def test_secret_values_skips_empty_and_short_values():
    config = load_config({"FLASK_SECRET_KEY": "a-long-flask-secret", "DEVICE_TOKEN": "short", "OPENHOME_API_KEY": ""})
    assert config.secret_values() == ("a-long-flask-secret",)


def test_session_cookie_is_http_only_and_lax(config):
    mapping = config.flask_mapping()
    assert mapping["SESSION_COOKIE_HTTPONLY"] is True
    assert mapping["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert mapping["SQLALCHEMY_ENGINE_OPTIONS"]["connect_args"]["check_same_thread"] is False


def test_checklist_without_keys_explains_every_gap(config):
    lines = build_checklist(config)
    text = "\n".join(render_checklist(lines))
    assert "Crew loaded (3 astronauts, 1 flight surgeon)" in text
    assert "OpenHome key missing: Dr. NOVA runs in fallback mode" in text
    assert "DEVICE_TOKEN set" in text
    assert "No wearable seen yet" in text
    assert "Sensor mode: device" in text
    assert f"Listening on 0.0.0.0:{config.port}, wearable URL http://" in text


def test_checklist_never_points_at_a_script_that_does_not_exist(config):
    for line in build_checklist(config):
        for word in line.fix.split():
            if word.startswith("scripts/"):
                assert (BASE_DIR / word).exists(), f"checklist mentions missing {word}"


def test_checklist_states(env_values):
    demo = load_config({**env_values, "SENSOR_MODE": "demo", "OPENHOME_MOCK": "true", "DEVICE_ENABLED": "false"})
    lines = {line.text: line.state for line in build_checklist(demo, wearable_last_seen_s=4)}
    assert lines["Sensor mode: DEMO DATA"] == "notice"
    assert lines["OpenHome mock mode: Dr. NOVA uses the local mock"] == "notice"
    assert any("wearable support is switched off" in text for text in lines)

    seen = load_config(env_values)
    text = " ".join(line.text for line in build_checklist(seen, wearable_last_seen_s=4))
    assert "Wearable AV-ESP32-01 last seen 4 s ago" in text

    broken = build_checklist(seen, db_ready=False)
    assert broken[0].state == "missing"


def test_ascii_checklist_has_no_unicode(config):
    for line in render_checklist(build_checklist(config), unicode=False):
        line.encode("ascii")
        assert line.startswith(("[ok]", "[--]", "[!!]"))


def test_config_module_is_not_shadowed_by_the_config_folder():
    import config as module

    assert Path(module.__file__).name == "config.py"
