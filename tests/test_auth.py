"""Astro ID login, per-astronaut scoping, CSRF and rate limits."""

from __future__ import annotations

import html

from app.extensions import db
from app.models import Astronaut, AuditLog, Measurement
from app.services import measurements
from conftest import build_app, crew_id, login, make_values


def test_only_registered_ids_log_in(client):
    page = client.post("/login", data={"astro_id": "AST-9999"})
    assert page.status_code == 200 and b"is-wrong" in page.data
    assert "That ID isn't on this mission's crew list." in html.unescape(page.get_data(as_text=True))
    assert client.get("/dashboard").status_code == 302


def test_ids_are_case_and_space_insensitive(client):
    response = client.post("/login", data={"astro_id": "  ast-1001 "})
    assert response.status_code == 302 and response.headers["Location"].endswith("/dashboard")
    assert client.get("/dashboard").status_code == 200


def test_an_id_removed_from_env_can_no_longer_log_in(app, env_values):
    narrowed = build_app({**env_values, "REGISTERED_ASTRONAUTS": "AST-1002:Dr. Leo Marquez:Flight Engineer:Atlas"})
    with narrowed.app_context():
        assert Astronaut.query.filter_by(astro_id="AST-1001").first() is not None  # row kept for history
    assert narrowed.test_client().post("/login", data={"astro_id": "AST-1001"}).status_code == 200


def test_session_ends_if_the_id_is_removed(app, env_values, tmp_path):
    client = app.test_client()
    login(client)
    app.extensions["astrovital_config"] = build_app(
        {**env_values, "REGISTERED_ASTRONAUTS": "AST-1002:Dr. Leo Marquez:Flight Engineer:Atlas"}
    ).extensions["astrovital_config"]
    assert client.get("/dashboard").status_code == 302


def test_logout_clears_the_session_and_is_audited(app, client):
    login(client)
    assert client.post("/logout").status_code == 302
    assert client.get("/dashboard").status_code == 302
    with app.app_context():
        actions = [row.action for row in AuditLog.query.order_by(AuditLog.id)]
    assert actions == ["login", "logout"]


def test_logged_in_user_skips_the_login_page(client):
    login(client)
    assert client.get("/login").headers["Location"].endswith("/dashboard")


def test_next_redirect_is_same_site_only(client):
    ok = client.post("/login", data={"astro_id": "AST-1001", "next": "/api/summary"})
    assert ok.headers["Location"].endswith("/api/summary")
    client.post("/logout")
    for target in ("https://evil.example/", "//evil.example/x", "javascript:alert(1)"):
        response = client.post("/login", data={"astro_id": "AST-1001", "next": target})
        assert response.headers["Location"].endswith("/dashboard"), target
        client.post("/logout")


def test_anonymous_api_calls_get_401_json(client):
    response = client.get("/api/summary")
    assert response.status_code == 401 and response.get_json()["error"] == "login_required"


def test_surgeon_lands_away_from_astronaut_pages(client):
    login(client, "FS-9001")
    assert client.get("/api/summary").status_code == 403


def test_each_astronaut_sees_only_their_own_data(app, client):
    sara, leo = crew_id(app, "AST-1001"), crew_id(app, "AST-1002")
    with app.app_context():
        measurements.record(leo, "heart_rate", 150, source="manual", context="resting")
        measurements.record(sara, "heart_rate", 70, source="manual", context="resting")
    login(client, "AST-1001")
    values = {item["key"]: item["value"] for item in client.get("/api/summary").get_json()["metrics"]}
    assert values["heart_rate"] == "70"
    client.post("/logout")
    login(client, "AST-1002")
    values = {item["key"]: item["value"] for item in client.get("/api/summary").get_json()["metrics"]}
    assert values["heart_rate"] == "150"
    with app.app_context():
        assert Measurement.query.filter_by(source="manual").count() == 2


def test_csrf_is_required_on_posts(env_values):
    app = build_app(env_values)
    app.config["WTF_CSRF_ENABLED"] = True
    client = app.test_client()
    assert client.post("/login", data={"astro_id": "AST-1001"}).status_code == 400
    page = client.get("/login").get_data(as_text=True)
    token = page.split('name="csrf_token" value="')[1].split('"')[0]
    assert client.post("/login", data={"astro_id": "AST-1001", "csrf_token": token}).status_code == 302
    api = client.post("/api/tasks/hydration/done", json={})
    assert api.status_code == 400 and "message" in api.get_json()
    stale = client.post("/api/tasks/hydration/done", json={}, headers={"X-CSRFToken": token})
    assert stale.status_code == 400, "logging in starts a new session, so the old token is void"
    page = client.get("/dashboard").get_data(as_text=True)
    fresh = page.split('name="csrf-token" content="')[1].split('"')[0]
    ok = client.post("/api/tasks/hydration/done", json={}, headers={"X-CSRFToken": fresh})
    assert ok.status_code == 200


def test_login_is_rate_limited_per_ip_and_per_id(tmp_path):
    app = build_app(make_values(tmp_path / "rl"), rate_limits=True)
    client = app.test_client()
    codes = [client.post("/login", data={"astro_id": f"AST-{9000 + i}"}).status_code for i in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429
    other_ip = app.test_client()
    codes = [other_ip.post("/login", data={"astro_id": "AST-9999"},
                           environ_base={"REMOTE_ADDR": f"10.0.0.{i}"}).status_code for i in range(6)]
    assert codes[5] == 429, "the same ID from many addresses is limited too"


def test_session_cookie_flags(client):
    response = client.post("/login", data={"astro_id": "AST-1001"})
    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie
    with client.application.app_context():
        assert db.session.get(Astronaut, crew_id(client.application, "AST-1001")).last_active_at is not None
