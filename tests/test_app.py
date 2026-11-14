"""App factory, public routes, error pages and start-up."""

from __future__ import annotations

import html
import logging
import re

from sqlalchemy import text

from app import SecretRedactor, bootstrap, get_config
from app.extensions import db
from config import FONT_FILES


def test_healthz_is_public_and_carries_no_crew_data(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True and body["server"] == "astrovital"
    assert body["server_time"].endswith("Z")
    assert set(body) == {"ok", "server", "version", "server_time"}


def test_landing_page_renders_with_the_disclaimer(client):
    response = client.get("/")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Beyond Earth." in page and "always in health." in page
    assert "Prototype for educational purposes. Not a certified medical device." in page
    assert 'name="csrf-token"' in page
    assert "<script" not in page, "phase 0 ships no JavaScript"


def test_landing_page_has_no_link_to_a_page_that_does_not_exist(client, app):
    page = client.get("/").get_data(as_text=True)
    known = {rule.rule for rule in app.url_map.iter_rules()}
    for href in re.findall(r'href="(/[^"]*)"', page):
        if href.startswith("/static/"):
            assert client.get(href).status_code == 200, href
        else:
            assert href in known, f"dead link {href}"


def test_unknown_page_gets_a_friendly_404(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    page = html.unescape(response.get_data(as_text=True))
    assert "That page isn't part of this mission." in page
    assert "Traceback" not in page


def test_unknown_api_path_gets_json(client):
    response = client.get("/api/no-such-thing")
    assert response.status_code == 404
    assert response.get_json() == {"ok": False, "error": "page_not_found"}


def test_unexpected_error_shows_a_safe_page(app):
    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail")

    response = app.test_client().get("/boom")
    assert response.status_code == 500
    page = response.get_data(as_text=True)
    assert "secret internal detail" not in page and "Traceback" not in page
    assert "Something went wrong" in page


def test_theme_and_fonts_are_served_locally(client):
    theme = client.get("/static/css/theme.css")
    assert theme.status_code == 200
    css = theme.get_data(as_text=True)
    for token in ("--bg:", "--good:", "--okay:", "--watch:", "--alert:", "--glow:", "--radius-pill:"):
        assert token in css
    assert "prefers-reduced-motion" in css
    for name in FONT_FILES:
        assert name in css
        response = client.get(f"/static/vendor/fonts/{name}")
        assert response.status_code == 200 and response.data[:4] == b"wOF2", name


def test_sqlite_runs_in_wal_mode_with_foreign_keys(app):
    with app.app_context():
        assert db.session.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert db.session.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert db.session.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_bootstrap_creates_the_database_and_sweeps_uploads(env_values):
    from app import create_app
    from config import load_config

    app = create_app(load_config(env_values), testing=True)
    config = get_config(app)
    config.uploads_dir.mkdir(parents=True, exist_ok=True)
    (config.uploads_dir / "leftover.wav").write_bytes(b"RIFF")
    (config.uploads_dir / ".gitkeep").write_text("", encoding="utf-8")

    report = bootstrap.run(app)

    assert report.db_ready is True
    assert report.uploads_swept == 1
    assert report.crew_loaded == 3 and report.sensor_mode == "device"
    assert (config.instance_dir / "astrovital.db").exists()
    assert [path.name for path in config.uploads_dir.iterdir()] == [".gitkeep"]


def test_bootstrap_reports_an_unusable_database(env_values, tmp_path):
    from app import create_app
    from config import load_config

    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x", encoding="utf-8")
    values = {**env_values, "DATABASE_URL": f"sqlite:///{(blocker / 'db.sqlite').as_posix()}"}
    broken_app = create_app(load_config(values), testing=True)
    assert bootstrap.ensure_database(broken_app) is False


def test_secrets_are_redacted_from_log_lines():
    redactor = SecretRedactor(("super-secret-token",))
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "connecting to wss://host/%s/agent",
                               ("super-secret-token",), None)
    assert redactor.filter(record) is True
    assert record.getMessage() == "connecting to wss://host/***/agent"
