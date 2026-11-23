"""Remote entity: remote.send_command / learn_command / delete_command."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.components.remote import (
    ATTR_COMMAND,
    ATTR_DELAY_SECS,
    ATTR_DEVICE,
    ATTR_NUM_REPEATS,
    ATTR_TIMEOUT,
    DEFAULT_DELAY_SECS,
    RemoteEntity,
    RemoteEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ITachConfigEntry
from .const import DOMAIN
from .itach import ITachError, parse_code


async def async_setup_entry(
    hass: HomeAssistant, entry: ITachConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ITachRemote(entry)])


class ITachRemote(RemoteEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_assumed_state = True
    _attr_is_on = True
    _attr_supported_features = (
        RemoteEntityFeature.LEARN_COMMAND | RemoteEntityFeature.DELETE_COMMAND
    )

    def __init__(self, entry: ITachConfigEntry) -> None:
        self._data = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_remote"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()

    def _resolve(self, device: str | None, command: str):
        """Return (code, connector, repeat) for a command name or raw code."""
        store, default = self._data.store, self._data.info.connectors[0]
        if device:
            found = store.find_device(device)
            if not found:
                raise ServiceValidationError(f'No iTach device called "{device}"')
            dev = found[1]
            cmd = store.find_command(dev, command)
            if not cmd:
                raise ServiceValidationError(f'"{dev["name"]}" has no code called "{command}"')
            return cmd[1]["code"], dev["connector"], cmd[1].get("repeat")
        try:
            ir = parse_code(command)
        except ValueError as err:
            raise ServiceValidationError(
                f"Without a device, the command must be a raw IR code: {err}"
            ) from err
        return ir, ir.connector or default, None

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        device = kwargs.get(ATTR_DEVICE)
        repeats = kwargs.get(ATTR_NUM_REPEATS, 1)
        delay = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)
        resolved = [self._resolve(device, c) for c in command]  # fail fast
        first = True
        for _ in range(repeats):
            for code, connector, repeat in resolved:
                if not first:
                    await asyncio.sleep(delay)
                first = False
                try:
                    await self._data.client.async_send(code, connector, repeat)
                except (ITachError, ValueError) as err:
                    raise HomeAssistantError(f"iTach send failed: {err}") from err

    async def async_learn_command(self, **kwargs: Any) -> None:
        device = kwargs.get(ATTR_DEVICE)
        commands = kwargs.get(ATTR_COMMAND) or []
        timeout = kwargs.get(ATTR_TIMEOUT) or 15
        if not device:
            raise ServiceValidationError("learn_command needs a device name")
        store = self._data.store
        found = store.find_device(device)
        dev_id = (
            found[0]
            if found
            else await store.async_save_device(None, device, self._data.info.connectors[0])
        )
        note_id = f"{DOMAIN}_learn_{self.entity_id}"
        try:
            for name in commands:
                persistent_notification.async_create(
                    self.hass,
                    f"Point your remote at the iTach and press **{name}** "
                    f"(listening for {timeout}s).",
                    title="iTach is learning",
                    notification_id=note_id,
                )
                try:
                    code = await self._data.client.async_learn(timeout)
                except ITachError as err:
                    raise HomeAssistantError(f"Learning {name} failed: {err}") from err
                existing = store.find_command(store.get_device(dev_id), name)
                await store.async_save_command(
                    dev_id, existing[0] if existing else None, name, code
                )
        finally:
            persistent_notification.async_dismiss(self.hass, note_id)

    async def async_delete_command(self, **kwargs: Any) -> None:
        store = self._data.store
        found = store.find_device(kwargs.get(ATTR_DEVICE) or "")
        if not found:
            raise ServiceValidationError(f'No iTach device called "{kwargs.get(ATTR_DEVICE)}"')
        for name in kwargs.get(ATTR_COMMAND) or []:
            cmd = store.find_command(found[1], name)
            if cmd:
                await store.async_delete_command(found[0], cmd[0])
