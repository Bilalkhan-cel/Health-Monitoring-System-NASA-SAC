"""Fetch any vendored front-end asset that is missing (fonts today; libraries later).

Every file is listed in ``scripts/assets_manifest.json`` with its URL, destination
and SHA-256. A download is written only when the checksum matches, so a broken
or tampered file never reaches ``app/static``. Standard library only.

Usage:
    python scripts/fetch_assets.py            fetch what is missing
    python scripts/fetch_assets.py --check    report only, no network (exit 1 if incomplete)
    python scripts/fetch_assets.py --force    re-download everything
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = Path(__file__).resolve().parent / "assets_manifest.json"
ALLOWED_HOSTS = {"cdn.jsdelivr.net", "raw.githubusercontent.com", "storage.googleapis.com"}
ALLOWED_ROOTS = ("app/static/",)
TIMEOUT_S = 30
USER_AGENT = "astrovital-setup/1.0"


@dataclass(frozen=True)
class Asset:
    """One vendored file."""

    id: str
    url: str
    dest: str
    sha256: str
    bytes: int
    license: str = ""

    @property
    def path(self) -> Path:
        return ROOT / self.dest


@dataclass(frozen=True)
class Result:
    asset: Asset
    state: str  # present | fetched | failed
    detail: str = ""


def validate_asset(asset: Asset) -> None:
    """Reject manifest entries that could write outside the static folder."""
    parsed = urlparse(asset.url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"{asset.id}: URL must be https on an allowed host")
    if not asset.dest.startswith(ALLOWED_ROOTS) or ".." in Path(asset.dest).parts:
        raise ValueError(f"{asset.id}: destination must stay inside {ALLOWED_ROOTS[0]}")
    if len(asset.sha256) != 64 or any(char not in "0123456789abcdef" for char in asset.sha256):
        raise ValueError(f"{asset.id}: sha256 must be 64 lowercase hex characters")


def load_manifest(path: Path = MANIFEST) -> list[Asset]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assets = [Asset(**entry) for entry in data["assets"]]
    for asset in assets:
        validate_asset(asset)
    return assets


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def is_current(asset: Asset) -> bool:
    """True when the file exists and matches the manifest checksum."""
    return asset.path.is_file() and sha256_file(asset.path) == asset.sha256


def download(asset: Asset) -> bytes:
    request = urllib.request.Request(asset.url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310 (https + allow-list checked)
        return response.read()


def write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".part")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def fetch(assets: list[Asset], *, force: bool = False, downloader=download) -> list[Result]:
    """Fetch missing (or all, with ``force``) assets. Never raises on a failed download."""
    results: list[Result] = []
    for asset in assets:
        if not force and is_current(asset):
            results.append(Result(asset, "present"))
            continue
        try:
            payload = downloader(asset)
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            results.append(Result(asset, "failed", f"download failed: {error}"))
            continue
        if sha256_bytes(payload) != asset.sha256:
            results.append(Result(asset, "failed", "checksum mismatch, file not saved"))
            continue
        write_atomic(asset.path, payload)
        results.append(Result(asset, "fetched"))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch missing vendored assets.")
    parser.add_argument("--check", action="store_true", help="report only; exit 1 if anything is missing")
    parser.add_argument("--force", action="store_true", help="download every asset again")
    parser.add_argument("--strict", action="store_true", help="exit 1 if any download fails")
    args = parser.parse_args(argv)

    assets = load_manifest()
    if args.check:
        missing = [asset for asset in assets if not is_current(asset)]
        for asset in missing:
            sys.stdout.write(f"  missing  {asset.dest}\n")
        sys.stdout.write(f"Assets: {len(assets) - len(missing)}/{len(assets)} present\n")
        return 1 if missing else 0

    results = fetch(assets, force=args.force)
    failed = [result for result in results if result.state == "failed"]
    for result in results:
        if result.state != "present":
            sys.stdout.write(f"  {result.state:8} {result.asset.dest} {result.detail}\n")
    fetched = sum(result.state == "fetched" for result in results)
    present = sum(result.state == "present" for result in results)
    sys.stdout.write(f"Assets: {present} already present, {fetched} fetched, {len(failed)} failed\n")
    if failed:
        sys.stdout.write("Some assets are missing. The app still starts and uses its fallbacks "
                         "(system fonts). Re-run this script when you are online.\n")
    return 1 if (failed and args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
