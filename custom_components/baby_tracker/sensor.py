"""KPI sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CM_PER_IN, LB_PER_KG, ML_PER_OZ
from .coordinator import BabyCoordinator
from .entity import device_info


def _last(d: dict[str, Any], field: str) -> Any:
    return d["last"][field] if d["last"] else None


def _attrs_last(d: dict[str, Any]) -> dict[str, Any]:
    u = d["last"]
    if not u:
        return {}
    return {k: u[k] for k in (
        "id", "oz_taken", "oz_prepared", "oz_leftover", "type",
        "confidence", "source", "logged_by", "note",
    )}


@dataclass(frozen=True, kw_only=True)
class BabySensorDescription(SensorEntityDescription):
    value: Callable[[dict[str, Any]], Any]
    attributes: Callable[[dict[str, Any]], dict[str, Any]] | None = None


SENSORS: tuple[BabySensorDescription, ...] = (
    BabySensorDescription(
        key="last_feeding", translation_key="last_feeding", icon="mdi:baby-bottle",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda d: d["last_ended_at"], attributes=_attrs_last,
    ),
    BabySensorDescription(
        key="last_feeding_oz", translation_key="last_feeding_oz", icon="mdi:cup-water",
        native_unit_of_measurement="oz", suggested_display_precision=2,
        value=lambda d: _last(d, "oz_taken"),
    ),
    BabySensorDescription(
        key="next_feeding", translation_key="next_feeding", icon="mdi:clock-outline",
        device_class=SensorDeviceClass.TIMESTAMP, value=lambda d: d["next"],
    ),
    BabySensorDescription(
        key="oz_today", translation_key="oz_today", icon="mdi:baby-bottle-outline",
        native_unit_of_measurement="oz", state_class=SensorStateClass.TOTAL,
        suggested_display_precision=1,
        value=lambda d: d["oz_today"],
        attributes=lambda d: {
            "ml": round(d["oz_today"] * ML_PER_OZ),
            "feedings_exact": d["exact_today"],
            "series_daily": d["series"],
        },
    ),
    BabySensorDescription(
        key="feedings_today", translation_key="feedings_today", icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT, value=lambda d: d["feedings_today"],
    ),
    BabySensorDescription(
        key="oz_24h", translation_key="oz_24h", icon="mdi:history",
        native_unit_of_measurement="oz", state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1, value=lambda d: d["oz_24h"],
    ),
    BabySensorDescription(
        key="average_7d", translation_key="average_7d", icon="mdi:chart-line",
        native_unit_of_measurement="oz", state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1, value=lambda d: d["average_7d"],
    ),
    BabySensorDescription(
        key="interval", translation_key="interval", icon="mdi:timer-sand",
        native_unit_of_measurement=UnitOfTime.HOURS, device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
        value=lambda d: d["interval_h"],
    ),
    BabySensorDescription(
        key="goal_oz_day", translation_key="goal_oz_day", icon="mdi:target",
        native_unit_of_measurement="oz", suggested_display_precision=1,
        value=lambda d: d["goal_oz_day"],
        attributes=lambda d: {
            "source": "pediatrician guidance (daily goal)",
            "feedings_per_day": d["feedings_goal"],
            "planned_oz_feeding": d["planned_oz_feeding"],
            "night_start": d["night_start"],
            "night_end": d["night_end"],
            "reference_per_weight_oz_day": d["reference_weight_oz_day"],
        },
    ),
    BabySensorDescription(
        key="goal_progress", translation_key="goal_progress", icon="mdi:progress-check",
        native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d["goal_progress"],
    ),
    BabySensorDescription(
        # How much the baby should have had by now (minimum goal); the ideal and the plan go in attributes
        key="reference_now", translation_key="reference_now", icon="mdi:chart-timeline-variant",
        native_unit_of_measurement="oz", state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1, value=lambda d: d["reference"]["expected_minimum"],
        attributes=lambda d: {k: v for k, v in d["reference"].items() if k != "expected_minimum"},
    ),
    BabySensorDescription(
        key="weight", translation_key="weight", device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.POUNDS, suggested_display_precision=2,
        value=lambda d: round(d["weight"]["weight_kg"] * LB_PER_KG, 3) if d["weight"] else None,
        attributes=lambda d: {"date": d["weight"]["date"]} if d["weight"] else {},
    ),
    BabySensorDescription(
        key="height", translation_key="height", device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.INCHES, suggested_display_precision=1,
        value=lambda d: round(d["height"]["height_cm"] / CM_PER_IN, 2) if d["height"] else None,
        attributes=lambda d: {"date": d["height"]["date"]} if d["height"] else {},
    ),
    BabySensorDescription(
        key="bottle_remaining", translation_key="bottle_remaining", icon="mdi:baby-bottle",
        native_unit_of_measurement="oz", suggested_display_precision=2,
        value=lambda d: d["bottle"]["remaining"] if d["bottle"] else None,
        attributes=lambda d: {
            **({k: d["bottle"][k] for k in (
                "id", "type", "oz", "consumed", "n_feedings", "prepared_at", "first_feeding", "use_by", "past_use_by", "state",
            )} if d["bottle"] else {}),
            "paused": [{k: b[k] for k in ("id", "type", "oz", "consumed", "remaining", "first_feeding", "use_by", "past_use_by")}
                         for b in d["paused"]],
        },
    ),
    BabySensorDescription(
        key="bottle_use_by", translation_key="bottle_use_by", icon="mdi:timer-alert-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda d: dt_util.parse_datetime(d["bottle"]["use_by"])
        if d["bottle"] and d["bottle"]["use_by"] else None,
    ),
    BabySensorDescription(
        key="oz_per_feeding", translation_key="oz_per_feeding", icon="mdi:cup-water",
        native_unit_of_measurement="oz", state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2, value=lambda d: d["oz_per_feeding"],
    ),
    BabySensorDescription(
        key="feedings_per_day", translation_key="feedings_per_day", icon="mdi:repeat",
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
        value=lambda d: d["feedings_per_day"],
    ),
    BabySensorDescription(
        key="bottles_today", translation_key="bottles_today", icon="mdi:baby-bottle-outline",
        state_class=SensorStateClass.MEASUREMENT, value=lambda d: d["bottles_today"],
    ),
    BabySensorDescription(
        key="pct_finished", translation_key="pct_finished", icon="mdi:check-circle-outline",
        native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT,
        value=lambda d: d["pct_finished"],
    ),
    BabySensorDescription(
        key="wasted_7d", translation_key="wasted_7d", icon="mdi:delete-outline",
        native_unit_of_measurement="oz", state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1, value=lambda d: d["wasted_7d"],
    ),
    BabySensorDescription(
        key="breast_milk_today", translation_key="breast_milk_today", icon="mdi:mother-nurse",
        native_unit_of_measurement="oz", state_class=SensorStateClass.TOTAL,
        suggested_display_precision=1, value=lambda d: d["breast_milk_today"],
    ),
    BabySensorDescription(
        key="formula_today", translation_key="formula_today", icon="mdi:baby-bottle",
        native_unit_of_measurement="oz", state_class=SensorStateClass.TOTAL,
        suggested_display_precision=1, value=lambda d: d["formula_today"],
    ),
    BabySensorDescription(
        key="pumped_today", translation_key="pumped_today", icon="mdi:water-plus",
        native_unit_of_measurement="oz", state_class=SensorStateClass.TOTAL,
        suggested_display_precision=1, value=lambda d: d["pumped_today"],
    ),
    BabySensorDescription(
        key="pumped_day", translation_key="pumped_day", icon="mdi:chart-line",
        native_unit_of_measurement="oz", state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1, value=lambda d: d["pumped_day"],
    ),
    BabySensorDescription(
        key="stash_oz", translation_key="stash_oz", icon="mdi:fridge-outline",
        native_unit_of_measurement="oz", state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1, value=lambda d: d["stash_oz"],
        attributes=lambda d: {
            "bottles": [{k: b[k] for k in ("id", "oz", "location", "made_at", "expires_at", "expired")}
                          for b in d["stashes"]],
            "current": sum(1 for b in d["stashes"] if not b["expired"]),
            "expired": sum(1 for b in d["stashes"] if b["expired"]),
        },
    ),
    BabySensorDescription(
        key="stash_expires", translation_key="stash_expires", icon="mdi:timer-sand-complete",
        device_class=SensorDeviceClass.TIMESTAMP, value=lambda d: d["next_expiry"],
    ),
    BabySensorDescription(
        key="breast_milk_wasted_7d", translation_key="breast_milk_wasted_7d", icon="mdi:delete-outline",
        native_unit_of_measurement="oz", state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1, value=lambda d: d["breast_milk_wasted_7d"],
    ),
    BabySensorDescription(
        key="oz_per_hour", translation_key="oz_per_hour", icon="mdi:speedometer",
        native_unit_of_measurement="oz/h", state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2, value=lambda d: d["oz_per_hour"],
        attributes=lambda d: {"goal_oz_hour": round(d["goal_oz_day"] / d["awake_hours"], 2)
                              if d["goal_oz_day"] and d["awake_hours"] else None},
    ),
    BabySensorDescription(
        key="last_diaper", translation_key="last_diaper", icon="mdi:human-baby-changing-table",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda d: dt_util.parse_datetime(d["last_diaper"]["ended_at"]) if d["last_diaper"] else None,
        attributes=lambda d: {k: d["last_diaper"][k] for k in ("id", "type", "color", "consistency", "logged_by")}
        if d["last_diaper"] else {},
    ),
    BabySensorDescription(
        key="last_pee", translation_key="last_pee", icon="mdi:water",
        device_class=SensorDeviceClass.TIMESTAMP, value=lambda d: d["last_pee"],
    ),
    BabySensorDescription(
        key="last_poop", translation_key="last_poop", icon="mdi:emoticon-poop",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda d: dt_util.parse_datetime(d["last_poop"]["ended_at"]) if d["last_poop"] else None,
        attributes=lambda d: {k: d["last_poop"][k] for k in ("color", "consistency")} if d["last_poop"] else {},
    ),
    BabySensorDescription(
        key="diapers_today", translation_key="diapers_today", icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT, value=lambda d: d["diapers_today"],
        attributes=lambda d: d["diapers_today_types"],
    ),
    BabySensorDescription(
        key="diapers_per_day", translation_key="diapers_per_day", icon="mdi:chart-bar",
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
        value=lambda d: d["diapers_per_day"],
    ),
    BabySensorDescription(
        key="diaper_interval", translation_key="diaper_interval", icon="mdi:timer-sand",
        native_unit_of_measurement=UnitOfTime.HOURS, device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
        value=lambda d: d["diaper_interval_h"],
    ),
    BabySensorDescription(
        key="age", translation_key="age", icon="mdi:cake-variant",
        native_unit_of_measurement=UnitOfTime.DAYS, value=lambda d: d["age_days"],
        attributes=lambda d: {"name": d["name"], "birth": d["birth"], "sex": d["sex"], "unit": d["unit"],
                                      "growth_unit": d["growth_unit"]},
    ),
)


# Growth sensors in kg/cm for babies whose growth unit is metric (the database already stores kg/cm)
METRIC_GROWTH: dict[str, dict[str, Any]] = {
    "weight": {
        "native_unit_of_measurement": UnitOfMass.KILOGRAMS, "suggested_display_precision": 2,
        "value": lambda d: round(d["weight"]["weight_kg"], 3) if d["weight"] else None,
    },
    "height": {
        "native_unit_of_measurement": UnitOfLength.CENTIMETERS, "suggested_display_precision": 1,
        "value": lambda d: round(d["height"]["height_cm"], 1) if d["height"] else None,
    },
}


def _metric(desc: BabySensorDescription) -> BabySensorDescription:
    return replace(desc, **METRIC_GROWTH[desc.key]) if desc.key in METRIC_GROWTH else desc


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    metric = coordinator.data["growth_unit"] == "metric"
    async_add_entities(
        BabySensor(coordinator, entry, _metric(desc) if metric else desc) for desc in SENSORS
    )


# Sensors that carry baby_id / name / unit (the ones the blueprints use)
WITH_BABY_DATA = {"last_feeding", "next_feeding", "stash_oz", "stash_expires", "bottle_remaining", "last_diaper"}


class BabySensor(CoordinatorEntity[BabyCoordinator], SensorEntity):
    _attr_has_entity_name = True
    # The daily series is large and already lives in the baby database; do not duplicate it in the HA history
    _unrecorded_attributes = frozenset({"series_daily"})
    entity_description: BabySensorDescription

    def __init__(self, coordinator: BabyCoordinator, entry: ConfigEntry,
                 desc: BabySensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = desc
        self._attr_unique_id = f"{entry.entry_id}_{desc.key}"
        self._attr_device_info = device_info(entry)
        self._entry_id = entry.entry_id

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attrs = dict(self.entity_description.attributes(self.coordinator.data)) if self.entity_description.attributes else {}
        if self.entity_description.key in WITH_BABY_DATA:
            # For blueprints: which baby the sensor belongs to and which unit to show amounts in
            d = self.coordinator.data
            attrs.update({"baby_id": self._entry_id, "name": d["name"], "unit": d["unit"]})
        return attrs or None
