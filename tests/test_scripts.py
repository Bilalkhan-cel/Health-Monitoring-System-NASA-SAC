"""setup.py, fetch_assets.py and the verify.py scanners."""

from __future__ import annotations

import urllib.error
from pathlib import Path

import pytest

from conftest import ROOT, load_script

setup_script = load_script("setup")
fetch_assets = load_script("fetch_assets")
verify = load_script("verify")


# ── setup.py ──────────────────────────────────────────────

def test_fill_secrets_generates_only_the_empty_ones():
    text = ("FLASK_SECRET_KEY=                # generated\n"
            "DEVICE_TOKEN=\n"
            "OPENHOME_BRIDGE_TOKEN=keep-me\n"
            "OPENHOME_API_KEY=\n")
    updated, filled = setup_script.fill_secrets(text)
    assert filled == ["FLASK_SECRET_KEY", "DEVICE_TOKEN"]
    values = dict(line.split("=", 1) for line in updated.splitlines())
    assert len(values["FLASK_SECRET_KEY"]) == 64
    assert len(values["DEVICE_TOKEN"]) >= 32
    assert values["OPENHOME_BRIDGE_TOKEN"] == "keep-me"
    assert values["OPENHOME_API_KEY"] == "", "API keys are never invented"


def test_fill_secrets_is_idempotent():
    first, _ = setup_script.fill_secrets("FLASK_SECRET_KEY=\nDEVICE_TOKEN=\nOPENHOME_BRIDGE_TOKEN=\n")
    second, filled = setup_script.fill_secrets(first)
    assert filled == [] and second == first


def test_ensure_env_file_creates_env_from_the_example(tmp_path):
    (tmp_path / ".env.example").write_text((ROOT / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
    actions = setup_script.ensure_env_file(tmp_path)
    assert actions[0] == "created .env from .env.example"
    assert "FLASK_SECRET_KEY, OPENHOME_BRIDGE_TOKEN, DEVICE_TOKEN" in actions[1]

    from config import load_config, read_env

    config = load_config(read_env(tmp_path / ".env", overrides={}))
    assert not config.secret_key_generated and config.device_token and config.openhome_bridge_token
    assert len(config.astronauts) == 3 and config.warnings == ()
    assert setup_script.ensure_env_file(tmp_path) == [], "second run changes nothing"


# ── fetch_assets.py ───────────────────────────────────────

def test_manifest_is_valid_and_stays_inside_vendor():
    assets = fetch_assets.load_manifest()
    assert len(assets) >= 6
    assert len({asset.dest for asset in assets}) == len(assets)
    for asset in assets:
        assert asset.dest.startswith("app/static/vendor/")
        pinned = "@" in asset.url or "/float16/1/" in asset.url
        assert asset.url.startswith("https://") and pinned, "URLs must pin a version"


@pytest.mark.parametrize("change", [
    {"url": "http://cdn.jsdelivr.net/npm/x@1/file.woff2"},
    {"url": "https://evil.example.com/file.woff2"},
    {"dest": "app/static/../../outside.txt"},
    {"dest": "scripts/setup.py"},
    {"sha256": "abc"},
])
def test_manifest_rejects_unsafe_entries(change):
    good = {"id": "x", "url": "https://cdn.jsdelivr.net/npm/x@1/file.woff2",
            "dest": "app/static/vendor/fonts/file.woff2", "sha256": "0" * 64, "bytes": 1}
    with pytest.raises(ValueError):
        fetch_assets.validate_asset(fetch_assets.Asset(**{**good, **change}))


def _asset(payload: bytes) -> "fetch_assets.Asset":
    return fetch_assets.Asset("x", "https://cdn.jsdelivr.net/npm/x@1/f.txt", "app/static/vendor/t/f.txt",
                              fetch_assets.sha256_bytes(payload), len(payload))


def test_fetch_saves_a_file_only_when_the_checksum_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_assets, "ROOT", tmp_path)
    asset = _asset(b"real content")

    tampered = fetch_assets.fetch([asset], downloader=lambda _asset: b"tampered")
    assert tampered[0].state == "failed" and "checksum" in tampered[0].detail
    assert not asset.path.exists()

    fetched = fetch_assets.fetch([asset], downloader=lambda _asset: b"real content")
    assert fetched[0].state == "fetched" and asset.path.read_bytes() == b"real content"

    def must_not_download(_asset):
        raise AssertionError("a current file must not be downloaded again")

    assert fetch_assets.fetch([asset], downloader=must_not_download)[0].state == "present"


def test_fetch_survives_being_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_assets, "ROOT", tmp_path)

    def offline(_asset):
        raise urllib.error.URLError("no network")

    results = fetch_assets.fetch([_asset(b"x")], downloader=offline)
    assert results[0].state == "failed" and "download failed" in results[0].detail


# ── verify.py scanners ────────────────────────────────────

def test_forbidden_scan_catches_each_pattern():
    scan = verify.scan_forbidden
    assert scan('<link href="https://fonts.googleapis.com/css2?family=Geist">', "html")
    assert scan('<script src="//cdn.jsdelivr.net/npm/three"></script>', "html")
    assert scan("{{ reply|safe }}", "html") == ["|safe filter"]
    assert scan("{{ reply | safe }}", "html") == ["|safe filter"]
    assert scan("console.log('x')", "js") == ["console.log left in"]
    assert scan("    print('debug')", "py") == ["print( in app code"]
    assert scan('key = "sk-abcdefghijklmnopqrstuvwxyz123456"', "py") == ["something shaped like a secret"]


def test_forbidden_scan_allows_normal_code():
    scan = verify.scan_forbidden
    assert scan('<svg xmlns="http://www.w3.org/2000/svg"></svg>', "html") == []
    assert scan('<a href="/static/css/theme.css">x</a> {{ value|e }} {{ a // b }}', "html") == []
    assert scan("app.register_blueprint(bp)\npprint(x)\nself.print(x)", "py") == []
    assert scan("// a comment\nconst a = b / c;", "js") == []
    assert scan('BASE = "https://api.openai.com/v1"', "py") == [], "server code may call external APIs"


def test_label_scan_catches_source_labels():
    scan = verify.scan_source_labels
    assert scan('<span class="badge">SIM</span>') == ["source tag 'SIM'"]
    assert scan("Heart rate 74 bpm SENSOR") == ["source tag 'SENSOR'"]
    assert scan("These values are simulated.") == ["word 'simulated'"]
    assert scan("Showing Demo Data today") == ["word 'demo data'"]
    assert scan("row.source", is_js=True) == ["a 'source' key"]
    assert scan('{"source": "sensor"}', is_js=True) == ["a 'source' key"]


def test_label_scan_allows_plain_language():
    scan = verify.scan_source_labels
    assert scan("Place a finger on the sensor. Similar readings are simple to compare.") == []
    assert scan("Demo data is generated for demonstration.", exempt_words=True) == []
    assert scan("const audioSource = ctx.createMediaStreamSource(stream);", is_js=True) == []


def test_find_source_keys_walks_nested_json():
    payload = {"metrics": [{"metric": "heart_rate", "source": "sensor"}, {"metric": "spo2"}], "live": {"source": 1}}
    assert verify.find_source_keys(payload) == ["$.metrics[0].source", "$.live.source"]
    assert verify.find_source_keys({"resource": "x", "sources_seen": 2}) == []


def test_log_scan_flags_tracebacks_and_warnings_only():
    log = "\n".join([
        "2026-11-14 12:00:00,001 INFO werkzeug WARNING: This is a development server. Do not use it in production.",
        "2026-11-14 12:00:00,002 INFO werkzeug 127.0.0.1 - - GET /healthz 200",
        "2026-11-14 12:00:01,003 WARNING app.bootstrap Could not delete leftover upload a.wav",
        "Traceback (most recent call last):",
        "2026-11-14 12:00:02,004 ERROR app Unhandled error on GET /boom",
    ])
    problems = verify.scan_log(log)
    assert len(problems) == 3
    assert problems[0].startswith("WARNING app.bootstrap") and problems[1] == "traceback"
    assert verify.scan_log(log, allowed=("leftover upload", "Unhandled error")) == ["traceback"]


def test_unpinned_requirements_are_reported():
    text = "# comment\n--extra-index-url https://x\n-r other.txt\nFlask==3.1.3\nrequests>=2\nnumpy  # loose\n"
    assert verify.unpinned_requirements(text) == ["requests>=2", "numpy"]


def test_project_requirements_are_pinned():
    for name in ("requirements-core.txt", "requirements-ml.txt"):
        assert verify.unpinned_requirements((ROOT / name).read_text(encoding="utf-8")) == []


def test_summary_is_red_when_anything_fails():
    Check = verify.Check
    assert verify.summarise([Check("a", verify.PASS), Check("b", verify.INFO)]).startswith("GREEN")
    assert verify.summarise([Check("a", verify.PASS), Check("b", verify.FAIL)]).startswith("RED")


def test_a_phase_without_a_gate_fails_instead_of_passing(monkeypatch):
    monkeypatch.setattr(verify, "PHASES", {0: []})
    results = verify.phase_checks(2)
    assert [check.status for check in results] == [verify.FAIL, verify.FAIL]


def test_hardware_facts_register_has_nothing_marked_verified():
    assert verify.check_hardware_facts().status == verify.PASS


def test_every_script_named_in_the_readme_exists():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    import re

    for name in set(re.findall(r"scripts/[a-z_]+\.py", readme)):
        assert (ROOT / name).exists(), f"README mentions missing {name}"
    assert Path(ROOT / "PROMPT.md").exists()
