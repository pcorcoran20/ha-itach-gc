"""One button entity per saved IR code, kept in sync with the code editor."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ITachConfigEntry
from .const import DOMAIN
from .itach import ITachError


def _uid(entry_id: str, dev_id: str, cmd_id: str) -> str:
    return f"{entry_id}_{dev_id}_{cmd_id}"


async def async_setup_entry(
    hass: HomeAssistant, entry: ITachConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    store = entry.runtime_data.store
    known: dict[str, ITachCodeButton] = {}
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    @callback
    def _sync() -> None:
        wanted = {
            _uid(entry.entry_id, d, c): (d, c)
            for d, dev in store.devices.items()
            for c in dev["commands"]
        }
        # drop entities for deleted codes (also cleans up leftovers in the registry)
        for reg in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
            if reg.domain == "button" and reg.unique_id not in wanted:
                ent_reg.async_remove(reg.entity_id)
        for uid in list(known):
            if uid not in wanted:
                known.pop(uid)
        # refresh names of the ones we keep
        for ent in known.values():
            if ent.hass is not None:
                ent.async_write_ha_state()
        # sync IR device names / drop empty devices
        for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
            for domain, ident in device.identifiers:
                if domain != DOMAIN or ident == entry.entry_id:
                    continue
                dev_id = ident.removeprefix(f"{entry.entry_id}_")
                dev = store.devices.get(dev_id)
                if dev is None or not dev["commands"]:
                    dev_reg.async_update_device(
                        device.id, remove_config_entry_id=entry.entry_id
                    )
                elif device.name != dev["name"]:
                    dev_reg.async_update_device(device.id, name=dev["name"])
        new = []
        for uid, (d, c) in wanted.items():
            if uid not in known:
                known[uid] = ITachCodeButton(entry, d, c)
                new.append(known[uid])
        if new:
            async_add_entities(new)

    entry.async_on_unload(store.async_add_listener(_sync))
    _sync()


class ITachCodeButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, entry: ITachConfigEntry, dev_id: str, cmd_id: str) -> None:
        self._entry = entry
        self._data = entry.runtime_data
        self._dev_id = dev_id
        self._cmd_id = cmd_id
        self._attr_unique_id = _uid(entry.entry_id, dev_id, cmd_id)
        dev = self._data.store.devices[dev_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{dev_id}")},
            name=dev["name"],
            model="IR device",
            via_device=(DOMAIN, entry.entry_id),
        )

    @property
    def _cmd(self) -> dict | None:
        dev = self._data.store.devices.get(self._dev_id)
        return dev["commands"].get(self._cmd_id) if dev else None

    @property
    def name(self) -> str | None:
        cmd = self._cmd
        return cmd["name"] if cmd else None

    @property
    def available(self) -> bool:
        return self._cmd is not None

    @property
    def icon(self) -> str:
        return "mdi:remote"

    async def async_press(self) -> None:
        cmd = self._cmd
        if cmd is None:
            raise HomeAssistantError("This code was deleted")
        connector = self._data.store.devices[self._dev_id]["connector"]
        try:
            await self._data.client.async_send(cmd["code"], connector, cmd.get("repeat"))
        except (ITachError, ValueError) as err:
            raise HomeAssistantError(f"iTach send failed: {err}") from err
