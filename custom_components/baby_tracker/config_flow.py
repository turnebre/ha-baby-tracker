"""UI configuration: adding a baby and the "Configure" option to edit their details."""

from __future__ import annotations

import os
from typing import Any
import uuid

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_DB,
    DB_FILENAME,
    POOP_COLOR_DEFAULT,
    POOP_COLORS,
    CONF_POOP_COLOR,
    CONF_POOP_CONSISTENCY,
    POOP_CONSISTENCY_DEFAULT,
    POOP_CONSISTENCIES,
    CONF_BIRTH_DATE,
    CONF_BABY_NAME,
    CONF_OZ_DEFAULT,
    CONF_SEX,
    CONF_TYPE_DEFAULT,
    CONF_GROWTH_UNIT,
    CONF_UNIT,
    DOMAIN,
    GROWTH_UNIT_DEFAULT,
    GROWTH_UNITS,
    SEXES,
    TYPES,
    UNITS,
)
from .migrate_legacy import LegacyImportError, find_legacy_dbs, import_legacy_db

CONF_IMPORT_DB = "import_db"


def _baby_schema(current: dict[str, Any]) -> dict:
    date = (
        vol.Required(CONF_BIRTH_DATE, default=current[CONF_BIRTH_DATE])
        if current.get(CONF_BIRTH_DATE) else vol.Required(CONF_BIRTH_DATE)
    )
    return {
        vol.Required(CONF_BABY_NAME, default=current.get(CONF_BABY_NAME, "")): selector.TextSelector(),
        date: selector.DateSelector(),
        vol.Optional(CONF_SEX, default=current.get(CONF_SEX, "unspecified")): selector.SelectSelector(
            selector.SelectSelectorConfig(options=SEXES, translation_key="sex")
        ),
        vol.Optional(CONF_UNIT, default=current.get(CONF_UNIT, "oz")): selector.SelectSelector(
            selector.SelectSelectorConfig(options=UNITS, translation_key="unit")
        ),
        vol.Optional(CONF_GROWTH_UNIT, default=current.get(CONF_GROWTH_UNIT, GROWTH_UNIT_DEFAULT)): selector.SelectSelector(
            selector.SelectSelectorConfig(options=GROWTH_UNITS, translation_key="growth_unit")
        ),
        vol.Optional(CONF_POOP_COLOR, default=current.get(CONF_POOP_COLOR, POOP_COLOR_DEFAULT)): selector.SelectSelector(
            selector.SelectSelectorConfig(options=[c for c in POOP_COLORS if c != "not_sure"], translation_key="poop_color")
        ),
        vol.Optional(CONF_POOP_CONSISTENCY, default=current.get(CONF_POOP_CONSISTENCY, POOP_CONSISTENCY_DEFAULT)): selector.SelectSelector(
            selector.SelectSelectorConfig(options=[c for c in POOP_CONSISTENCIES if c != "not_sure"], translation_key="poop_consistency")
        ),
    }


class BabyConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        legacy = await self.hass.async_add_executor_job(find_legacy_dbs, self.hass.config.config_dir)
        if user_input is not None:
            user_input = dict(user_input)
            source = user_input.pop(CONF_IMPORT_DB, None)
            # One database per baby: the first one uses baby_tracker.db
            used = {e.data.get(CONF_DB, DB_FILENAME) for e in self._async_current_entries()}
            db = DB_FILENAME if DB_FILENAME not in used else f"baby_tracker_{uuid.uuid4().hex[:8]}.db"
            if source:
                # An imported baby needs a database file that does not exist yet
                if await self.hass.async_add_executor_job(os.path.exists, self.hass.config.path(db)):
                    db = f"baby_tracker_{uuid.uuid4().hex[:8]}.db"
                try:
                    await self.hass.async_add_executor_job(
                        import_legacy_db, self.hass.config.path(source), self.hass.config.path(db)
                    )
                except LegacyImportError as err:
                    errors["base"] = err.key
            if not errors:
                return self.async_create_entry(title=user_input[CONF_BABY_NAME], data={**user_input, CONF_DB: db})
        fields: dict[Any, Any] = {
            **_baby_schema({}),
            vol.Required(CONF_OZ_DEFAULT, default=3.0): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.5, max=10, step=0.5, unit_of_measurement="oz")
            ),
            vol.Required(CONF_TYPE_DEFAULT, default="formula"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=TYPES, translation_key="type")
            ),
        }
        if legacy:
            fields[vol.Optional(CONF_IMPORT_DB)] = selector.SelectSelector(
                selector.SelectSelectorConfig(options=legacy, mode=selector.SelectSelectorMode.DROPDOWN)
            )
        schema = self.add_suggested_values_to_schema(vol.Schema(fields), user_input)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BabyOptionsFlow()


class BabyOptionsFlow(OptionsFlow):
    """Edit name, date of birth and sex without reinstalling."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                self.config_entry, data={**self.config_entry.data, **user_input}, title=user_input[CONF_BABY_NAME]
            )
            # Reload so the panel, the device and the age use the new data
            self.hass.async_create_task(self.hass.config_entries.async_reload(self.config_entry.entry_id))
            return self.async_create_entry(data={})
        return self.async_show_form(step_id="init", data_schema=vol.Schema(_baby_schema(dict(self.config_entry.data))))
