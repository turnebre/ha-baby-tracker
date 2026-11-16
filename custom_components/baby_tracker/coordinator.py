"""KPI calculation from the database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import logging
from statistics import median
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BIRTH_DATE,
    CONF_BABY_NAME,
    CONF_SEX,
    CONF_UNIT,
    DOMAIN,
    ML_PER_KG_DAY,
    ML_PER_OZ,
    OZ_DAY_MAX,
)
from .db import BabyDB

_LOGGER = logging.getLogger(__name__)

SERIES_DAYS = 30


@dataclass
class BabyRuntime:
    """In-memory state of the integration (entry.runtime_data)."""

    db: BabyDB
    coordinator: BabyCoordinator
    oz_default: float
    type_default: str
    goal_oz_day: float
    prescribed_interval_h: float
    night_start: time
    night_end: time
    bottle_limit_h: float
    breast_milk_limit_h: float
    room_expiry_h: float
    fridge_expiry_days: float

    @property
    def limits(self) -> dict[str, float]:
        return {
            "formula": self.bottle_limit_h,
            "breast_milk": self.breast_milk_limit_h,
            "room": self.room_expiry_h,
            "fridge": self.fridge_expiry_days * 24,
        }


def _parse(iso: str) -> datetime:
    return dt_util.as_local(dt_util.parse_datetime(iso))


def _per_weight(weight_kg: float) -> float:
    """General weight-based reference (~150 ml/kg/day, capped), in oz/day."""
    return round(min(weight_kg * ML_PER_KG_DAY / ML_PER_OZ, OZ_DAY_MAX), 1)


def _achievement(oz: float, minimum: float, ideal: float) -> int:
    """0 = did not reach the minimum, 1 = minimum, 2 = ideal (with rounding margin)."""
    return 2 if oz >= ideal - 0.05 else 1 if oz >= minimum - 0.05 else 0


# ---------- Overnight window: no feedings are expected between bedtime and wake-up ----------

def _at(day: date, t: time) -> datetime:
    return dt_util.start_of_local_day(day).replace(hour=t.hour, minute=t.minute)


def _night_spans(rt: BabyRuntime, lo: datetime, hi: datetime) -> list[tuple[datetime, datetime]]:
    """Night intervals overlapping [lo, hi], oldest first. Equal bedtime and wake-up means no night."""
    if rt.night_start == rt.night_end:
        return []
    spans = []
    for i in range(-1, (hi.date() - lo.date()).days + 1):
        day = lo.date() + timedelta(days=i)
        end_day = day if rt.night_end > rt.night_start else day + timedelta(days=1)
        start, end = _at(day, rt.night_start), _at(end_day, rt.night_end)
        if end > lo and start < hi:
            spans.append((start, end))
    return spans


def _in_night(rt: BabyRuntime, when: datetime) -> datetime | None:
    """Wake-up time if `when` falls inside the night, else None."""
    for start, end in _night_spans(rt, when, when + timedelta(seconds=1)):
        if start <= when < end:
            return end
    return None


def _next_bedtime(rt: BabyRuntime, when: datetime) -> datetime | None:
    starts = [s for s, _ in _night_spans(rt, when, when + timedelta(days=2)) if s > when]
    return min(starts) if starts else None


def _awake_seconds(rt: BabyRuntime, a: datetime, b: datetime) -> float:
    """Seconds between a and b that are not night."""
    total = b.timestamp() - a.timestamp()
    for start, end in _night_spans(rt, a, b):
        total -= max(0.0, min(end, b).timestamp() - max(start, a).timestamp())
    return max(0.0, total)


def _step(rt: BabyRuntime, when: datetime) -> datetime:
    """Time of the feeding that follows one at `when`: interval later, a top-up right at bedtime if the
    interval would cross it (and bedtime is at least half an interval away), and wake-up after that."""
    interval = timedelta(hours=rt.prescribed_interval_h)
    nxt = when + interval
    if (wake := _in_night(rt, when)) is not None:  # a feeding in the middle of the night
        return wake if nxt < wake else nxt
    bedtime = _next_bedtime(rt, when)
    if bedtime is not None and nxt >= bedtime:
        return bedtime if bedtime - when >= interval / 2 else _in_night(rt, bedtime) or nxt
    return nxt


def _plan_slots(rt: BabyRuntime, start: datetime, end: datetime) -> list[datetime]:
    """Planned feeding times in [start, end): every interval while awake, skipping the night."""
    slots: list[datetime] = []
    when = _in_night(rt, start) or start
    while when < end and len(slots) < 200:
        slots.append(when)
        when = _step(rt, when)
    return slots


class BabyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Recalculates Kpis every 5 min and after every log."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, db: BabyDB) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=timedelta(minutes=5)
        )
        self.db = db
        self.entry = entry
        self.birth = date.fromisoformat(entry.data[CONF_BIRTH_DATE])

    async def _async_update_data(self) -> dict[str, Any]:
        return await self.hass.async_add_executor_job(self._calculate)

    def _calculate(self) -> dict[str, Any]:
        rt: BabyRuntime = self.entry.runtime_data
        now = dt_util.now()
        today = now.date()
        today_start = dt_util.start_of_local_day(today)
        series_start = dt_util.start_of_local_day(today - timedelta(days=SERIES_DAYS - 1))
        feedings = self.db.feedings_since(dt_util.as_utc(series_start).isoformat())
        for t in feedings:
            t["_ended_at"] = _parse(t["ended_at"])

        # Daily series (local day)
        per_day: dict[date, dict[str, float]] = {}
        for t in feedings:
            d = per_day.setdefault(t["_ended_at"].date(), {"oz": 0.0, "feedings": 0, "exact": 0})
            d["oz"] += t["oz_taken"]
            d["feedings"] += 1
            d["exact"] += t["confidence"] == "exact"
        series = []
        for i in range(SERIES_DAYS):
            day = today - timedelta(days=SERIES_DAYS - 1 - i)
            d = per_day.get(day, {"oz": 0.0, "feedings": 0, "exact": 0})
            series.append({
                "date": day.isoformat(),
                "oz": round(d["oz"], 2),
                "feedings": d["feedings"],
                "exact": d["exact"],
            })

        today_d = per_day.get(today, {"oz": 0.0, "feedings": 0, "exact": 0})
        oz_24h = sum(t["oz_taken"] for t in feedings if t["_ended_at"] >= now - timedelta(hours=24))

        # Average of the last 7 complete days (excluding today), only days since the first record
        first_day = min(per_day) if per_day else today
        days_7 = [today - timedelta(days=i) for i in range(1, 8)]
        days_valid = [d for d in days_7 if d >= first_day]
        average_7d = (
            round(sum(per_day.get(d, {"oz": 0})["oz"] for d in days_valid) / len(days_valid), 2)
            if days_valid else None
        )

        # Typical interval: median between feedings over the last 48 h (ignores gaps > 8 h)
        recent = [t["_ended_at"] for t in feedings if t["_ended_at"] >= now - timedelta(hours=48)]
        intervals = [
            (b - a).total_seconds() / 3600
            for a, b in zip(recent, recent[1:])
            if 0.5 <= (b - a).total_seconds() / 3600 <= 8
        ]
        interval_h = round(median(intervals), 2) if len(intervals) >= 3 else None

        last = self.db.last_feeding()
        last_ended_at = _parse(last["ended_at"]) if last else None
        # The next feeding follows the pediatrician's guidance, not the learned interval, and never falls overnight
        next_feeding = _step(rt, last_ended_at) if last_ended_at else None

        # Last 7 days (168 h): oz per feeding and frequency
        hace7 = now - timedelta(days=7)
        t7 = [t for t in feedings if t["_ended_at"] >= hace7]
        days_with_data = max(1.0, min(7.0, (now - max(hace7, feedings[0]["_ended_at"])).total_seconds() / 86400)) if feedings else 1.0
        oz_per_feeding = round(sum(t["oz_taken"] for t in t7) / len(t7), 2) if t7 else None
        feedings_per_day = round(len(t7) / days_with_data, 1) if t7 else None

        # Bottles
        bottle = self.db.current_bottle(rt.limits)
        paused = self.db.paused_bottles(rt.limits)
        b7 = self.db.bottles_range(
            dt_util.as_utc(hace7).isoformat(timespec="seconds"),
            dt_util.as_utc(now + timedelta(days=1)).isoformat(timespec="seconds"),
            rt.limits,
        )
        cerrados7 = [b for b in b7 if b["state"] in ("finished", "incomplete")]
        bottles_today = sum(1 for b in b7 if b["state"] != "stash" and _parse(b["prepared_at"]) >= today_start)
        pct_finished = (
            round(sum(b["state"] == "finished" for b in cerrados7) / len(cerrados7) * 100)
            if cerrados7 else None
        )
        wasted_7d = round(sum(b["wasted"] for b in b7), 2)
        breast_milk_wasted_7d = round(sum(b["wasted"] for b in b7 if b["type"] == "breast_milk"), 2)

        # Breast milk: feedings by type today, pumping and stash
        today_feedings = [t for t in feedings if t["_ended_at"] >= today_start]
        breast_milk_today = round(sum(t["oz_taken"] for t in today_feedings if t["type"] == "breast_milk"), 2)
        formula_today = round(sum(t["oz_taken"] for t in today_feedings if t["type"] != "breast_milk"), 2)
        pump = self.db.pumpings_range(
            dt_util.as_utc(hace7).isoformat(timespec="seconds"),
            dt_util.as_utc(now + timedelta(minutes=1)).isoformat(timespec="seconds"),
        )
        pumped_today = round(sum(e["oz_total"] for e in pump if _parse(e["ended_at"]) >= today_start), 2)
        days_pump = max(1.0, min(7.0, (now - _parse(pump[0]["ended_at"])).total_seconds() / 86400)) if pump else 1.0
        pumped_day = round(sum(e["oz_total"] for e in pump) / days_pump, 2) if pump else None
        stashes = self.db.stashes(rt.limits)
        current = [b for b in stashes if not b["expired"]]
        next_expiry = min((b["expires_at"] for b in current if b["expires_at"]), default=None)

        # Diapers
        pn = self.db.diapers_range(
            dt_util.as_utc(hace7).isoformat(timespec="seconds"),
            dt_util.as_utc(now + timedelta(minutes=1)).isoformat(timespec="seconds"),
        )
        for x in pn:
            x["_ended_at"] = _parse(x["ended_at"])
        pn_today = [x for x in pn if x["_ended_at"] >= today_start]
        count_today = {t: sum(1 for x in pn_today if x["type"] == t) for t in ("pee", "poop", "both")}
        days_pn = max(1.0, min(7.0, (now - pn[0]["_ended_at"]).total_seconds() / 86400)) if pn else 1.0
        fines = [x["_ended_at"] for x in pn if x["_ended_at"] >= now - timedelta(hours=48)]
        ints_pn = [(b - a).total_seconds() / 3600 for a, b in zip(fines, fines[1:]) if (b - a).total_seconds() > 300]
        last_diaper = self.db.last_diaper()
        last_pee = self.db.last_diaper(("pee", "both"))
        last_poop = self.db.last_diaper(("poop", "both"))

        weight = self.db.last_measurement("weight_kg")
        height = self.db.last_measurement("height_cm")
        weight_kg = weight["weight_kg"] if weight else None
        day_end = dt_util.start_of_local_day(today + timedelta(days=1))
        # Planned daytime feedings and the amount each one needs to reach the daily goal
        feedings_goal = len(_plan_slots(rt, today_start, day_end)) or 1
        goal = round(rt.goal_oz_day, 1)
        awake_s = _awake_seconds(rt, today_start, day_end)
        weight_reference = _per_weight(weight_kg) if weight_kg else None
        reference = self._reference(rt, now, today, today_start, today_d["oz"], goal, next_feeding, series, first_day,
                                    feedings_goal)

        return {
            "reference": reference,
            "last": last,
            "last_ended_at": last_ended_at,
            "oz_today": round(today_d["oz"], 2),
            "feedings_today": today_d["feedings"],
            "exact_today": today_d["exact"],
            "oz_24h": round(oz_24h, 2),
            "average_7d": average_7d,
            "interval_h": interval_h,
            "next": next_feeding,
            "weight": weight,
            "height": height,
            "goal_oz_day": goal,
            "feedings_goal": feedings_goal,
            "planned_oz_feeding": round(goal / feedings_goal, 2),
            "awake_hours": round(awake_s / 3600, 1),
            "night_start": rt.night_start.strftime("%H:%M"),
            "night_end": rt.night_end.strftime("%H:%M"),
            "reference_weight_oz_day": weight_reference,
            "goal_progress": round(today_d["oz"] / goal * 100) if goal else None,
            "age_days": (today - self.birth).days,
            "name": self.entry.data.get(CONF_BABY_NAME),
            "birth": self.entry.data[CONF_BIRTH_DATE],
            "sex": self.entry.data.get(CONF_SEX, "unspecified"),
            "unit": self.entry.data.get(CONF_UNIT, "oz"),
            "oz_per_feeding": oz_per_feeding,
            "oz_per_hour": round(oz_24h / 24, 2),
            "diapers_today": len(pn_today),
            "diapers_today_types": count_today,
            "diapers_per_day": round(len(pn) / days_pn, 1) if pn else None,
            "diaper_interval_h": round(median(ints_pn), 2) if len(ints_pn) >= 2 else None,
            "last_diaper": last_diaper,
            "last_pee": _parse(last_pee["ended_at"]) if last_pee else None,
            "last_poop": last_poop,
            "feedings_per_day": feedings_per_day,
            "bottle": bottle,
            "paused": paused,
            "bottles_today": bottles_today,
            "pct_finished": pct_finished,
            "wasted_7d": wasted_7d,
            "breast_milk_wasted_7d": breast_milk_wasted_7d,
            "breast_milk_today": breast_milk_today,
            "formula_today": formula_today,
            "pumped_today": pumped_today,
            "pumped_day": pumped_day,
            "stashes": stashes,
            "stash_oz": round(sum(b["remaining"] for b in current), 2),
            "next_expiry": _parse(next_expiry) if next_expiry else None,
            "series": series,
        }

    def _reference(self, rt: BabyRuntime, now: datetime, today: date, today_start: datetime, oz_today: float,
                    pediatrician_goal: float, next_feeding: datetime | None, series: list[dict[str, Any]],
                    first_day: date, feedings_goal: int) -> dict[str, Any]:
        """How much the baby should have had by this time, based on two daily goals: the pediatrician's and
        the weight-based reference (each day using the weight current on that day). The smaller one is the
        minimum and the larger one the ideal, so they swap on their own when the weight-based goal exceeds the pediatrician's."""
        pesos = [(_parse(m["date"]).date(), m["weight_kg"]) for m in self.db.measurements() if m["weight_kg"]]

        def metas(day: date) -> tuple[float, float, str | None]:
            current = [p for f, p in pesos if f <= day]
            per_weight = _per_weight(current[-1]) if current else None
            if per_weight is None:
                return pediatrician_goal, pediatrician_goal, None
            return min(per_weight, pediatrician_goal), max(per_weight, pediatrician_goal), (
                "weight" if per_weight <= pediatrician_goal else "pediatrician")

        for s in series:
            minimum, ideal, _ = metas(date.fromisoformat(s["date"]))
            s.update(goal_minimum=minimum, goal_ideal=ideal, achievement=_achievement(s["oz"], minimum, ideal))
        # Last 7 complete days (excluding today) since the first record
        dias7 = [s for s in series[-8:-1] if date.fromisoformat(s["date"]) >= first_day]

        minimum, ideal, source_minimum = metas(today)
        ended_at_today = dt_util.start_of_local_day(today + timedelta(days=1))
        # Intake is expected only while awake: the curve is flat overnight and reaches the goal at bedtime
        awake_day = _awake_seconds(rt, today_start, ended_at_today) or 1.0

        def expected(goal: float, when: datetime) -> float:
            return round(goal * min(1.0, _awake_seconds(rt, today_start, min(when, ended_at_today)) / awake_day), 1)

        expected_min, expected_ideal = expected(minimum, now), expected(ideal, now)
        # One-feeding margin: right before eating it is normal to be one feeding below the line
        margin = min(1.0, rt.prescribed_interval_h * 3600 / awake_day)
        if oz_today >= expected_ideal - ideal * margin:
            state = "ideal"
        elif oz_today >= expected_min - minimum * margin:
            state = "minimum"
        else:
            state = "behind"

        # Feedings left today according to the prescribed interval, starting from the next feeding (none overnight)
        slots = _plan_slots(rt, max(next_feeding, now) if next_feeding else now, ended_at_today)
        upcoming = [{"hhmm": w.isoformat(timespec="seconds"),
                     "minimum": expected(minimum, w), "ideal": expected(ideal, w)} for w in slots]
        n = len(upcoming)

        def per_feeding(goal: float) -> float | None:
            return round(max(0.0, goal - oz_today) / n, 2) if n else None

        return {
            "goal_minimum": minimum,
            "goal_ideal": ideal,
            "source_minimum": source_minimum,  # "weight", "pediatrician" or None (no weight logged)
            "expected_minimum": expected_min,
            "expected_ideal": expected_ideal,
            "diff_min": round(oz_today - expected_min, 1),
            "diff_ideal": round(oz_today - expected_ideal, 1),
            "state": state,
            "achievement_today": _achievement(oz_today, minimum, ideal),
            "feedings_remaining": n,
            "per_feeding_minimum": per_feeding(minimum),
            "per_feeding_ideal": per_feeding(ideal),
            # More than this per feeding is no longer "prepare a bit more": the goal is not chased by forcing
            "feeding_cap": round(ideal / feedings_goal + 1, 2),
            "next": upcoming,
            "days_7d": [{"date": s["date"], "oz": s["oz"], "achievement": s["achievement"]} for s in dias7],
            "days_minimum_7d": sum(s["achievement"] >= 1 for s in dias7),
            "days_ideal_7d": sum(s["achievement"] == 2 for s in dias7),
        }
