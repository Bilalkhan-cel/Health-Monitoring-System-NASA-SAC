"""Local speech-to-text with faster-whisper (CTranslate2, int8 on CPU).

The model loads once from ``ml_models/whisper/<size>`` (``local_files_only``) behind a
lock. Transcription runs in background threads, one audio chunk at a time.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)
_lock = threading.Lock()
_model = None
_failed = False


def available(model_dir: Path) -> bool:
    return (model_dir / "model.bin").is_file()


def _load(model_dir: Path, compute_type: str):
    global _model, _failed
    with _lock:
        if _model is not None or _failed:
            return _model
        try:
            from faster_whisper import WhisperModel

            _model = WhisperModel(str(model_dir), device="cpu", compute_type=compute_type, local_files_only=True)
        except Exception:  # noqa: BLE001 (missing package or model: the check-in offers text instead)
            log.warning("Whisper model could not be loaded from %s", model_dir)
            _failed = True
        return _model


def _read_wav(path: Path):
    """Decode our own 16 kHz mono 16-bit WAV chunks without PyAV/ffmpeg (None if the format differs)."""
    import wave

    import numpy as np

    try:
        with wave.open(str(path), "rb") as handle:
            if handle.getframerate() != 16000 or handle.getnchannels() != 1 or handle.getsampwidth() != 2:
                return None
            frames = handle.readframes(handle.getnframes())
    except (wave.Error, OSError, EOFError):
        return None
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe(path: Path, model_dir: Path, compute_type: str = "int8") -> str | None:
    """Transcribe one WAV chunk (English). Returns None when speech-to-text is unavailable."""
    model = _load(model_dir, compute_type)
    if model is None:
        return None
    audio = _read_wav(path)
    segments, _info = model.transcribe(audio if audio is not None else str(path), language="en", vad_filter=True,
                                       beam_size=1)
    return " ".join(segment.text.strip() for segment in segments).strip()
