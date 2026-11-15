"""Shared pytest fixtures. Every test runs against a throwaway instance folder."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
for entry in (str(ROOT), str(SCRIPTS)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from app import bootstrap, create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Astronaut  # noqa: E402
from config import load_config  # noqa: E402

CREW = ("AST-1001:Cmdr. Sara Whitman:Commander:Falcon,"
        "AST-1002:Dr. Leo Marquez:Flight Engineer:Atlas,"
        "AST-1003:Aisha Rahman:Mission Specialist:Nova")
SURGEON = "FS-9001:Dr. Grace Okafor:Flight Surgeon:Hippocrates"


def load_script(name: str):
    """Import a file from ``scripts/`` under a private module name."""
    spec = importlib.util.spec_from_file_location(f"astro_script_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_values(instance: Path, **extra: str) -> dict[str, str]:
    values = {
        "ASTROVITAL_INSTANCE_DIR": str(instance),
        "FLASK_SECRET_KEY": "test-secret-key-0123456789",
        "REGISTERED_ASTRONAUTS": CREW,
        "FLIGHT_SURGEON_IDS": SURGEON,
        "DEVICE_TOKEN": "test-device-token-0123456789",
        "OPENHOME_BRIDGE_TOKEN": "test-bridge-token-0123456789",
        "MISSION_DAY_OVERRIDE": "160",
        "OPENHOME_MOCK": "true",
        "SEED_ON_FIRST_RUN": "false",
        "BIND_HOST": "127.0.0.1",
    }
    values.update(extra)
    return values


def build_app(values: dict[str, str], *, seed: bool = False, rate_limits: bool = False):
    app = create_app(load_config(values), testing=True, rate_limits=rate_limits)
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        db.create_all()
        bootstrap.prepare_data(app, seed=seed)
    return app


@pytest.fixture
def env_values(tmp_path) -> dict[str, str]:
    """A complete, valid environment that never touches the real .env."""
    return make_values(tmp_path / "instance")


@pytest.fixture
def config(env_values):
    return load_config(env_values)


@pytest.fixture
def app(env_values):
    return build_app(env_values)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(scope="module")
def seeded_app(tmp_path_factory):
    """One app with 30 days of demo history, shared by the read-only tests of a module."""
    return build_app(make_values(tmp_path_factory.mktemp("seeded")), seed=True)


def login(client, astro_id: str = "AST-1001"):
    response = client.post("/login", data={"astro_id": astro_id})
    assert response.status_code == 302, response.data
    return response


def crew_id(app, astro_id: str) -> int:
    with app.app_context():
        return Astronaut.query.filter_by(astro_id=astro_id).one().id
