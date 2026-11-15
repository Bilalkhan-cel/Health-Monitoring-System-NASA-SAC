"""Download the local ML models into ``ml_models/`` and check that they load.

Models (all run on this computer, nothing is sent to a cloud service):
    whisper    Systran/faster-whisper-<size>                      speech to text
    sentiment  cardiffnlp/twitter-roberta-base-sentiment-latest   positive / neutral / negative
    emotion    j-hartmann/emotion-english-distilroberta-base      seven emotions
    pose       usyd-community/vitpose-base-simple                 only with --with-vitpose

Usage:
    python scripts/download_models.py                 download what is missing, then verify
    python scripts/download_models.py --check         report only, no network
    python scripts/download_models.py --with-vitpose  also fetch the optional pose model

A failed download is reported and skipped: the app still starts and uses its
fallbacks (text check-in, self-rating).
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap_env import ROOT, ensure_environment  # noqa: E402

ensure_environment()
sys.path.insert(0, str(ROOT))

from config import Config, hf_model_found, load_config, whisper_model_found  # noqa: E402

HF_WEIGHTS = ["config.json", "*.txt", "*.json", "model.safetensors", "pytorch_model.bin"]
WHISPER_FILES = ["config.json", "model.bin", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"]


@dataclass(frozen=True)
class ModelSpec:
    """One model to download."""

    key: str
    repo_id: str
    target: Path
    patterns: list[str]
    kind: str  # whisper | classifier | pose


@dataclass(frozen=True)
class Outcome:
    spec: ModelSpec
    state: str  # present | downloaded | failed
    detail: str = ""
    seconds: float = 0.0


def model_specs(config: Config, *, with_vitpose: bool = False) -> list[ModelSpec]:
    specs = [
        ModelSpec("whisper", f"Systran/faster-whisper-{config.whisper_model_size}",
                  config.whisper_model_path / config.whisper_model_size, WHISPER_FILES, "whisper"),
        ModelSpec("sentiment", "cardiffnlp/twitter-roberta-base-sentiment-latest",
                  config.nlp_sentiment_path, HF_WEIGHTS, "classifier"),
        ModelSpec("emotion", "j-hartmann/emotion-english-distilroberta-base",
                  config.nlp_emotion_path, HF_WEIGHTS, "classifier"),
    ]
    if with_vitpose:
        specs.append(ModelSpec("pose", "usyd-community/vitpose-base-simple",
                               config.pose_model_path, HF_WEIGHTS, "pose"))
    return specs


def is_present(spec: ModelSpec, config: Config) -> bool:
    if spec.kind == "whisper":
        return whisper_model_found(config)
    has_weights = any((spec.target / name).is_file() for name in ("model.safetensors", "pytorch_model.bin"))
    return hf_model_found(spec.target) and has_weights


def folder_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) / 1_048_576


def _prune_duplicate_weights(spec: ModelSpec) -> None:
    """Keep one weights file when a repository ships both formats."""
    safetensors, legacy = spec.target / "model.safetensors", spec.target / "pytorch_model.bin"
    if safetensors.is_file() and legacy.is_file():
        legacy.unlink()


def download_one(spec: ModelSpec, config: Config) -> Outcome:
    """Download one model. Returns a failed outcome instead of raising."""
    started = time.monotonic()
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        return Outcome(spec, "failed", "huggingface_hub is not installed (run python scripts/setup.py)")
    patterns = list(spec.patterns)
    if spec.kind != "whisper":
        # Prefer safetensors; fall back to the legacy file only when it is all there is.
        try:
            from huggingface_hub import list_repo_files

            if "model.safetensors" in list_repo_files(spec.repo_id):
                patterns.remove("pytorch_model.bin")
        except Exception:  # noqa: BLE001 (network or hub error: download both, prune afterwards)
            pass
    try:
        snapshot_download(repo_id=spec.repo_id, local_dir=str(spec.target), allow_patterns=patterns)
    except Exception as error:  # noqa: BLE001 (any hub/network failure degrades gracefully)
        return Outcome(spec, "failed", f"{type(error).__name__}: {error}".splitlines()[0][:200])
    if spec.kind != "whisper":
        _prune_duplicate_weights(spec)
    if not is_present(spec, config):
        return Outcome(spec, "failed", "download finished but expected files are missing")
    return Outcome(spec, "downloaded", seconds=time.monotonic() - started)


def verify_one(spec: ModelSpec, config: Config) -> tuple[bool, str]:
    """Load a model from disk only (``local_files_only``) to prove it works offline."""
    try:
        if spec.kind == "whisper":
            from faster_whisper import WhisperModel

            WhisperModel(str(spec.target), device="cpu", compute_type=config.whisper_compute_type,
                         local_files_only=True)
            return True, "loads"
        if spec.kind == "classifier":
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            from transformers.utils import logging as hf_logging

            hf_logging.set_verbosity_error()  # the unused-pooler load report is expected noise
            AutoTokenizer.from_pretrained(str(spec.target), local_files_only=True)
            model = AutoModelForSequenceClassification.from_pretrained(str(spec.target), local_files_only=True)
            labels = ", ".join(str(label).lower() for label in model.config.id2label.values())
            return True, f"loads; labels: {labels}"
        from transformers import VitPoseForPoseEstimation

        VitPoseForPoseEstimation.from_pretrained(str(spec.target), local_files_only=True)
        return True, "loads"
    except ImportError as error:
        return False, f"cannot verify, missing package: {error.name}"
    except Exception as error:  # noqa: BLE001 (report any load failure in plain words)
        return False, f"{type(error).__name__}: {error}".splitlines()[0][:200]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download and verify the local ML models.")
    parser.add_argument("--check", action="store_true", help="report only; exit 1 if a model is missing")
    parser.add_argument("--with-vitpose", action="store_true", help="also download the optional ViTPose model")
    parser.add_argument("--no-verify", action="store_true", help="skip the load test")
    parser.add_argument("--strict", action="store_true", help="exit 1 if any model fails")
    args = parser.parse_args(argv)

    config = load_config()
    specs = model_specs(config, with_vitpose=args.with_vitpose)
    write = sys.stdout.write

    if args.check:
        missing = [spec for spec in specs if not is_present(spec, config)]
        for spec in specs:
            state = "missing" if spec in missing else f"present ({folder_size_mb(spec.target):.0f} MB)"
            write(f"  {spec.key:10} {state}\n")
        return 1 if missing else 0

    problems = 0
    for spec in specs:
        if is_present(spec, config):
            outcome = Outcome(spec, "present")
        else:
            write(f"  {spec.key:10} downloading {spec.repo_id} ...\n")
            sys.stdout.flush()
            outcome = download_one(spec, config)
        if outcome.state == "failed":
            problems += 1
            write(f"  {spec.key:10} FAILED: {outcome.detail}\n")
            continue
        line = f"  {spec.key:10} {outcome.state}, {folder_size_mb(spec.target):.0f} MB"
        if outcome.seconds:
            line += f", {outcome.seconds:.0f} s"
        if not args.no_verify:
            ok, detail = verify_one(spec, config)
            line += f", {detail}" if ok else f", VERIFY FAILED: {detail}"
            problems += 0 if ok else 1
        write(line + "\n")

    if problems:
        write("Some models are not ready. The app still starts: voice check-in falls back to text "
              "and mood uses the self-rating. Re-run this script when you are online.\n")
    return 1 if (problems and args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
