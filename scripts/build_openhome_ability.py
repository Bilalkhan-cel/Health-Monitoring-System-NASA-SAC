"""Build the Dr. NOVA OpenHome Ability and print the setup steps.

    python scripts/build_openhome_ability.py            render + rotate token + validate + zip
    python scripts/build_openhome_ability.py --push     also run `openhome push` if the CLI is installed
    python scripts/build_openhome_ability.py --persona  print the persona text and exit

Each build writes a NEW random OPENHOME_BRIDGE_TOKEN into .env and into the rendered
main.py, so every upload rotates the shared secret. Restart `python run.py` afterwards.
Output: build/openhome_ability/ (git-ignored) and build/astrovital_health_context.zip.
"""

from __future__ import annotations

import argparse
import re
import secrets
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "openhome_ability"
OUT_DIR = ROOT / "build" / "openhome_ability"
ZIP_PATH = ROOT / "build" / "astrovital_health_context.zip"
PERSONA = ROOT / "config" / "dr_nova_persona.md"
ENV = ROOT / ".env"

# Mirrors openhome-dev/abilities validate_ability.py (checked 2026-11).
BLOCKED_PATTERNS = [
    (r"\bprint\s*\(", "print() is not allowed; use editor_logging_handler"),
    (r"\basyncio\.sleep\s*\(", "use session_tasks.sleep()"),
    (r"\basyncio\.create_task\s*\(", "use session_tasks.create()"),
    (r"\bexec\s*\(", "exec() is not allowed"),
    (r"\beval\s*\(", "eval() is not allowed"),
    (r"\bpickle\.", "pickle is not allowed"),
    (r"\bopen\s*\(", "raw open() is not allowed"),
    (r"\bassert\s+", "assert is not allowed"),
]
REQUIRED_PATTERNS = [
    (r"resume_normal_flow\s*\(", "resume_normal_flow() must be called"),
    (r"class\s+\w+.*MatchingCapability", "class must extend MatchingCapability"),
    (r"def\s+call\s*\(", "must have call()"),
    (r"#\s?\{\{register[_ ]capability\}\}", "missing the register capability tag"),
]
TRIGGERS = ["doctor nova", "dr nova", "check my health", "how am i doing", "review my vitals", "health report",
            "log my sleep", "i feel", "my heart", "my head hurts"]
PERSONA_INSTRUCTION = ("At the start of every conversation, run the AstroVital Health Context ability before "
                       "answering any health question.")


def read_env() -> dict[str, str]:
    values = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
            if match:
                value = match.group(2).strip()
                values[match.group(1)] = "" if value.startswith("#") else re.split(r"\s+#", value, maxsplit=1)[0].strip()
    return values


def set_env(key: str, value: str) -> None:
    lines = ENV.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[index] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render(public_url: str, token: str, persona: str) -> str:
    template = (SOURCE / "main.py.tmpl").read_text(encoding="utf-8")
    safe_persona = persona.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return (template.replace("{{PUBLIC_BASE_URL}}", public_url.rstrip("/"))
            .replace("{{OPENHOME_BRIDGE_TOKEN}}", token).replace("{{DR_NOVA_PERSONA}}", safe_persona))


def validate(code: str) -> list[str]:
    problems = [message for pattern, message in BLOCKED_PATTERNS if re.search(pattern, code)]
    problems += [message for pattern, message in REQUIRED_PATTERNS if not re.search(pattern, code)]
    try:
        compile(code, "main.py", "exec")
    except SyntaxError as error:
        problems.append(f"syntax error: {error}")
    return problems


def build(public_url: str, token: str) -> list[str]:
    persona = PERSONA.read_text(encoding="utf-8").strip()
    code = render(public_url, token, persona)
    problems = validate(code)
    if problems:
        return problems
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)
    (OUT_DIR / "main.py").write_text(code, encoding="utf-8")
    (OUT_DIR / "__init__.py").write_text("", encoding="utf-8")
    shutil.copy(SOURCE / "README.md", OUT_DIR / "README.md")
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("main.py", "__init__.py", "README.md"):
            archive.write(OUT_DIR / name, name)
    return []


def print_steps(public_url: str, agent_id: str) -> None:
    write = sys.stdout.write
    write("\nNext steps in OpenHome (app.openhome.com):\n")
    write("  1. Create the agent: Personalities -> New, name it \"Dr. NOVA\", pick a calm, warm voice.\n")
    write("     Paste the persona (python scripts/build_openhome_ability.py --persona), and add this line:\n")
    write(f"       {PERSONA_INSTRUCTION}\n")
    write("     Copy the agent id into .env as OPENHOME_AGENT_ID, and your API key (Settings -> API Keys)\n")
    write("     as OPENHOME_API_KEY.\n")
    write(f"  2. Upload {ZIP_PATH.relative_to(ROOT)}: Abilities -> Add Custom Ability (or use --push).\n")
    write(f"     Trigger words: {', '.join(TRIGGERS)}\n")
    write("     Install it into the Dr. NOVA agent.\n")
    write("  3. Make Flask reachable for the Ability: cloudflared tunnel --url http://localhost:5000\n")
    write("     then set PUBLIC_BASE_URL in .env to the https URL it prints, and run this script again.\n")
    write("     Only /api/openhome/* and /healthz are reachable through the tunnel.\n")
    write("  4. Restart python run.py (the new bridge token is in .env).\n")
    if "localhost" in public_url or "127.0.0.1" in public_url:
        write("\n  Note: PUBLIC_BASE_URL is still local, so the cloud Ability cannot reach it yet (step 3).\n")
    if not agent_id:
        write("  Note: OPENHOME_AGENT_ID is empty in .env.\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Dr. NOVA OpenHome Ability.")
    parser.add_argument("--push", action="store_true", help="push with the openhome CLI when it is installed")
    parser.add_argument("--persona", action="store_true", help="print the persona and exit")
    parser.add_argument("--no-rotate", action="store_true", help="keep the current bridge token (tests)")
    args = parser.parse_args(argv)
    if args.persona:
        sys.stdout.write(PERSONA.read_text(encoding="utf-8") + f"\n{PERSONA_INSTRUCTION}\n")
        return 0
    if not ENV.exists():
        sys.stdout.write("No .env yet. Run python scripts/setup.py first.\n")
        return 1
    env = read_env()
    token = env.get("OPENHOME_BRIDGE_TOKEN") if args.no_rotate else ""
    if not token:
        token = secrets.token_urlsafe(32)
        set_env("OPENHOME_BRIDGE_TOKEN", token)
    public_url = env.get("PUBLIC_BASE_URL") or "http://localhost:5000"
    problems = build(public_url, token)
    if problems:
        sys.stdout.write("The Ability failed validation:\n" + "".join(f"  - {p}\n" for p in problems))
        return 1
    sys.stdout.write(f"Built {ZIP_PATH.relative_to(ROOT)} (bridge token rotated and saved to .env).\n")
    if args.push:
        cli = shutil.which("openhome")
        if cli is None:
            sys.stdout.write("The openhome CLI is not installed (pip install openhome-client). Upload the zip by hand.\n")
        else:
            agent = env.get("OPENHOME_AGENT_ID", "")
            command = [cli, "push", str(OUT_DIR)] + (["--agent", agent] if agent else [])
            code = subprocess.call(command)
            sys.stdout.write("Pushed.\n" if code == 0 else "openhome push failed; upload the zip by hand.\n")
    print_steps(public_url, env.get("OPENHOME_AGENT_ID", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
