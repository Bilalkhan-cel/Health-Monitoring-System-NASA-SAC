"""Daily tasks, XP, level, streak and badges (Section 9.6).

XP depends only on finishing tasks, never on the measured values, so there is no
incentive to fake good numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ..extensions import db
from ..models import Astronaut, Badge, DailyTask, Notification, ReadinessDaily, SleepLog, utcnow
from .readiness import load_indicators

ALL_TASKS_BONUS = 20
STREAK_MIN_TASKS = 3
BADGES = {
    "iron_heart": ("Iron Heart", "7 heart checks in 7 days"),
    "titanium_bones": ("Titanium Bones", "Exercise on 5 days in a week"),
    "steady_mind": ("Steady Mind", "7 voice check-ins in 10 days"),
    "streak_7": ("7-Day Streak", "3 or more tasks a day for 7 days"),
    "night_owl_reformed": ("Night Owl Reformed", "3 nights of 7 h or more after 3 short nights"),
    "full_systems_go": ("Full Systems Go", "Readiness 85 or higher for 3 days"),
}


@dataclass(frozen=True)
class TaskOutcome:
    newly_done: bool
    xp_gained: int
    badges: tuple[str, ...] = ()


def level_for(xp: int) -> int:
    return int((xp / 50) ** 0.5) + 1


def _done_counts(astronaut_id: int) -> dict[date, int]:
    counts: dict[date, int] = {}
    for task in DailyTask.query.filter_by(astronaut_id=astronaut_id, done=True):
        counts[task.date] = counts.get(task.date, 0) + 1
    return counts


def streak_for(astronaut_id: int, today: date) -> int:
    """Consecutive mission days with at least 3 of 5 tasks done (today counts once it qualifies)."""
    counts = _done_counts(astronaut_id)
    day = today if counts.get(today, 0) >= STREAK_MIN_TASKS else today - timedelta(days=1)
    streak = 0
    while counts.get(day, 0) >= STREAK_MIN_TASKS:
        streak, day = streak + 1, day - timedelta(days=1)
    return streak


def complete_task(astronaut: Astronaut, code: str, when: datetime | None = None) -> TaskOutcome:
    """Tick a task for the day, award XP once, update streak and badges. Does not commit."""
    when = when or utcnow()
    tasks = load_indicators()["tasks"]
    if code not in tasks:
        raise KeyError(code)
    task = DailyTask.query.filter_by(astronaut_id=astronaut.id, date=when.date(), task_code=code).first()
    if task is None:
        task = DailyTask(astronaut_id=astronaut.id, date=when.date(), task_code=code)
        db.session.add(task)
    if task.done:
        return TaskOutcome(False, 0)
    task.done, task.done_at = True, when
    db.session.flush()
    gained = tasks[code]["xp"]
    done_today = DailyTask.query.filter_by(astronaut_id=astronaut.id, date=when.date(), done=True).count()
    if done_today == len(tasks):
        gained += ALL_TASKS_BONUS
    astronaut.xp += gained
    astronaut.level = level_for(astronaut.xp)
    astronaut.streak = streak_for(astronaut.id, when.date())
    return TaskOutcome(True, gained, tuple(award_badges(astronaut, when)))


def _has(astronaut_id: int, code: str) -> bool:
    return Badge.query.filter_by(astronaut_id=astronaut_id, code=code).first() is not None


def earned_badges(astronaut_id: int, today: date) -> set[str]:
    """Which badge rules hold today."""
    earned: set[str] = set()
    tasks = DailyTask.query.filter(DailyTask.astronaut_id == astronaut_id, DailyTask.done.is_(True),
                                   DailyTask.date > today - timedelta(days=10)).all()
    by_code: dict[str, set[date]] = {}
    for task in tasks:
        by_code.setdefault(task.task_code, set()).add(task.date)
    week = {today - timedelta(days=i) for i in range(7)}
    if len(by_code.get("cardio", set()) & week) >= 7:
        earned.add("iron_heart")
    if len(by_code.get("exercise", set()) & week) >= 5:
        earned.add("titanium_bones")
    if len(by_code.get("mental", set())) >= 7:
        earned.add("steady_mind")
    if streak_for(astronaut_id, today) >= 7:
        earned.add("streak_7")
    nights = [log.hours for log in SleepLog.query.filter(SleepLog.astronaut_id == astronaut_id,
                                                         SleepLog.date > today - timedelta(days=6))
              .order_by(SleepLog.date)]
    if len(nights) >= 6 and all(h < 6 for h in nights[-6:-3]) and all(h >= 7 for h in nights[-3:]):
        earned.add("night_owl_reformed")
    scores = [row.score for row in ReadinessDaily.query.filter(ReadinessDaily.astronaut_id == astronaut_id,
                                                               ReadinessDaily.date > today - timedelta(days=3))]
    if len(scores) == 3 and all(score is not None and score >= 85 for score in scores):
        earned.add("full_systems_go")
    return earned


def award_badges(astronaut: Astronaut, when: datetime) -> list[str]:
    """Award any newly earned badge (once) with a notification. Does not commit."""
    new = []
    for code in sorted(earned_badges(astronaut.id, when.date())):
        if _has(astronaut.id, code):
            continue
        name, rule = BADGES[code]
        db.session.add(Badge(astronaut_id=astronaut.id, code=code, awarded_at=when))
        db.session.add(Notification(astronaut_id=astronaut.id, type="badge", severity="good",
                                    title=f"Badge unlocked: {name}", message=f"{rule}. Nice work.",
                                    action_url="/settings", dedupe_key=f"badge:{code}", created_at=when))
        new.append(code)
    return new


def badges_for(astronaut_id: int) -> list[dict]:
    owned = {badge.code: badge for badge in Badge.query.filter_by(astronaut_id=astronaut_id)}
    return [{"code": code, "name": name, "rule": rule, "earned": code in owned,
             "awarded_at": owned[code].awarded_at.date().isoformat() if code in owned else None}
            for code, (name, rule) in BADGES.items()]


def summary_for(astronaut: Astronaut) -> dict:
    return {"xp": astronaut.xp, "level": astronaut.level, "streak": astronaut.streak,
            "next_level_xp": 50 * astronaut.level ** 2, "badges": badges_for(astronaut.id)}

