"""Config flow: add an iTach from the UI."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.data_entry_flow import AbortFlow

from .const import DOMAIN
from .itach import DEFAULT_PORT, ITachClient, ITachError, ITachInfo

_LOGGER = logging.getLogger(__name__)


async def _probe(host: str, port: int) -> tuple[ITachInfo | None, dict[str, str]]:
    try:
        return await ITachClient(host, port).async_get_info(), {}
    except ITachError as err:
        _LOGGER.debug("iTach probe failed: %s", err)
        return None, {"base": "cannot_connect"}
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Unexpected error talking to iTach")
        return None, {"base": "unknown"}


class ITachConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()
            info, errors = await _probe(host, port)
            if info:
                name = (user_input.get(CONF_NAME) or "").strip() or f"{info.model} ({host})"
                return self.async_create_entry(
                    title=name, data={CONF_HOST: host, CONF_PORT: port}
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_NAME): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            await self.async_set_unique_id(f"{host}:{port}")
            for other in self._async_current_entries(include_ignore=False):
                if other.entry_id != entry.entry_id and other.unique_id == self.unique_id:
                    raise AbortFlow("already_configured")
            info, errors = await _probe(host, port)
            if info:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=f"{host}:{port}",
                    data_updates={CONF_HOST: host, CONF_PORT: port},
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                vol.Required(
                    CONF_PORT, default=entry.data.get(CONF_PORT, DEFAULT_PORT)
                ): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)
