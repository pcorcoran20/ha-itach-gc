"""Persistent storage of IR devices + codes for one iTach."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION
from .itach import parse_code


def _clean_name(name: str, what: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError(f"{what} name can't be empty")
    if len(name) > 64:
        raise ValueError(f"{what} name is too long (max 64 characters)")
    return name


def _clean_repeat(repeat: Any) -> int | None:
    if repeat in (None, ""):
        return None
    repeat = int(repeat)
    if not 1 <= repeat <= 50:
        raise ValueError("Repeat must be between 1 and 50")
    return repeat


class CodeStore:
    """Devices -> commands -> codes.

    {"devices": {dev_id: {"name", "connector", "commands": {cmd_id: {"name", "code", "repeat"}}}}}
    Ids are stable so renames don't break entities.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )
        self.devices: dict[str, dict[str, Any]] = {}
        self._listeners: list[Callable[[], None]] = []

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.devices = data.get("devices", {})

    async def async_remove(self) -> None:
        await self._store.async_remove()

    async def _async_commit(self) -> None:
        await self._store.async_save({"devices": self.devices})
        for listener in list(self._listeners):
            listener()

    @callback
    def async_add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)

        @callback
        def _remove() -> None:
            if cb in self._listeners:
                self._listeners.remove(cb)

        return _remove

    # ---- lookups -------------------------------------------------------
    def get_device(self, device_id: str) -> dict[str, Any]:
        if device_id not in self.devices:
            raise ValueError("That device doesn't exist (anymore)")
        return self.devices[device_id]

    def get_command(self, device_id: str, command_id: str) -> dict[str, Any]:
        dev = self.get_device(device_id)
        if command_id not in dev["commands"]:
            raise ValueError("That code doesn't exist (anymore)")
        return dev["commands"][command_id]

    def find_device(self, name: str) -> tuple[str, dict[str, Any]] | None:
        key = name.strip().casefold()
        for dev_id, dev in self.devices.items():
            if dev["name"].casefold() == key:
                return dev_id, dev
        return None

    @staticmethod
    def find_command(dev: dict[str, Any], name: str) -> tuple[str, dict[str, Any]] | None:
        key = name.strip().casefold()
        for cmd_id, cmd in dev["commands"].items():
            if cmd["name"].casefold() == key:
                return cmd_id, cmd
        return None

    # ---- mutations -----------------------------------------------------
    def _put_device(self, device_id: str | None, name: str, connector: str) -> str:
        name = _clean_name(name, "Device")
        clash = self.find_device(name)
        if clash and clash[0] != device_id:
            raise ValueError(f'A device called "{name}" already exists')
        if device_id is None:
            device_id = uuid4().hex
            self.devices[device_id] = {"name": name, "connector": connector, "commands": {}}
        else:
            dev = self.get_device(device_id)
            dev["name"] = name
            dev["connector"] = connector
        return device_id

    def _put_command(
        self, device_id: str, command_id: str | None, name: str, code: str, repeat: Any
    ) -> str:
        dev = self.get_device(device_id)
        name = _clean_name(name, "Code")
        code = (code or "").strip()
        parse_code(code)  # raises ValueError with a friendly message
        repeat = _clean_repeat(repeat)
        clash = self.find_command(dev, name)
        if clash and clash[0] != command_id:
            raise ValueError(f'"{dev["name"]}" already has a code called "{name}"')
        if command_id is None:
            command_id = uuid4().hex
        elif command_id not in dev["commands"]:
            raise ValueError("That code doesn't exist (anymore)")
        dev["commands"][command_id] = {"name": name, "code": code, "repeat": repeat}
        return command_id

    async def async_save_device(self, device_id: str | None, name: str, connector: str) -> str:
        device_id = self._put_device(device_id, name, connector)
        await self._async_commit()
        return device_id

    async def async_delete_device(self, device_id: str) -> None:
        self.get_device(device_id)
        del self.devices[device_id]
        await self._async_commit()

    async def async_save_command(
        self, device_id: str, command_id: str | None, name: str, code: str, repeat: Any = None
    ) -> str:
        command_id = self._put_command(device_id, command_id, name, code, repeat)
        await self._async_commit()
        return command_id

    async def async_delete_command(self, device_id: str, command_id: str) -> None:
        self.get_command(device_id, command_id)
        del self.devices[device_id]["commands"][command_id]
        await self._async_commit()

    # ---- import / export -----------------------------------------------
    def export(self) -> dict[str, Any]:
        return {
            "format": "itach_gc",
            "version": 1,
            "devices": [
                {
                    "name": dev["name"],
                    "connector": dev["connector"],
                    "commands": [
                        {"name": c["name"], "code": c["code"], "repeat": c.get("repeat")}
                        for c in dev["commands"].values()
                    ],
                }
                for dev in self.devices.values()
            ],
        }

    async def async_import(
        self, data: Any, default_connector: str, replace: bool = False
    ) -> dict[str, int]:
        """Import our export format, or a simple {device: {command: code}} dict."""
        devices: list[dict[str, Any]]
        if isinstance(data, dict) and isinstance(data.get("devices"), list):
            devices = data["devices"]
        elif isinstance(data, dict):
            devices = []
            for dev_name, cmds in data.items():
                if not isinstance(cmds, dict):
                    raise ValueError(f'"{dev_name}" should map command names to codes')
                devices.append(
                    {
                        "name": dev_name,
                        "commands": [{"name": k, "code": v} for k, v in cmds.items()],
                    }
                )
        else:
            raise ValueError("Import must be a JSON object")

        # Validate everything before touching real data.
        errors = []
        for dev in devices:
            for cmd in dev.get("commands", []):
                try:
                    _clean_name(cmd.get("name", ""), "Code")
                    parse_code(str(cmd.get("code", "")))
                except (ValueError, TypeError) as err:
                    errors.append(f'{dev.get("name")} / {cmd.get("name")}: {err}')
        if errors:
            raise ValueError("Nothing imported. Problems:\n" + "\n".join(errors[:10]))

        backup = self.devices
        if replace:
            self.devices = {}
        else:
            # deep-ish copy so a failure halfway leaves the original intact
            self.devices = {
                k: {**v, "commands": dict(v["commands"])} for k, v in backup.items()
            }
        added = 0
        try:
            for dev in devices:
                existing = self.find_device(str(dev.get("name", "")))
                connector = dev.get("connector") or (
                    existing[1]["connector"] if existing else default_connector
                )
                dev_id = self._put_device(
                    existing[0] if existing else None, str(dev.get("name", "")), connector
                )
                for cmd in dev.get("commands", []):
                    found = self.find_command(self.devices[dev_id], str(cmd["name"]))
                    self._put_command(
                        dev_id,
                        found[0] if found else None,
                        str(cmd["name"]),
                        str(cmd["code"]),
                        cmd.get("repeat"),
                    )
                    added += 1
        except (ValueError, TypeError):
            self.devices = backup
            raise
        await self._async_commit()
        return {"devices": len(devices), "commands": added}
