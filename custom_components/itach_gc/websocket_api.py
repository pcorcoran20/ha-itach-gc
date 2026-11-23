"""Websocket commands used by the code editor panel."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import functools
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .itach import ITachError, parse_code

Handler = Callable[[HomeAssistant, websocket_api.ActiveConnection, dict[str, Any]], Awaitable[Any]]


def _data(hass: HomeAssistant, entry_id: str):
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        raise ValueError("That iTach isn't set up or isn't reachable right now")
    return entry.runtime_data


def _cmd(schema: dict, *, admin: bool = True):
    """websocket_command + admin + async + friendly errors, returning the result."""

    def deco(func: Handler):
        @functools.wraps(func)
        async def wrapper(hass, connection, msg):
            try:
                result = await func(hass, connection, msg)
            except ValueError as err:
                connection.send_error(msg["id"], "invalid", str(err))
            except ITachError as err:
                connection.send_error(msg["id"], "itach_error", str(err))
            else:
                connection.send_result(msg["id"], result)

        handler = websocket_api.async_response(wrapper)
        if admin:
            handler = websocket_api.require_admin(handler)
        return websocket_api.websocket_command(schema)(handler)

    return deco


ENTRY = {vol.Required("entry_id"): str}


@_cmd({vol.Required("type"): f"{DOMAIN}/entries"})
async def ws_entries(hass, connection, msg):
    out = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        loaded = entry.state is ConfigEntryState.LOADED
        out.append(
            {
                "entry_id": entry.entry_id,
                "title": entry.title,
                "host": entry.data.get(CONF_HOST),
                "loaded": loaded,
                "connectors": entry.runtime_data.info.connectors if loaded else [],
                "model": entry.runtime_data.info.model if loaded else None,
            }
        )
    return out


@_cmd({vol.Required("type"): f"{DOMAIN}/codes", **ENTRY})
async def ws_codes(hass, connection, msg):
    return {"devices": _data(hass, msg["entry_id"]).store.devices}


@_cmd(
    {
        vol.Required("type"): f"{DOMAIN}/device/save",
        **ENTRY,
        vol.Optional("device_id"): vol.Any(str, None),
        vol.Required("name"): str,
        vol.Required("connector"): str,
    }
)
async def ws_device_save(hass, connection, msg):
    data = _data(hass, msg["entry_id"])
    if msg["connector"] not in data.info.connectors:
        raise ValueError(f"Connector {msg['connector']} isn't an IR port on this iTach")
    dev_id = await data.store.async_save_device(
        msg.get("device_id"), msg["name"], msg["connector"]
    )
    return {"device_id": dev_id}


@_cmd({vol.Required("type"): f"{DOMAIN}/device/delete", **ENTRY, vol.Required("device_id"): str})
async def ws_device_delete(hass, connection, msg):
    await _data(hass, msg["entry_id"]).store.async_delete_device(msg["device_id"])


@_cmd(
    {
        vol.Required("type"): f"{DOMAIN}/command/save",
        **ENTRY,
        vol.Required("device_id"): str,
        vol.Optional("command_id"): vol.Any(str, None),
        vol.Required("name"): str,
        vol.Required("code"): str,
        vol.Optional("repeat"): vol.Any(int, None),
    }
)
async def ws_command_save(hass, connection, msg):
    cmd_id = await _data(hass, msg["entry_id"]).store.async_save_command(
        msg["device_id"], msg.get("command_id"), msg["name"], msg["code"], msg.get("repeat")
    )
    return {"command_id": cmd_id}


@_cmd(
    {
        vol.Required("type"): f"{DOMAIN}/command/delete",
        **ENTRY,
        vol.Required("device_id"): str,
        vol.Required("command_id"): str,
    }
)
async def ws_command_delete(hass, connection, msg):
    await _data(hass, msg["entry_id"]).store.async_delete_command(
        msg["device_id"], msg["command_id"]
    )


@_cmd(
    {
        vol.Required("type"): f"{DOMAIN}/send",
        **ENTRY,
        vol.Required("code"): str,
        vol.Optional("connector"): vol.Any(str, None),
        vol.Optional("repeat"): vol.Any(int, None),
    }
)
async def ws_send(hass, connection, msg):
    data = _data(hass, msg["entry_id"])
    await data.client.async_send(
        msg["code"], msg.get("connector") or data.info.connectors[0], msg.get("repeat")
    )


@_cmd({vol.Required("type"): f"{DOMAIN}/learn", **ENTRY, vol.Optional("timeout", default=15): vol.All(int, vol.Range(3, 60))})
async def ws_learn(hass, connection, msg):
    code = await _data(hass, msg["entry_id"]).client.async_learn(msg["timeout"])
    return {"code": code}


@_cmd({vol.Required("type"): f"{DOMAIN}/parse", vol.Required("code"): str})
async def ws_parse(hass, connection, msg):
    ir = parse_code(msg["code"])
    return {
        "format": ir.source,
        "freq": ir.freq,
        "repeat": ir.repeat,
        "offset": ir.offset,
        "connector": ir.connector,
        "pulse_count": len(ir.pulses),
        "pulses": ir.numeric_pulses(),
        "sendir": ir.to_sendir(ir.connector or "1:1", 1),
    }


@_cmd({vol.Required("type"): f"{DOMAIN}/export", **ENTRY})
async def ws_export(hass, connection, msg):
    return _data(hass, msg["entry_id"]).store.export()


@_cmd(
    {
        vol.Required("type"): f"{DOMAIN}/import",
        **ENTRY,
        vol.Required("data"): vol.Any(dict, list),
        vol.Optional("replace", default=False): bool,
    }
)
async def ws_import(hass, connection, msg):
    data = _data(hass, msg["entry_id"])
    return await data.store.async_import(msg["data"], data.info.connectors[0], msg["replace"])


@callback
def async_register(hass: HomeAssistant) -> None:
    for handler in (
        ws_entries,
        ws_codes,
        ws_device_save,
        ws_device_delete,
        ws_command_save,
        ws_command_delete,
        ws_send,
        ws_learn,
        ws_parse,
        ws_export,
        ws_import,
    ):
        websocket_api.async_register_command(hass, handler)
