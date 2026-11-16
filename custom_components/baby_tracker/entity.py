"""Base entity: groups everything under a device named after the baby."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import CONF_BABY_NAME, DOMAIN


def device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data[CONF_BABY_NAME],
        manufacturer="Baby Tracker",
        entry_type=DeviceEntryType.SERVICE,
    )
