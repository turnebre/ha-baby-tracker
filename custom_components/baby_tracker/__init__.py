"""Baby Tracker integration: bottles, feedings, measurements and Kpis."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    CM_PER_IN,
    CONF_DB,
    CONF_UNIT,
    CONF_BABY_NAME,
    POOP_COLOR_DEFAULT,
    CONF_POOP_COLOR,
    CONF_POOP_CONSISTENCY,
    POOP_CONSISTENCY_DEFAULT,
    CONF_OZ_DEFAULT,
    CONF_TYPE_DEFAULT,
    POOP_COLORS,
    CONFIDENCES,
    POOP_CONSISTENCIES,
    DB_FILENAME,
    DOMAIN,
    EVENT_MEASUREMENT,
    EVENT_FEEDING,
    PRESCRIBED_INTERVAL_DEFAULT_H,
    ROOM_EXPIRY_DEFAULT_H,
    FRIDGE_EXPIRY_DEFAULT_DAYS,
    BOTTLE_LIMIT_DEFAULT_H,
    BREAST_MILK_LIMIT_DEFAULT_H,
    GOAL_OZ_DAY_DEFAULT,
    NIGHT_START_DEFAULT,
    NIGHT_END_DEFAULT,
    TYPES,
    DIAPER_TYPES,
    FUTURE_TOLERANCE_MIN,
    LOCATIONS,
    LB_PER_KG,
    LIVE_WINDOW_MIN,
)
from .coordinator import BabyCoordinator, BabyRuntime
from .db import BabyDB, BabyError
from .panel import async_update_panel

PLATFORMS = [Platform.NUMBER, Platform.SENSOR, Platform.TIME]

OZ = vol.All(vol.Coerce(float), vol.Range(min=0, max=12))
OZ_POS = vol.All(vol.Coerce(float), vol.Range(min=0.05, max=12))

LOG_FEEDING_SCHEMA = vol.Schema({
    vol.Optional("ended_at"): cv.datetime,
    vol.Optional("oz_taken"): OZ_POS,
    # "X was left in the bottle": the baby took what was left minus X (0 = finished what was left)
    vol.Optional("oz_leftover"): OZ,
    vol.Optional("new_bottle", default=False): cv.boolean,
    # Consecutive button taps: add to the last feeding if it was less than N seconds ago
    vol.Optional("accumulate_seconds", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=600)),
    vol.Optional("type"): vol.In(TYPES),
    # The feeding is from this stash bottle (it becomes the current bottle)
    vol.Optional("stash_id"): cv.positive_int,
    vol.Optional("pause_current", default=True): cv.boolean,
    vol.Optional("confidence", default="exact"): vol.In(CONFIDENCES),
    vol.Optional("source", default="manual"): cv.string,
    vol.Optional("note"): cv.string,
})

CORRECT_FEEDING_SCHEMA = vol.Schema({
    vol.Optional("id"): cv.positive_int,
    vol.Optional("ended_at"): cv.datetime,
    vol.Optional("oz_taken"): OZ_POS,
    vol.Optional("type"): vol.In(TYPES),
    vol.Optional("confidence"): vol.In(CONFIDENCES),
    vol.Optional("note"): cv.string,
    vol.Optional("move"): vol.In(["new", "previous"]),
})

ID_SCHEMA = vol.Schema({vol.Optional("id"): cv.positive_int})
ID_REQUIRED_SCHEMA = vol.Schema({vol.Required("id"): cv.positive_int})

NEW_BOTTLE_SCHEMA = vol.Schema({
    vol.Optional("oz"): OZ_POS,
    vol.Optional("type"): vol.In(TYPES),
})

CORRECT_BOTTLE_SCHEMA = vol.Schema({
    vol.Required("id"): cv.positive_int,
    vol.Optional("made_at"): cv.datetime,
    vol.Optional("location"): vol.In(LOCATIONS),
    vol.Optional("oz"): OZ_POS,
    vol.Optional("type"): vol.In(TYPES),
    vol.Optional("note"): cv.string,
    vol.Optional("reopen"): cv.boolean,
    # The bottle came from this stash milk (it is deducted from it)
    vol.Optional("stash_id"): cv.positive_int,
})

SAVE_MILK_SCHEMA = vol.Schema({
    vol.Required("oz"): OZ_POS,
    vol.Optional("made_at"): cv.datetime,
    vol.Optional("location", default="fridge"): vol.In(LOCATIONS),
    vol.Optional("note"): cv.string,
})

USE_STASH_SCHEMA = vol.Schema({
    vol.Optional("id"): cv.positive_int,
    # True: the current bottle is paused to continue later; False: it is tossed
    vol.Optional("pause_current", default=True): cv.boolean,
})

MOVE_STASH_SCHEMA = vol.Schema({
    vol.Required("id"): cv.positive_int,
    vol.Required("location"): vol.In(LOCATIONS),
})

PUMPING_SCHEMA = vol.Schema({
    vol.Optional("ended_at"): cv.datetime,
    vol.Optional("oz_left"): OZ,
    vol.Optional("oz_right"): OZ,
    vol.Optional("duration_min"): vol.All(vol.Coerce(float), vol.Range(min=0, max=180)),
    vol.Optional("note"): cv.string,
    # How it is split into stash bottles; if omitted, a single bottle with the total
    vol.Optional("bottles"): vol.All(cv.ensure_list, [OZ_POS]),
    vol.Optional("save", default=True): cv.boolean,
    vol.Optional("location", default="fridge"): vol.In(LOCATIONS),
})

DIAPER_SCHEMA = vol.Schema({
    vol.Required("type"): vol.In(DIAPER_TYPES),
    vol.Optional("ended_at"): cv.datetime,
    vol.Optional("color"): vol.In(POOP_COLORS),
    vol.Optional("consistency"): vol.In(POOP_CONSISTENCIES),
    vol.Optional("note"): cv.string,
    vol.Optional("source", default="manual"): cv.string,
})

CORRECT_DIAPER_SCHEMA = vol.Schema({
    vol.Required("id"): cv.positive_int,
    vol.Optional("type"): vol.In(DIAPER_TYPES),
    vol.Optional("ended_at"): cv.datetime,
    vol.Optional("color"): vol.In(POOP_COLORS),
    vol.Optional("consistency"): vol.In(POOP_CONSISTENCIES),
    vol.Optional("note"): cv.string,
})

LIST_SCHEMA = vol.Schema({
    vol.Required("since"): cv.datetime,
    vol.Required("until"): cv.datetime,
    vol.Optional("deleted", default=False): cv.boolean,
})

MILESTONE_SCHEMA = vol.Schema({
    vol.Required("milestone_id"): cv.string,
    # Day they noticed it; if omitted, today
    vol.Optional("date"): cv.date,
    vol.Optional("note"): cv.string,
})

MILESTONE_ID_SCHEMA = vol.Schema({vol.Required("milestone_id"): cv.string})

MEASUREMENT_SCHEMA = vol.Schema({
    vol.Optional("date"): cv.datetime,
    vol.Optional("weight_lb"): vol.All(vol.Coerce(float), vol.Range(min=1, max=66)),
    vol.Optional("height_in"): vol.All(vol.Coerce(float), vol.Range(min=8, max=51)),
    vol.Optional("head_in"): vol.All(vol.Coerce(float), vol.Range(min=8, max=24)),
    vol.Optional("note"): cv.string,
})


def _error(key: str, **data: Any) -> ServiceValidationError:
    """User-facing error, translated (the "exceptions" section of translations/*.json)."""
    return ServiceValidationError(
        translation_domain=DOMAIN, translation_key=key,
        translation_placeholders={k: str(v) for k, v in data.items()},
    )


def _local(value: datetime) -> datetime:
    """Times without a timezone are interpreted in the HA timezone."""
    return value.replace(tzinfo=dt_util.get_default_time_zone()) if value.tzinfo is None else value


def _a_utc(value: datetime | None, field: str, future_ok: bool = False) -> str | None:
    if value is None:
        return None
    value = _local(value)
    if not future_ok and value > dt_util.utcnow() + timedelta(minutes=FUTURE_TOLERANCE_MIN):
        raise _error("future_date", field=field, value=value.isoformat())
    return dt_util.as_utc(value).isoformat(timespec="seconds")


async def _user(hass: HomeAssistant, call: ServiceCall) -> str | None:
    if call.context.user_id and (u := await hass.auth.async_get_user(call.context.user_id)):
        return u.name
    return None


def _entry(hass: HomeAssistant, call: ServiceCall | None = None) -> ConfigEntry:
    """Baby the call is for: field "baby" (entry id or name); optional when there is only one baby."""
    babies: dict[str, ConfigEntry] = hass.data.get(DOMAIN, {}).get("babies", {})
    if not babies:
        raise _error("not_loaded")
    wanted = str(call.data.get("baby", "")).strip() if call else ""
    if not wanted:
        if len(babies) == 1:
            return next(iter(babies.values()))
        raise _error("several_babies", babies=", ".join(e.data[CONF_BABY_NAME] for e in babies.values()))
    if wanted in babies:
        return babies[wanted]
    for e in babies.values():
        if e.data[CONF_BABY_NAME].casefold() == wanted.casefold():
            return e
    raise _error("baby_not_found", baby=wanted)


def _runtime(hass: HomeAssistant, call: ServiceCall | None = None) -> BabyRuntime:
    return _entry(hass, call).runtime_data


async def _db(hass: HomeAssistant, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Runs a DB operation in the executor and translates validation errors."""
    try:
        return await hass.async_add_executor_job(lambda: fn(*args, **kwargs))
    except BabyError as err:
        raise _error(err.key, **err.data) from err


async def _after(hass: HomeAssistant, rt: BabyRuntime, action: str, data: dict[str, Any]) -> None:
    await rt.coordinator.async_refresh()
    entry = rt.coordinator.entry
    hass.bus.async_fire(EVENT_FEEDING, {"action": action, "baby": entry.entry_id,
                                      "name": entry.data[CONF_BABY_NAME], **data})


# ------------------------------------------------------------------ feedings
async def _log_feeding(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    d = call.data
    if "oz_taken" not in d and "oz_leftover" not in d:
        raise _error("missing_amount")
    ended_at_dt = _local(d.get("ended_at") or dt_util.now())
    ended_at = _a_utc(ended_at_dt, "ended_at")
    live = abs(dt_util.utcnow() - ended_at_dt) <= timedelta(minutes=LIVE_WINDOW_MIN)
    r = await _db(
        hass, rt.db.log,
        ended_at=ended_at, oz=d.get("oz_taken"), oz_leftover=d.get("oz_leftover"),
        type=d.get("type"), source=d["source"], confidence=d["confidence"],
        user=await _user(hass, call), note=d.get("note"),
        new_bottle=d["new_bottle"], accumulate_s=d["accumulate_seconds"],
        oz_default=rt.oz_default, lim=rt.limits, live=live, bottle_type=rt.type_default,
        stash_id=d.get("stash_id"), pause_current=d["pause_current"],
    )
    await _after(hass, rt, "logged", {"id": r["id"], "bottle_id": r["bottle"]["id"],
                                            "new_bottle": r["new_bottle"]})
    return r


async def _id_o_last(hass: HomeAssistant, rt: BabyRuntime, call: ServiceCall) -> int:
    if "id" in call.data:
        return call.data["id"]
    last = await _db(hass, rt.db.last_feeding)
    if not last:
        raise _error("no_feedings")
    return last["id"]


async def _correct_feeding(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    feeding_id = await _id_o_last(hass, rt, call)
    if not await _db(hass, rt.db.get_feeding, feeding_id):
        raise _error("feeding_not_found", id=feeding_id)
    changes = {k: v for k, v in call.data.items() if k in ("oz_taken", "type", "confidence", "note")}
    if "ended_at" in call.data:
        changes["ended_at"] = _a_utc(call.data["ended_at"], "ended_at")
    if changes:
        await _db(hass, rt.db.update_feeding, feeding_id, changes)
    if "move" in call.data:
        await _db(hass, rt.db.move_feeding, feeding_id, call.data["move"], rt.oz_default)
    feeding = await _db(hass, rt.db.get_feeding, feeding_id)
    bottle = (
        await _db(hass, rt.db.get_bottle, feeding["bottle_id"], rt.limits)
        if feeding.get("bottle_id") else None
    )
    await _after(hass, rt, "corrected", {"id": feeding_id})
    return {**feeding, "bottle": bottle}


async def _delete_feeding(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    feeding_id = await _id_o_last(hass, rt, call)
    feeding = await _db(hass, rt.db.get_feeding, feeding_id)
    if not feeding or not await _db(hass, rt.db.delete_feeding, feeding_id):
        raise _error("feeding_not_found", id=feeding_id)
    await _after(hass, rt, "deleted", {"id": feeding_id})
    return {"id": feeding_id, "oz_taken": feeding["oz_taken"], "ended_at": feeding["ended_at"]}


async def _restore_feeding(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    if "id" not in call.data:
        raise _error("missing_id_restore")
    if not await _db(hass, rt.db.restore_feeding, call.data["id"]):
        raise _error("feeding_not_deleted", id=call.data["id"])
    await _after(hass, rt, "restored", {"id": call.data["id"]})
    return {"id": call.data["id"]}


# ------------------------------------------------------------------ bottles
async def _new_bottle(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    r = await _db(hass, rt.db.new_bottle, call.data.get("oz", rt.oz_default),
                  call.data.get("type", rt.type_default), rt.limits)
    await _after(hass, rt, "new_bottle", {"bottle_id": r["bottle"]["id"]})
    return r


async def _resume_bottle(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    r = await _db(hass, rt.db.resume_bottle, call.data["id"], rt.limits)
    await _after(hass, rt, "bottle_resumed", {"bottle_id": call.data["id"]})
    return r


async def _close_bottle(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    b = await _db(hass, rt.db.close_bottle, call.data.get("id"), rt.limits)
    await _after(hass, rt, "bottle_closed", {"bottle_id": b["id"]})
    return b


async def _delete_bottle(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    r = await _db(hass, rt.db.delete_bottle, call.data["id"])
    await _after(hass, rt, "bottle_deleted", {"bottle_id": call.data["id"]})
    return r


async def _correct_bottle(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    changes = {k: v for k, v in call.data.items() if k != "id"}
    if "made_at" in changes:
        changes["made_at"] = _a_utc(changes["made_at"], "made_at")
    b = await _db(hass, rt.db.correct_bottle, call.data["id"], changes, rt.limits)
    await _after(hass, rt, "bottle_corrected", {"bottle_id": b["id"]})
    return b


# ------------------------------------------------------------------ breast milk
async def _save_milk(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    made_at = _a_utc(call.data.get("made_at") or dt_util.now(), "made_at")
    b = await _db(hass, rt.db.save_milk, call.data["oz"], made_at, call.data["location"],
                  rt.limits, None, call.data.get("note"))
    await _after(hass, rt, "stash", {"bottle_id": b["id"]})
    return b


async def _use_stash(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    r = await _db(hass, rt.db.use_stash, call.data.get("id"), rt.limits, call.data["pause_current"])
    await _after(hass, rt, "new_bottle", {"bottle_id": r["bottle"]["id"]})
    return r


async def _move_stash(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    b = await _db(hass, rt.db.move_stash, call.data["id"], call.data["location"], rt.limits)
    await _after(hass, rt, "stash", {"bottle_id": b["id"]})
    return b


async def _discard_stash(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    b = await _db(hass, rt.db.discard_stash, call.data["id"], rt.limits)
    await _after(hass, rt, "stash", {"bottle_id": b["id"]})
    return b


async def _log_pumping(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    d = call.data
    total = (d.get("oz_left") or 0) + (d.get("oz_right") or 0)
    bottles = d.get("bottles") or ([total] if total > 0 else [])
    r = await _db(
        hass, rt.db.log_pumping,
        ended_at=_a_utc(d.get("ended_at") or dt_util.now(), "ended_at"), oz_left=d.get("oz_left"), oz_right=d.get("oz_right"),
        duration_min=d.get("duration_min"), note=d.get("note"), user=await _user(hass, call),
        bottles=bottles if d["save"] else [], location=d["location"], lim=rt.limits,
    )
    await _after(hass, rt, "pumping", {"id": r["id"]})
    return r


async def _delete_pumping(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    if not await _db(hass, rt.db.delete_pumping, call.data["id"]):
        raise _error("pumping_not_found", id=call.data["id"])
    await _after(hass, rt, "pumping", {"id": call.data["id"]})
    return {"id": call.data["id"]}


# ------------------------------------------------------------------ diapers
async def _log_diaper(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    d: dict[str, Any] = dict(call.data)
    d["ended_at"] = _a_utc(d.get("ended_at") or dt_util.now(), "ended_at")
    if d["type"] == "pee":  # color and consistency only apply to poop
        d.pop("color", None)
        d.pop("consistency", None)
    else:  # if not given, the "normal" poop configured for the baby is used
        data = _entry(hass, call).data
        d.setdefault("color", data.get(CONF_POOP_COLOR, POOP_COLOR_DEFAULT))
        d.setdefault("consistency", data.get(CONF_POOP_CONSISTENCY, POOP_CONSISTENCY_DEFAULT))
    d["logged_by"] = await _user(hass, call)
    p = await _db(hass, rt.db.add_diaper, d)
    await _after(hass, rt, "diaper", {"id": p["id"], "type": p["type"]})
    return p


async def _correct_diaper(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    changes = {k: v for k, v in call.data.items() if k != "id"}
    if "ended_at" in changes:
        changes["ended_at"] = _a_utc(changes["ended_at"], "ended_at")
    p = await _db(hass, rt.db.update_diaper, call.data["id"], changes)
    await _after(hass, rt, "diaper", {"id": p["id"], "type": p["type"]})
    return p


async def _delete_diaper(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    if not await _db(hass, rt.db.delete_diaper, call.data["id"]):
        raise _error("diaper_not_found", id=call.data["id"])
    await _after(hass, rt, "diaper", {"id": call.data["id"]})
    return {"id": call.data["id"]}


async def _list_diapers(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    since, until = _range(call)
    return {"diapers": await _db(hass, rt.db.diapers_range, since, until)}


# ------------------------------------------------------------------ queries
def _range(call: ServiceCall) -> tuple[str, str]:
    return (_a_utc(call.data["since"], "since", future_ok=True),
            _a_utc(call.data["until"], "until", future_ok=True))


async def _list_feedings(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    since, until = _range(call)
    return {"feedings": await _db(hass, rt.db.feedings_range, since, until, call.data["deleted"])}


async def _list_stashes(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    return {"stashes": await _db(hass, rt.db.stashes, rt.limits)}


async def _list_pumpings(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    since, until = _range(call)
    return {"pumpings": await _db(hass, rt.db.pumpings_range, since, until)}


async def _list_bottles(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    since, until = _range(call)
    return {"bottles": await _db(hass, rt.db.bottles_range, since, until, rt.limits)}


# ------------------------------------------------------------------ developmental milestones
def _leer_ids_milestones() -> set[str]:
    catalog = json.loads((Path(__file__).parent / "www" / "milestones.json").read_text(encoding="utf-8"))
    return {step["id"] for skill in catalog["skills"] for step in skill["steps"]}


async def _validate_milestone(hass: HomeAssistant, milestone_id: str) -> None:
    data = hass.data[DOMAIN]
    if "milestones_ids" not in data:
        data["milestones_ids"] = await hass.async_add_executor_job(_leer_ids_milestones)
    if milestone_id not in data["milestones_ids"]:
        raise _error("milestone_not_found", id=milestone_id)


async def _mark_milestone(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    d = call.data
    await _validate_milestone(hass, d["milestone_id"])
    date = d.get("date") or dt_util.now().date()
    if date > dt_util.now().date():
        raise _error("future_date", field="date", value=date.isoformat())
    return await _db(hass, rt.db.mark_milestone, d["milestone_id"], date.isoformat(), d.get("note"), await _user(hass, call))


async def _unmark_milestone(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    await _validate_milestone(hass, call.data["milestone_id"])
    return {"milestone_id": call.data["milestone_id"], "unmarked": await _db(hass, rt.db.unmark_milestone, call.data["milestone_id"])}


async def _list_milestones(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    return {"milestones": await _db(hass, rt.db.milestones)}


# ------------------------------------------------------------------ measurements
async def _log_measurement(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    d: dict[str, Any] = dict(call.data)
    if not any(k in d for k in ("weight_lb", "height_in", "head_in")):
        raise _error("missing_measurement")
    d["date"] = _a_utc(d.get("date") or dt_util.now(), "date")
    d["logged_by"] = await _user(hass, call)
    stored = {k: v for k, v in d.items() if k not in ("weight_lb", "height_in", "head_in")}
    if "weight_lb" in d:
        stored["weight_kg"] = round(d["weight_lb"] / LB_PER_KG, 4)
    if "height_in" in d:
        stored["height_cm"] = round(d["height_in"] * CM_PER_IN, 3)
    if "head_in" in d:
        stored["head_cm"] = round(d["head_in"] * CM_PER_IN, 3)
    measurement_id = await _db(hass, rt.db.add_measurement, stored)
    await rt.coordinator.async_refresh()
    hass.bus.async_fire(EVENT_MEASUREMENT, {"id": measurement_id, "baby": rt.coordinator.entry.entry_id, **d})
    return {"id": measurement_id}


def _imperial(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a stored (kg/cm) measurement row to lb/in for the API."""
    out = {k: v for k, v in row.items() if k not in ("weight_kg", "height_cm", "head_cm")}
    for src, dst, factor in (("weight_kg", "weight_lb", LB_PER_KG), ("height_cm", "height_in", 1 / CM_PER_IN),
                             ("head_cm", "head_in", 1 / CM_PER_IN)):
        out[dst] = round(row[src] * factor, 2) if row.get(src) is not None else None
    return out


async def _list_measurements(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    rows = await _db(hass, rt.db.measurements)
    return {"measurements": [_imperial(r) for r in rows]}


async def _delete_measurement(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    rt = _runtime(hass, call)
    if not await _db(hass, rt.db.delete_measurement, call.data["id"]):
        raise _error("measurement_not_found", id=call.data["id"])
    await rt.coordinator.async_refresh()
    return {"id": call.data["id"]}


Handler = Callable[[HomeAssistant, ServiceCall], Awaitable[ServiceResponse]]

SERVICES: dict[str, tuple[Handler, vol.Schema]] = {
    "log_feeding": (_log_feeding, LOG_FEEDING_SCHEMA),
    "correct_feeding": (_correct_feeding, CORRECT_FEEDING_SCHEMA),
    "delete_feeding": (_delete_feeding, ID_SCHEMA),
    "restore_feeding": (_restore_feeding, ID_SCHEMA),
    "new_bottle": (_new_bottle, NEW_BOTTLE_SCHEMA),
    "close_bottle": (_close_bottle, ID_SCHEMA),
    "resume_bottle": (_resume_bottle, ID_REQUIRED_SCHEMA),
    "delete_bottle": (_delete_bottle, ID_REQUIRED_SCHEMA),
    "correct_bottle": (_correct_bottle, CORRECT_BOTTLE_SCHEMA),
    "save_milk": (_save_milk, SAVE_MILK_SCHEMA),
    "use_stash": (_use_stash, USE_STASH_SCHEMA),
    "move_stash": (_move_stash, MOVE_STASH_SCHEMA),
    "discard_stash": (_discard_stash, ID_REQUIRED_SCHEMA),
    "log_pumping": (_log_pumping, PUMPING_SCHEMA),
    "delete_pumping": (_delete_pumping, ID_REQUIRED_SCHEMA),
    "log_diaper": (_log_diaper, DIAPER_SCHEMA),
    "correct_diaper": (_correct_diaper, CORRECT_DIAPER_SCHEMA),
    "delete_diaper": (_delete_diaper, ID_REQUIRED_SCHEMA),
    "log_measurement": (_log_measurement, MEASUREMENT_SCHEMA),
    "delete_measurement": (_delete_measurement, ID_REQUIRED_SCHEMA),
    "mark_milestone": (_mark_milestone, MILESTONE_SCHEMA),
    "unmark_milestone": (_unmark_milestone, MILESTONE_ID_SCHEMA),
}
QUERIES: dict[str, tuple[Handler, vol.Schema]] = {
    "list_feedings": (_list_feedings, LIST_SCHEMA),
    "list_bottles": (_list_bottles, LIST_SCHEMA),
    "list_stashes": (_list_stashes, vol.Schema({})),
    "list_pumpings": (_list_pumpings, LIST_SCHEMA.extend({vol.Optional("deleted"): cv.boolean})),
    "list_measurements": (_list_measurements, vol.Schema({})),
    "list_milestones": (_list_milestones, vol.Schema({})),
    "list_diapers": (_list_diapers, LIST_SCHEMA.extend({vol.Optional("deleted"): cv.boolean})),
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Each baby has their own database; the first one uses baby_tracker.db
    db = BabyDB(hass.config.path(entry.data.get(CONF_DB, DB_FILENAME)))
    await hass.async_add_executor_job(db.initialize)
    # The per-feeding goal was replaced by a daily goal: drop the orphaned entity
    registry = er.async_get(hass)
    if old := registry.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_goal_oz_feeding"):
        registry.async_remove(old)
    coordinator = BabyCoordinator(hass, entry, db)
    entry.runtime_data = BabyRuntime(
        db=db,
        coordinator=coordinator,
        oz_default=entry.data[CONF_OZ_DEFAULT],
        type_default=entry.data[CONF_TYPE_DEFAULT],
        goal_oz_day=GOAL_OZ_DAY_DEFAULT,
        prescribed_interval_h=PRESCRIBED_INTERVAL_DEFAULT_H,
        night_start=NIGHT_START_DEFAULT,
        night_end=NIGHT_END_DEFAULT,
        bottle_limit_h=BOTTLE_LIMIT_DEFAULT_H,
        breast_milk_limit_h=BREAST_MILK_LIMIT_DEFAULT_H,
        room_expiry_h=ROOM_EXPIRY_DEFAULT_H,
        fridge_expiry_days=FRIDGE_EXPIRY_DEFAULT_DAYS,
    )
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    babies = hass.data.setdefault(DOMAIN, {}).setdefault("babies", {})
    babies[entry.entry_id] = entry
    # Actions belong to the domain: they are registered once for all babies
    if not hass.services.has_service(DOMAIN, "log_feeding"):
        for group, support in ((SERVICES, SupportsResponse.OPTIONAL), (QUERIES, SupportsResponse.ONLY)):
            for name, (fn, schema) in group.items():
                async def _handler(call: ServiceCall, fn: Handler = fn) -> ServiceResponse:
                    r = await fn(hass, call)
                    if isinstance(r, dict):
                        # Baby details in every response (for blueprints and notifications)
                        e = _entry(hass, call)
                        r = {**r, "baby": e.entry_id, "name": e.data[CONF_BABY_NAME],
                             "unit": e.data.get(CONF_UNIT, "oz")}
                    return r
                hass.services.async_register(
                    DOMAIN, name, _handler, schema=schema.extend({vol.Optional("baby"): cv.string}),
                    supports_response=support,
                )
    await async_update_panel(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        babies = hass.data.get(DOMAIN, {}).get("babies", {})
        babies.pop(entry.entry_id, None)
        if not babies:
            for name in list(hass.services.async_services_for_domain(DOMAIN)):
                hass.services.async_remove(DOMAIN, name)
        await async_update_panel(hass)
    return ok
