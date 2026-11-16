"""Bedtime and wake-up: no feedings are expected between them."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import device_info


@dataclass(frozen=True, kw_only=True)
class BabyTimeDescription(TimeEntityDescription):
    # BabyRuntime attribute that mirrors this value
    field: str


TIMES: tuple[BabyTimeDescription, ...] = (
    BabyTimeDescription(key="night_start", translation_key="night_start", field="night_start",
                        icon="mdi:weather-night"),
    BabyTimeDescription(key="night_end", translation_key="night_end", field="night_end",
                        icon="mdi:weather-sunset-up"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(BabyTime(entry, desc) for desc in TIMES)


class BabyTime(TimeEntity, RestoreEntity):
    _attr_has_entity_name = True
    entity_description: BabyTimeDescription

    def __init__(self, entry: ConfigEntry, desc: BabyTimeDescription) -> None:
        self._entry = entry
        self.entity_description = desc
        self._attr_unique_id = f"{entry.entry_id}_{desc.key}"
        self._attr_device_info = device_info(entry)
        self._attr_native_value = getattr(entry.runtime_data, desc.field)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state not in ("unknown", "unavailable"):
            try:
                await self.async_set_value(time.fromisoformat(last.state))
            except ValueError:
                pass

    async def async_set_value(self, value: time) -> None:
        value = value.replace(second=0, microsecond=0)
        self._attr_native_value = value
        setattr(self._entry.runtime_data, self.entity_description.field, value)
        self.async_write_ha_state()
        # The goal curve and the next feeding depend on the night window
        await self._entry.runtime_data.coordinator.async_refresh()
