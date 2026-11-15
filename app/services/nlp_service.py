"""Local text analysis for the voice check-in and Dr. NOVA (Section 12).

* safety screen: a hard lexicon rule (config/safety_lexicon.yaml), always first;
* sentiment per sentence (cardiffnlp/twitter-roberta-base-sentiment-latest) and emotions
  (j-hartmann/emotion-english-distilroberta-base), loaded once from ml_models/ with
  ``local_files_only`` behind a lock; a small word list stands in when they are missing;
* theme flags from a lexicon; the Mental Wellbeing Score.

English only. Speech sentiment is not a psychiatric diagnosis, and nothing here says so.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from config import BASE_DIR

log = logging.getLogger(__name__)

EMOTIONS = ("joy", "sadness", "anger", "fear", "surprise", "disgust", "neutral")
_lock = threading.Lock()
_pipelines: dict[str, object] = {}
_failed: set[str] = set()


@lru_cache(maxsize=1)
def mental_config() -> dict:
    return yaml.safe_load((BASE_DIR / "config" / "mental.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def safety_config() -> dict:
    return yaml.safe_load((BASE_DIR / "config" / "safety_lexicon.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _crisis_patterns() -> tuple[re.Pattern, ...]:
    return tuple(re.compile(pattern) for pattern in safety_config()["crisis"])


def normalise(text: str) -> str:
    text = text.lower().replace("’", "'").replace("'", "")
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def safety_screen(text: str) -> bool:
    """True when the text contains a crisis phrase. Never depends on a model."""
    clean = normalise(text or "")
    return any(pattern.search(clean) for pattern in _crisis_patterns())


def support_message() -> str:
    return " ".join(safety_config()["support_message"].split())


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", (text or "").strip())
    return [part.strip() for part in parts if len(part.strip()) >= 3]


def _pipeline(kind: str, path: Path):
    """Load a text-classification pipeline once, from disk only."""
    with _lock:
        if kind in _pipelines:
            return _pipelines[kind]
        if kind in _failed or not (path / "config.json").is_file():
            return None
        try:
            from transformers import pipeline
            from transformers.utils import logging as hf_logging

            hf_logging.set_verbosity_error()
            _pipelines[kind] = pipeline("text-classification", model=str(path), tokenizer=str(path), top_k=None,
                                        device=-1, local_files_only=True)
        except Exception:  # noqa: BLE001 (any load failure falls back to the word lists)
            log.warning("Could not load the %s model; using the word-list fallback", kind)
            _failed.add(kind)
            return None
        return _pipelines[kind]


def models_available(sentiment_path: Path, emotion_path: Path) -> bool:
    return (sentiment_path / "config.json").is_file() and (emotion_path / "config.json").is_file()


def _words(text: str, words: list[str]) -> int:
    clean = f" {normalise(text)} "
    return sum(clean.count(f" {word} ") for word in words)


def _fallback_sentiment(text: str) -> dict[str, float]:
    config = mental_config()
    pos, neg = _words(text, config["positive_words"]), _words(text, config["negative_words"])
    if pos == neg:
        return {"positive": 0.2, "neutral": 0.6, "negative": 0.2}
    total = pos + neg
    return {"positive": 0.8 * pos / total, "neutral": 0.2, "negative": 0.8 * neg / total}


@dataclass
class Analysis:
    segments: list[dict] = field(default_factory=list)
    pos_ratio: float = 0.0
    neg_ratio: float = 0.0
    emotions: dict[str, float] = field(default_factory=dict)
    themes: list[str] = field(default_factory=list)
    safety: bool = False
    engine: str = "models"
    confidence: float = 0.0


def analyse(text: str, sentiment_path: Path, emotion_path: Path) -> Analysis:
    """Sentiment per sentence, emotion distribution, theme flags and the safety screen."""
    result = Analysis(safety=safety_screen(text))
    parts = sentences(text)
    if not parts:
        result.emotions = {name: (1.0 if name == "neutral" else 0.0) for name in EMOTIONS}
        return result
    sentiment_model = _pipeline("sentiment", sentiment_path)
    emotion_model = _pipeline("emotion", emotion_path)
    result.engine = "models" if sentiment_model and emotion_model else "word lists"
    labels = []
    confidences = []
    for part in parts:
        if sentiment_model:
            scores = {item["label"].lower(): item["score"] for item in sentiment_model(part[:512], truncation=True)[0]}
        else:
            scores = _fallback_sentiment(part)
        label = max(scores, key=scores.get)
        labels.append(label)
        confidences.append(scores[label])
        result.segments.append({"text": part, "label": label, "score": round(scores[label], 3)})
    result.pos_ratio = labels.count("positive") / len(labels)
    result.neg_ratio = labels.count("negative") / len(labels)
    result.confidence = round(sum(confidences) / len(confidences), 2)
    totals = {name: 0.0 for name in EMOTIONS}
    if emotion_model:
        for part in parts:
            for item in emotion_model(part[:512], truncation=True)[0]:
                totals[item["label"].lower()] = totals.get(item["label"].lower(), 0) + item["score"]
    else:
        for label in labels:
            totals["joy" if label == "positive" else "sadness" if label == "negative" else "neutral"] += 1
    total = sum(totals.values()) or 1
    result.emotions = {name: round(value / total, 3) for name, value in totals.items()}
    themes = mental_config()["themes"]
    clean = f" {normalise(text)} "
    result.themes = [theme for theme, words in themes.items()
                     if any(f" {normalise(word)} " in clean for word in words)]
    return result


def wellbeing_score(analysis: Analysis, self_mood: int | None) -> float:
    """score = 100 · (0.35·sentiment + 0.25·emotion valence + 0.20·self-rating + 0.20·(1 − flag penalty))."""
    config = mental_config()
    weights = dict(config["wellbeing_weights"])
    e = analysis.emotions
    components = {
        "sentiment": (analysis.pos_ratio - analysis.neg_ratio + 1) / 2,
        "emotion": max(0.0, min(1.0, 0.5 + 0.5 * (e.get("joy", 0) - (e.get("sadness", 0) + e.get("anger", 0)
                                                                       + e.get("fear", 0) + e.get("disgust", 0))))),
        "flags": 1 - min(1.0, config["flag_penalty_per_theme"] * len(analysis.themes)),
    }
    if self_mood is not None:
        components["self_rating"] = (self_mood - 1) / 9
    else:
        weights.pop("self_rating")
    total = sum(weights.values())
    return round(100 * sum(weights[key] * components[key] for key in weights) / total, 1)


def mood_category(score: float) -> tuple[str, str]:
    """(word shown, internal status) for the score."""
    if score >= 70:
        return "Good", "NOMINAL"
    if score >= 55:
        return "Okay", "STABLE"
    return "Low", "CAUTION"


def summary_text(analysis: Analysis, score: float, category: str) -> str:
    """Three plain sentences. Never a diagnosis."""
    tone = {"Good": "You sounded mostly positive today.", "Okay": "You sounded mixed today.",
            "Low": "You sounded low today."}[category]
    if analysis.themes:
        second = "You talked about " + ", ".join(analysis.themes[:-1]) + \
                 (" and " if len(analysis.themes) > 1 else "") + analysis.themes[-1] + "."
    else:
        second = "Nothing in particular stood out as a worry."
    third = "This is a reflection of your words today, not a diagnosis." if category != "Low" else \
        "If this feeling stays for a few days, talk to your crew medical officer."
    return f"{tone} {second} {third}"


def suggestions(analysis: Analysis, category: str) -> list[dict]:
    texts = mental_config()["suggestions"]
    keys = []
    if "stress" in analysis.themes or category == "Low":
        keys.append("breathing")
    if "sleep trouble" in analysis.themes or "fatigue" in analysis.themes:
        keys.append("sleep")
    if "homesickness" in analysis.themes or "loneliness" in analysis.themes:
        keys.append("family")
    if "conflict" in analysis.themes or "loneliness" in analysis.themes:
        keys.append("crew")
    keys += ["exercise", "breathing", "crew"]
    unique = list(dict.fromkeys(keys))[:3]
    return [{"key": key, "text": texts[key]} for key in unique]
