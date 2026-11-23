from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.itach_gc.const import DOMAIN

from .conftest import LEARNED


async def test_config_flow(hass, fake_itach):
    res = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert res["type"] is FlowResultType.FORM
    bad = await hass.config_entries.flow.async_configure(res["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: 1})
    assert bad["errors"] == {"base": "cannot_connect"}
    ok = await hass.config_entries.flow.async_configure(
        res["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: fake_itach.port, "name": "Lounge iTach"}
    )
    assert ok["type"] is FlowResultType.CREATE_ENTRY
    assert ok["title"] == "Lounge iTach"
    await hass.async_block_till_done()
    assert hass.states.get("remote.lounge_itach").state == "on"


async def test_panel_ws_and_entities(hass, hass_ws_client, fake_itach):
    entry = MockConfigEntry(domain=DOMAIN, title="iTach", data={CONF_HOST: "127.0.0.1", CONF_PORT: fake_itach.port})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert "itach-gc" in hass.data["frontend_panels"]

    ws = await hass_ws_client(hass)
    n = 0

    async def call(t, **kw):
        nonlocal n
        n += 1
        await ws.send_json({"id": n, "type": f"itach_gc/{t}", **kw})
        return await ws.receive_json()

    r = await call("entries")
    assert r["result"][0]["connectors"] == ["1:1", "1:2", "1:3"]
    dev = (await call("device/save", entry_id=entry.entry_id, name="Living room TV", connector="1:2"))["result"]["device_id"]
    r = await call("command/save", entry_id=entry.entry_id, device_id=dev, name="Power", code="nope")
    assert not r["success"] and "Unrecognised" in r["error"]["message"]
    cmd = (await call("command/save", entry_id=entry.entry_id, device_id=dev, name="Power", code=LEARNED))["result"]["command_id"]
    await hass.async_block_till_done()

    state = hass.states.get("button.living_room_tv_power")
    assert state is not None
    await hass.services.async_call("button", "press", {"entity_id": "button.living_room_tv_power"}, blocking=True)
    assert fake_itach.received[-1].startswith("sendir,1:2,")

    await hass.services.async_call(
        "remote", "send_command", {"entity_id": "remote.itach", "device": "living room tv", "command": "power"}, blocking=True
    )
    assert fake_itach.received[-1].startswith("sendir,1:2,")

    # rename keeps the entity id, updates name
    await call("command/save", entry_id=entry.entry_id, device_id=dev, command_id=cmd, name="Power toggle", code=LEARNED)
    await hass.async_block_till_done()
    assert hass.states.get("button.living_room_tv_power").attributes["friendly_name"] == "Living room TV Power toggle"

    r = await call("parse", code="0000 006D 0002 0001 0156 00AB 0015 0040 0156 0055")
    assert r["result"]["format"] == "pronto" and r["result"]["offset"] == 5

    r = await call("learn", entry_id=entry.entry_id, timeout=5)
    assert r["result"]["code"] == LEARNED

    exp = (await call("export", entry_id=entry.entry_id))["result"]
    await call("command/delete", entry_id=entry.entry_id, device_id=dev, command_id=cmd)
    await hass.async_block_till_done()
    assert hass.states.get("button.living_room_tv_power") is None
    assert not [e for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id) if e.domain == "button"]

    r = await call("import", entry_id=entry.entry_id, data={"Soundbar": {"Mute": LEARNED}, **{}}, replace=False)
    assert r["result"] == {"devices": 1, "commands": 1}
    r = await call("import", entry_id=entry.entry_id, data=exp, replace=True)
    assert r["success"]
    await hass.async_block_till_done()
    assert hass.states.get("button.living_room_tv_power_toggle") is not None

    # learn via the standard remote service
    await hass.services.async_call(
        "remote", "learn_command", {"entity_id": "remote.itach", "device": "Projector", "command": ["On"], "timeout": 5}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get("button.projector_on") is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert "itach-gc" not in hass.data["frontend_panels"]
