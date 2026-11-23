"""Registers the sidebar panel that hosts the visual code editor."""

from __future__ import annotations

import hashlib
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, PANEL_ELEMENT, PANEL_URL, STATIC_URL

_DATA = f"{DOMAIN}_panel"
_JS = Path(__file__).parent / "frontend" / "itach-gc-panel.js"


def _js_hash() -> str:
    """Fingerprint of the panel file so browsers reload it whenever it changes."""
    return hashlib.sha256(_JS.read_bytes()).hexdigest()[:12]


async def async_register_panel(hass: HomeAssistant) -> None:
    state = hass.data.setdefault(_DATA, {"static": False, "panel": False})
    if not state["static"]:
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    STATIC_URL, str(Path(__file__).parent / "frontend"), cache_headers=False
                )
            ]
        )
        state["static"] = True
    if state["panel"]:
        return
    js_hash = await hass.async_add_executor_job(_js_hash)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title="iTach IR",
        sidebar_icon="mdi:remote",
        module_url=f"{STATIC_URL}/itach-gc-panel.js?v={js_hash}",
        require_admin=True,
        config={},
    )
    state["panel"] = True


@callback
def async_unregister_panel(hass: HomeAssistant) -> None:
    state = hass.data.get(_DATA)
    if state and state["panel"]:
        frontend.async_remove_panel(hass, PANEL_URL)
        state["panel"] = False
