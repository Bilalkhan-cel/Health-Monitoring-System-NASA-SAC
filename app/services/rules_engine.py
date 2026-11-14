"""Offline Dr. NOVA: rule-based answers from the same context the AI engines get.

Used when neither OpenHome nor the fallback LLM is reachable, and by the voice mock.
It follows the persona's rules: quotes only real values, never volunteers where a
number came from (but answers truthfully when asked), never diagnoses or prescribes,
and escalates emergency symptoms with the comms delay.
"""

from __future__ import annotations

import re

from .doctor_context import source_sentence
from .readiness import load_indicators
from .recommendations import steps
from .summary import duration_text

EMERGENCY = re.compile(r"chest pain|cant breathe|can not breathe|short of breath|faint|passed out|confus|"
                       r"severe headache|worst headache|vision|bleeding|\bnumb(ness)?\b|slurred")
SOURCE_QUESTION = re.compile(r"how (was|is|were|are|did) (that|this|it|these|the|my)?.*(measured|calculated|get|got|"
                             r"obtained|know)|where (does|did) (that|this|it|the).*(come|number)|is (that|this|it) "
                             r"(real|measured|simulated|generated)|which sensor|what sensor")
TOPICS = {
    "heart": ("heart", "pulse", "heart rate", "bpm", "cardio"),
    "blood_pressure": ("blood pressure", "pressure", "bp"),
    "spo2": ("oxygen", "spo2", "saturation"),
    "temperature_c": ("temperature", "fever", "temp"),
    "glucose": ("sugar", "glucose"),
    "respiration": ("breathing rate", "respiration", "breaths"),
    "sleep": ("sleep", "tired", "insomnia", "waking up", "wake up"),
    "mood": ("mood", "stress", "stressed", "anxious", "lonely", "sad", "feel down", "homesick"),
    "exercise": ("exercise", "workout", "bone", "muscle", "load", "push-up", "pushup"),
    "week": ("week", "trend", "history"),
}
METRIC_FOR_TOPIC = {"heart": "heart_rate", "blood_pressure": "blood_pressure", "spo2": "spo2",
                    "temperature_c": "temperature_c", "glucose": "glucose", "respiration": "respiration",
                    "sleep": "sleep_hours", "mood": "wellbeing", "exercise": "loading_index"}
SYSTEM_FOR_TOPIC = {"heart": "heart", "blood_pressure": "heart", "spo2": "heart", "temperature_c": "heart",
                    "glucose": "heart", "respiration": "heart", "sleep": "mind", "mood": "mind", "exercise": "bones"}
STATUS_KEY = {"Good": "NOMINAL", "Okay": "STABLE", "Needs attention": "CAUTION", "Get help now": "CRITICAL"}


def _metric(context: dict, metric: str) -> dict | None:
    return next((item for item in context.get("latest", []) if item["metric"] == metric), None)


def _value_text(item: dict) -> str:
    value = item["value"]
    if isinstance(value, dict):
        return f"{value['sys']}/{value['dia']} mmHg"
    if item["metric"] == "sleep_hours":
        hours = int(value)
        return f"{hours} hours {round((value - hours) * 60)} minutes"
    unit = item["unit"] if item["unit"] not in ("score", "/100") else "out of 100"
    return f"{value} {unit}".replace(" %", "%")


def _label(metric: str) -> str:
    return load_indicators()["metrics"][metric]["short"].lower()


def _when(item: dict) -> str:
    hours = item["data_age_h"]
    if hours < 1:
        return "in the last hour"
    if hours < 24:
        return f"{round(hours)} hours ago"
    return f"{round(hours / 24)} days ago"


def _delay(context: dict) -> str:
    return duration_text(context["mission"]["comms_delay_one_way_s"])


def _escalation(context: dict, reason: str) -> str:
    return (f"{reason} Please tell your crew medical officer now and follow the onboard medical protocol. "
            f"The ground flight surgeon should be contacted too; messages to Earth take {_delay(context)}.")


def topic_of(message: str) -> str | None:
    text = message.lower()
    for topic, words in TOPICS.items():
        if any(word in text for word in words):
            return topic
    return None


def _numbered(actions: list[str], voice: bool) -> str:
    if voice:
        ordinals = ("First", "second", "third")
        return " ".join(f"{ordinals[i]}, {action[0].lower()}{action[1:]}" for i, action in enumerate(actions[:3]))
    return "\n".join(f"{i + 1}. {action}" for i, action in enumerate(actions[:3]))


def overview(context: dict, voice: bool = False) -> str:
    name = context["profile"].get("callsign") or "there"
    flagged = [item for item in context["latest"] if item["status_word"] in ("Needs attention", "Get help now")]
    critical = [item for item in flagged if item["status_word"] == "Get help now"]
    if critical:
        item = critical[0]
        return _escalation(context, f"{name}, your {_label(item['metric'])} is {_value_text(item)}, which needs help now.")
    good = [item for item in context["latest"] if item["status_word"] in ("Good", "Okay")]
    good_names = ", ".join(_label(item["metric"]) for item in good[:2])
    if not flagged:
        return (f"You're doing well, {name}. Your {good_names or 'readings'} look fine. "
                "Keep drinking water and keep your exercise going.")
    first = flagged[0]
    sentence = f"Mostly well, {name}. " if len(flagged) == 1 else f"A couple of things need attention, {name}. "
    sentence += f"Your {_label(first['metric'])} is {_value_text(first)}"
    if first.get("baseline"):
        sentence += f", and your usual is {first['baseline']}"
    sentence += "."
    if len(flagged) > 1:
        second = flagged[1]
        sentence += f" Your {_label(second['metric'])} is {_value_text(second)} too."
    if first.get("note"):
        sentence += " That reading is unconfirmed, so it's a prompt to re-measure, not an emergency."
    topic = next((t for t, m in METRIC_FOR_TOPIC.items() if m == first["metric"]), "heart")
    actions = steps(SYSTEM_FOR_TOPIC[topic], STATUS_KEY.get(first["status_word"], "CAUTION"),
                    context["mission"]["environment"], _delay(context))
    joiner = " " if voice else "\n\nHere's what I'd do:\n"
    return sentence + joiner + _numbered(actions, voice)


def about_metric(context: dict, topic: str, voice: bool = False) -> str:
    metric = METRIC_FOR_TOPIC[topic]
    item = _metric(context, metric)
    if item is None:
        return f"I don't have a recent {_label(metric)} reading. Want to take one now?"
    if item["data_age_h"] > 48:
        return (f"Your last {_label(metric)} reading was {_value_text(item)}, {_when(item)}. That's too old to "
                "rely on. Want to take a fresh one?")
    word = item["status_word"] or "Recorded"
    text = f"Your {_label(metric)} was {_value_text(item)} {_when(item)}. That's {word.lower()}."
    if item.get("baseline"):
        text += f" Your usual is {item['baseline']}."
    if item.get("note"):
        text += " It isn't confirmed yet, so please re-measure."
    if metric == "spo2" and item["source"] == "sensor" and word != "Good":
        text += (" The wearable's oxygen sensor is hobby-grade, so re-measure while keeping your hand still. "
                 "How do you feel?")
    if word == "Get help now":
        return _escalation(context, text)
    if word == "Needs attention":
        actions = steps(SYSTEM_FOR_TOPIC[topic], "CAUTION", context["mission"]["environment"], _delay(context))
        text += (" " if voice else "\n\n") + _numbered(actions, voice)
    if metric == "loading_index":
        text += " The camera counts loading exercise; it can't measure bone density."
    if metric == "wellbeing":
        text += " This comes from your check-in's words and rating, so it's support, not a diagnosis."
    return text


def source_answer(context: dict, message: str) -> str:
    topic = topic_of(message)
    items = [_metric(context, METRIC_FOR_TOPIC[topic])] if topic in METRIC_FOR_TOPIC else context["latest"][:6]
    lines = [f"Your {_label(item['metric'])} was {source_sentence(item)}." for item in items if item]
    if not lines:
        return "I don't have a reading for that yet."
    return " ".join(lines)


def week(context: dict) -> str:
    trends = context.get("trends_14d", {})
    if not trends:
        return "I don't have enough readings yet to describe your last two weeks."
    parts = []
    for metric, trend in list(trends.items())[:4]:
        parts.append(f"your {_label(metric)} is {trend['direction']}")
    streak = context.get("streak_days")
    text = "Over the last two weeks, " + ", ".join(parts) + "."
    if streak:
        text += f" You've kept a {streak}-day streak of daily checks. Nice work."
    return text


def answer(message: str, context: dict, *, voice: bool = False) -> str:
    """One reply in the persona's voice."""
    text = message.lower().replace("'", "")
    if EMERGENCY.search(text):
        return _escalation(context, "That symptom can be serious.")
    if SOURCE_QUESTION.search(text):
        return source_answer(context, message)
    if any(word in text for word in ("medication", "medicine", "pill", "dose", "ibuprofen", "paracetamol",
                                     "prescribe", "drug")):
        return ("I can't recommend medicines or doses. Please ask your crew medical officer, who can check the "
                "onboard kit and talk to the ground flight surgeon.")
    if any(word in text for word in ("diagnos", "do i have", "is it cancer", "am i sick")):
        return ("I can't give a diagnosis. I can tell you what your readings show and when to involve your crew "
                "medical officer. " + overview(context, voice))
    topic = topic_of(message)
    if topic == "week":
        return week(context)
    if topic:
        return about_metric(context, topic, voice)
    return overview(context, voice)
