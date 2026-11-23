"""Sidebar panel "Baby Tracker": a single one, with a selector when there are several babies."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    POOP_COLOR_DEFAULT, CONF_POOP_COLOR, CONF_POOP_CONSISTENCY, CONF_BIRTH_DATE, CONF_BABY_NAME,
    CONF_GROWTH_UNIT, CONF_SEX, CONF_UNIT, GROWTH_UNIT_DEFAULT, POOP_CONSISTENCY_DEFAULT, DOMAIN, PROJECT_NAME,
)

PANEL_URL = "baby-tracker"
STATIC_URL = "/baby_tracker_static"
WWW = Path(__file__).parent / "www"
ENTITY_KEYS = {
    "sensor": ["last_feeding", "next_feeding", "oz_today", "feedings_today", "oz_24h", "average_7d",
               "interval", "goal_oz_day", "goal_progress", "weight", "height", "age",
               "bottle_remaining", "bottle_use_by", "oz_per_feeding", "feedings_per_day",
               "bottles_today", "pct_finished", "wasted_7d", "breast_milk_today", "formula_today",
               "pumped_today", "pumped_day", "stash_oz", "stash_expires", "breast_milk_wasted_7d",
               "oz_per_hour", "reference_now", "last_diaper", "last_pee", "last_poop", "diapers_today",
               "diapers_per_day", "diaper_interval"],
    "number": ["oz_per_bottle", "daily_goal", "prescribed_interval", "bottle_limit",
               "breast_milk_limit", "room_expiry", "fridge_expiry"],
    "time": ["night_start", "night_end"],
}


def _version() -> str:
    # Changes whenever the JS changes, so the browser/app does not use a stale copy
    return hashlib.md5((WWW / "baby-tracker-panel.js").read_bytes()).hexdigest()[:8]


def _config_baby(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    reg = er.async_get(hass)
    d = entry.data
    return {
        "entry_id": entry.entry_id,
        "name": d[CONF_BABY_NAME],
        "birth": d[CONF_BIRTH_DATE],
        "sex": d.get(CONF_SEX, "unspecified"),
        "unit": d.get(CONF_UNIT, "oz"),
        "growth_unit": d.get(CONF_GROWTH_UNIT, GROWTH_UNIT_DEFAULT),
        "poop_color": d.get(CONF_POOP_COLOR, POOP_COLOR_DEFAULT),
        "poop_consistency": d.get(CONF_POOP_CONSISTENCY, POOP_CONSISTENCY_DEFAULT),
        "entities": {
            key: reg.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")
            for domain, keys in ENTITY_KEYS.items() for key in keys
        },
    }


async def async_update_panel(hass: HomeAssistant) -> None:
    """(Re)registers the panel with all loaded babies; removes it if none are left."""
    data = hass.data.setdefault(DOMAIN, {})
    # Babies load and unload concurrently: two registrations of the same URL would make HA reject the second
    async with data.setdefault("panel_lock", asyncio.Lock()):
        await _update_panel(hass, data)


async def _update_panel(hass: HomeAssistant, data: dict) -> None:
    babies: dict[str, ConfigEntry] = data.setdefault("babies", {})
    if PANEL_URL in hass.data.get(getattr(frontend, "DATA_PANELS", "frontend_panels"), {}):
        frontend.async_remove_panel(hass, PANEL_URL)
    if not babies:
        return
    if not data.get("static"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(WWW), cache_headers=False)]
        )
        data["static"] = True
    version = await hass.async_add_executor_job(_version)
    list = sorted((_config_baby(hass, e) for e in babies.values()), key=lambda b: b["birth"])
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="baby-tracker-panel",
        frontend_url_path=PANEL_URL,
        module_url=f"{STATIC_URL}/baby-tracker-panel.js?v={version}",
        sidebar_title=PROJECT_NAME,
        sidebar_icon="mdi:baby-bottle",
        require_admin=False,
        config={"project": PROJECT_NAME, "babies": list},
    )
