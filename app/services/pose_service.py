"""Pose analysis on canonical COCO keypoints (Section 11).

The browser runs MediaPipe and sends only keypoints (never video). Each frame is
``{"t": seconds, "kp": {name: [x, y, confidence]}}`` in normalised image coordinates
(y grows downwards). This module turns them into joint angles, counts reps with small
state machines (hysteresis, minimum 0.6 s per rep), scores form, and estimates running
cadence. Pure Python, no I/O.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

COCO = ("nose", "l_eye", "r_eye", "l_ear", "r_ear", "l_shoulder", "r_shoulder", "l_elbow", "r_elbow",
        "l_wrist", "r_wrist", "l_hip", "r_hip", "l_knee", "r_knee", "l_ankle", "r_ankle")
MIN_CONFIDENCE = 0.4
MIN_REP_S = 0.6
EMA_ALPHA = 0.5
MIN_CADENCE_FPS = 10
EXERCISES = ("run", "pushup", "pullup", "squat")

Point = tuple[float, float, float]


def angle(a: Point, b: Point, c: Point) -> float:
    """Angle at b (degrees) between b→a and b→c."""
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 == 0 or n2 == 0:
        return 180.0
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cos))


def pick_side(kp: dict[str, Point], joints: tuple[str, ...]) -> str | None:
    """The side (l/r) whose chain has the higher mean confidence, if it is confident enough."""
    best, best_score = None, -1.0
    for side in ("l", "r"):
        points = [kp.get(f"{side}_{joint}") for joint in joints]
        if any(point is None for point in points):
            continue
        score = sum(point[2] for point in points) / len(points)
        if min(point[2] for point in points) >= MIN_CONFIDENCE and score > best_score:
            best, best_score = side, score
    return best


@dataclass
class Update:
    reps: int
    state: str
    cue: str | None = None
    rep_done: bool = False
    form: int | None = None
    cadence: float | None = None
    steps: int | None = None
    confidence: float = 0.0


@dataclass
class _Ema:
    value: float | None = None

    def push(self, sample: float) -> float:
        self.value = sample if self.value is None else EMA_ALPHA * sample + (1 - EMA_ALPHA) * self.value
        return self.value


@dataclass
class RepCounter:
    """Shared logic: a DOWN phase followed by an UP phase is one rep."""

    exercise: str
    reps: int = 0
    phase: str = "up"
    last_rep_t: float = -10.0
    started_t: float | None = None
    form_scores: list[int] = field(default_factory=list)
    _angle: _Ema = field(default_factory=_Ema)
    _rep_min: float = 180.0
    _rep_max_dev: float = 0.0
    _went_partway: bool = False

    def _complete(self, t: float, form: int) -> Update:
        if t - self.last_rep_t < MIN_REP_S:
            self.phase = "up"
            return Update(self.reps, "up", "Slow down a little.")
        self.reps += 1
        self.last_rep_t = t
        self.phase = "up"
        self.form_scores.append(form)
        return Update(self.reps, "up", "Good rep!", rep_done=True, form=form)

    @property
    def form(self) -> int | None:
        return round(sum(self.form_scores) / len(self.form_scores)) if self.form_scores else None


class PushUpCounter(RepCounter):
    """DOWN: elbow < 90° with hip–shoulder–ankle within 15° of straight. UP: elbow > 155°."""

    def __init__(self) -> None:
        super().__init__("pushup")

    def update(self, t: float, kp: dict[str, Point]) -> Update:
        side = pick_side(kp, ("shoulder", "elbow", "wrist", "hip", "ankle"))
        if side is None:
            return Update(self.reps, self.phase, "Step back so your whole body is in view.")
        s, e, w = kp[f"{side}_shoulder"], kp[f"{side}_elbow"], kp[f"{side}_wrist"]
        h, a = kp[f"{side}_hip"], kp[f"{side}_ankle"]
        elbow = self._angle.push(angle(s, e, w))
        deviation = abs(180 - angle(s, h, a))
        cue = None
        if self.phase == "up":
            if elbow < 125:
                self._went_partway = True
            if elbow < 90:
                if deviation <= 15:
                    self.phase = "down"
                    self._rep_min, self._rep_max_dev = elbow, deviation
                else:
                    cue = "Keep your body in a straight line."
            elif self._went_partway and elbow > 155:
                self._went_partway = False
                cue = "Go lower."
        else:
            self._rep_min = min(self._rep_min, elbow)
            self._rep_max_dev = max(self._rep_max_dev, deviation)
            if deviation > 20:
                cue = "Keep your hips level."
            if elbow > 155:
                self._went_partway = False
                depth = max(0.0, min(1.0, (110 - self._rep_min) / 30))
                straight = max(0.0, 1 - self._rep_max_dev / 25)
                return self._complete(t, round(100 * (0.6 * depth + 0.4 * straight)))
        return Update(self.reps, self.phase, cue, confidence=_mean_conf(kp, side))


class PullUpCounter(RepCounter):
    """UP: nose (or ear midpoint) above the wrist line and elbow < 70°. DOWN: elbow > 150°."""

    def __init__(self) -> None:
        super().__init__("pullup")
        self.phase = "down"
        self._extended = True

    def update(self, t: float, kp: dict[str, Point]) -> Update:
        side = pick_side(kp, ("shoulder", "elbow", "wrist"))
        if side is None:
            return Update(self.reps, self.phase, "Step back so your arms are in view.")
        elbow = self._angle.push(angle(kp[f"{side}_shoulder"], kp[f"{side}_elbow"], kp[f"{side}_wrist"]))
        head = kp.get("nose")
        if head is None or head[2] < MIN_CONFIDENCE:
            ears = [kp.get("l_ear"), kp.get("r_ear")]
            ears = [ear for ear in ears if ear and ear[2] >= MIN_CONFIDENCE]
            head = (0, sum(ear[1] for ear in ears) / len(ears), 1) if ears else None
        wrists = [kp.get(f"{s}_wrist") for s in ("l", "r") if kp.get(f"{s}_wrist")]
        wrist_line = sum(w[1] for w in wrists) / len(wrists)
        above = head is not None and head[1] < wrist_line
        cue = None
        if self.phase == "down":
            if elbow > 150:
                self._extended = True
            if above and elbow < 70:
                if not self._extended:
                    cue = "Full extension at the bottom."
                    self.phase = "up"
                else:
                    self.phase = "up"
                    self._extended = False
                    return self._complete_up(t)
        elif elbow > 150:
            self.phase = "down"
            self._extended = True
        return Update(self.reps, self.phase, cue, confidence=_mean_conf(kp, side))

    def _complete_up(self, t: float) -> Update:
        update = self._complete(t, 90)
        self.phase = "up"
        update.state = "up"
        return update


class SquatCounter(RepCounter):
    """DOWN: knee < 100°. UP: knee > 160°."""

    def __init__(self) -> None:
        super().__init__("squat")

    def update(self, t: float, kp: dict[str, Point]) -> Update:
        side = pick_side(kp, ("hip", "knee", "ankle"))
        if side is None:
            return Update(self.reps, self.phase, "Step back so your legs are in view.")
        knee = self._angle.push(angle(kp[f"{side}_hip"], kp[f"{side}_knee"], kp[f"{side}_ankle"]))
        cue = None
        if self.phase == "up":
            if knee < 130:
                self._went_partway = True
            if knee < 100:
                self.phase = "down"
                self._rep_min = knee
            elif self._went_partway and knee > 160:
                self._went_partway = False
                cue = "Go a little deeper."
        else:
            self._rep_min = min(self._rep_min, knee)
            if knee > 160:
                self._went_partway = False
                depth = max(0.0, min(1.0, (115 - self._rep_min) / 30))
                return self._complete(t, round(60 + 40 * depth))
        return Update(self.reps, self.phase, cue, confidence=_mean_conf(kp, side))


class CadenceTracker:
    """Steps from the alternating vertical position of the ankles (with hysteresis)."""

    def __init__(self) -> None:
        self.steps = 0
        self.exercise = "run"
        self.started_t: float | None = None
        self._sign = 0
        self._step_times: deque[float] = deque(maxlen=64)
        self._frame_times: deque[float] = deque(maxlen=60)
        self._diff = _Ema()
        self.form_scores: list[int] = []

    @property
    def reps(self) -> int:
        return self.steps

    @property
    def form(self) -> int | None:
        return None

    def fps(self) -> float:
        if len(self._frame_times) < 2:
            return 0.0
        span = self._frame_times[-1] - self._frame_times[0]
        return (len(self._frame_times) - 1) / span if span > 0 else 0.0

    def cadence(self, t: float) -> float | None:
        if self.fps() < MIN_CADENCE_FPS:
            return None
        recent = [s for s in self._step_times if t - s <= 10]
        if len(recent) < 3:
            return None
        span = recent[-1] - recent[0]
        return round((len(recent) - 1) / span * 60, 1) if span > 0 else None

    def update(self, t: float, kp: dict[str, Point]) -> Update:
        self._frame_times.append(t)
        if self.started_t is None:
            self.started_t = t
        left, right = kp.get("l_ankle"), kp.get("r_ankle")
        if not left or not right or min(left[2], right[2]) < MIN_CONFIDENCE:
            left, right = kp.get("l_knee"), kp.get("r_knee")
        if not left or not right or min(left[2], right[2]) < MIN_CONFIDENCE:
            return Update(self.steps, "run", "Step back so your feet are in view.", steps=self.steps)
        diff = self._diff.push(left[1] - right[1])
        threshold = 0.012
        sign = 1 if diff > threshold else -1 if diff < -threshold else 0
        if sign and sign != self._sign:
            if self._sign:
                self.steps += 1
                self._step_times.append(t)
            self._sign = sign
        cadence = self.cadence(t)
        return Update(self.steps, "run", None if cadence or self.fps() >= MIN_CADENCE_FPS else
                      "Hold the camera steady: the video is too slow to measure cadence.",
                      cadence=cadence, steps=self.steps)


def _mean_conf(kp: dict[str, Point], side: str) -> float:
    values = [point[2] for name, point in kp.items() if name.startswith(f"{side}_")]
    return round(sum(values) / len(values), 2) if values else 0.0


def make_counter(exercise: str):
    return {"pushup": PushUpCounter, "pullup": PullUpCounter, "squat": SquatCounter,
            "run": CadenceTracker}[exercise]()


def parse_keypoints(raw: object) -> dict[str, Point] | None:
    """Validate one frame's keypoints. Unknown names are ignored; bad values reject the frame."""
    if not isinstance(raw, dict):
        return None
    out: dict[str, Point] = {}
    for name in COCO:
        value = raw.get(name)
        if value is None:
            continue
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            return None
        try:
            x, y, c = (float(v) for v in value)
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(v) for v in (x, y, c)) or not 0 <= c <= 1:
            return None
        out[name] = (x, y, c)
    return out
