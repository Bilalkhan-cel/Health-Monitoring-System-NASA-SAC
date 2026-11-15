"""BUILD-TIME ONLY: download the raw 3D inputs that ``scripts/vendor_build/build.mjs`` optimizes.

    python scripts/fetch_build_sources.py

Outputs go to ``build_sources/`` (git-ignored). The optimized results under
``app/static/models`` and ``app/static/textures`` are committed, so end users never
run this. Sources (all public):

* NASA 3D Resources, International Space Station (ISS) (D) (IGOAL) glb (~96 MB).
  NASA media is generally not copyrighted; no NASA logo or endorsement is implied.
* three.js r186 example textures (Earth day, night, clouds, specular; derived from NASA
  imagery) and the Xbot humanoid (Mixamo character shipped with the three.js examples).
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build_sources"
THREE = "https://raw.githubusercontent.com/mrdoob/three.js/r186/examples"
NASA = "https://raw.githubusercontent.com/nasa/NASA-3D-Resources/master/3D%20Models/"
ISS_DIR = quote("International Space Station (ISS) (D) (IGOAL)")
ISS_FILE = quote("International Space Station (ISS).glb")

SOURCES = (
    ("iss/iss.glb", f"{NASA}{ISS_DIR}/{ISS_FILE}"),
    ("body/Xbot.glb", f"{THREE}/models/gltf/Xbot.glb"),
    ("earth/earth-day.jpg", f"{THREE}/textures/planets/earth_day_4096.jpg"),
    ("earth/earth-night.jpg", f"{THREE}/textures/planets/earth_night_4096.jpg"),
    ("earth/earth-bump-roughness-clouds.jpg", f"{THREE}/textures/planets/earth_bump_roughness_clouds_4096.jpg"),
    ("earth/earth-specular.jpg", f"{THREE}/textures/planets/earth_specular_2048.jpg"),
)


def fetch(target: Path, url: str) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "astrovital-build/1.0"})
    digest = hashlib.sha256()
    part = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(request, timeout=300) as response, part.open("wb") as stream:  # noqa: S310
        for block in iter(lambda: response.read(1 << 20), b""):
            stream.write(block)
            digest.update(block)
    part.replace(target)
    return digest.hexdigest()


def main() -> int:
    failed = 0
    for relative, url in SOURCES:
        target = OUT / relative
        if target.exists() and target.stat().st_size > 0:
            sys.stdout.write(f"  present  {relative}\n")
            continue
        try:
            sha = fetch(target, url)
            sys.stdout.write(f"  fetched  {relative}  {target.stat().st_size / 1e6:.1f} MB  sha256 {sha[:16]}\n")
        except OSError as error:
            failed += 1
            sys.stdout.write(f"  FAILED   {relative}: {error}\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
