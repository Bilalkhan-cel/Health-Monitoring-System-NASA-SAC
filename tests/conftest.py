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

from app import create_app  # noqa: E402
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


@pytest.fixture
def env_values(tmp_path) -> dict[str, str]:
    """A complete, valid environment that never touches the real .env."""
    return {
        "ASTROVITAL_INSTANCE_DIR": str(tmp_path / "instance"),
        "FLASK_SECRET_KEY": "test-secret-key-0123456789",
        "REGISTERED_ASTRONAUTS": CREW,
        "FLIGHT_SURGEON_IDS": SURGEON,
        "DEVICE_TOKEN": "test-device-token-0123456789",
        "OPENHOME_BRIDGE_TOKEN": "test-bridge-token-0123456789",
        "MISSION_DAY_OVERRIDE": "160",
    }


@pytest.fixture
def config(env_values):
    return load_config(env_values)


@pytest.fixture
def app(config):
    return create_app(config, testing=True)


@pytest.fixture
def client(app):
    return app.test_client()
