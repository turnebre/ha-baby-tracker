"""Values adjustable from the UI: oz per bottle and the pediatrician's guidance."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import device_info


@dataclass(frozen=True, kw_only=True)
class BabyNumberDescription(NumberEntityDescription):
    # BabyRuntime attribute that mirrors this value
    field: str


NUMBERS: tuple[BabyNumberDescription, ...] = (
    BabyNumberDescription(
        key="oz_per_bottle", translation_key="oz_per_bottle", field="oz_default",
        icon="mdi:baby-bottle-outline", native_min_value=0.5, native_max_value=10,
        native_step=0.5, native_unit_of_measurement="oz", mode=NumberMode.BOX,
    ),
    BabyNumberDescription(
        key="daily_goal", translation_key="daily_goal", field="goal_oz_day",
        icon="mdi:target", native_min_value=4, native_max_value=50,
        native_step=0.5, native_unit_of_measurement="oz", mode=NumberMode.BOX,
    ),
    BabyNumberDescription(
        key="prescribed_interval", translation_key="prescribed_interval",
        field="prescribed_interval_h", icon="mdi:timer-cog-outline",
        native_min_value=1, native_max_value=6, native_step=0.5,
        native_unit_of_measurement=UnitOfTime.HOURS, mode=NumberMode.BOX,
    ),
    BabyNumberDescription(
        key="bottle_limit", translation_key="bottle_limit", field="bottle_limit_h",
        icon="mdi:timer-alert-outline", native_min_value=0.5, native_max_value=4, native_step=0.25,
        native_unit_of_measurement=UnitOfTime.HOURS, mode=NumberMode.BOX,
    ),
    BabyNumberDescription(
        key="breast_milk_limit", translation_key="breast_milk_limit", field="breast_milk_limit_h",
        icon="mdi:mother-nurse", native_min_value=0.5, native_max_value=4, native_step=0.25,
        native_unit_of_measurement=UnitOfTime.HOURS, mode=NumberMode.BOX,
    ),
    BabyNumberDescription(
        key="room_expiry", translation_key="room_expiry", field="room_expiry_h",
        icon="mdi:thermometer", native_min_value=0.5, native_max_value=8, native_step=0.5,
        native_unit_of_measurement=UnitOfTime.HOURS, mode=NumberMode.BOX,
    ),
    BabyNumberDescription(
        key="fridge_expiry", translation_key="fridge_expiry", field="fridge_expiry_days",
        icon="mdi:fridge-outline", native_min_value=0.5, native_max_value=8, native_step=0.5,
        native_unit_of_measurement=UnitOfTime.DAYS, mode=NumberMode.BOX,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(BabyNumber(entry, desc) for desc in NUMBERS)


class BabyNumber(RestoreNumber):
    _attr_has_entity_name = True
    entity_description: BabyNumberDescription

    def __init__(self, entry: ConfigEntry, desc: BabyNumberDescription) -> None:
        self._entry = entry
        self.entity_description = desc
        self._attr_unique_id = f"{entry.entry_id}_{desc.key}"
        self._attr_device_info = device_info(entry)
        self._attr_native_value = getattr(entry.runtime_data, desc.field)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) and last.native_value:
            await self.async_set_native_value(last.native_value)

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        setattr(self._entry.runtime_data, self.entity_description.field, value)
        self.async_write_ha_state()
        # The goal and the next feeding depend on these values
        await self._entry.runtime_data.coordinator.async_refresh()
