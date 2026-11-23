"""Global Caché iTach IR integration with a visual code editor."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from . import websocket_api
from .const import DOMAIN, MANUFACTURER
from .itach import DEFAULT_PORT, ITachClient, ITachError, ITachInfo
from .panel import async_register_panel, async_unregister_panel
from .storage import CodeStore

PLATFORMS = [Platform.REMOTE, Platform.BUTTON]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class ITachData:
    client: ITachClient
    store: CodeStore
    info: ITachInfo


type ITachConfigEntry = ConfigEntry[ITachData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    websocket_api.async_register(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ITachConfigEntry) -> bool:
    host = entry.data[CONF_HOST]
    client = ITachClient(host, entry.data.get(CONF_PORT, DEFAULT_PORT))
    try:
        info = await client.async_get_info()
    except ITachError as err:
        raise ConfigEntryNotReady(f"Can't reach iTach at {host}: {err}") from err

    store = CodeStore(hass, entry.entry_id)
    await store.async_load()
    entry.runtime_data = ITachData(client=client, store=store, info=info)

    # Hub device first, so IR devices can point at it via via_device.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer=MANUFACTURER,
        model=info.model,
        name=entry.title,
        sw_version=info.version,
        configuration_url=f"http://{host}",
    )

    await async_register_panel(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ITachConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and not [
        e
        for e in hass.config_entries.async_loaded_entries(DOMAIN)
        if e.entry_id != entry.entry_id
    ]:
        async_unregister_panel(hass)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ITachConfigEntry) -> None:
    await CodeStore(hass, entry.entry_id).async_remove()
