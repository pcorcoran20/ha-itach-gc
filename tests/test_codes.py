import asyncio

import pytest

from custom_components.itach_gc.itach import ITachClient, ITachCommandError, parse_code

from .conftest import LEARNED

PRONTO = (
    "0000 006D 0002 0001 0156 00AB 0015 0040 0156 0055"
)


def test_parse_sendir():
    ir = parse_code(LEARNED)
    assert ir.freq == 38000 and ir.offset == 1 and ir.connector == "1:1"
    assert ir.numeric_pulses()[:2] == [342, 171]
    assert ir.to_sendir("1:3", 7, 2).startswith("sendir,1:3,7,38000,2,1,342")


def test_parse_pronto():
    ir = parse_code(PRONTO)
    assert ir.source == "pronto"
    assert 37900 < ir.freq < 38100
    assert ir.offset == 5  # 2 once-pairs -> repeat section starts at pulse 5
    assert ir.numeric_pulses() == [342, 171, 21, 64, 342, 85]


def test_parse_raw_and_compressed():
    assert parse_code("38000,1,1,342,171,21,21").source == "raw"
    assert parse_code("sendir,1:1,1,38000,1,1,342,171,21,64AB,21,21").source == "compressed"


@pytest.mark.parametrize(
    "bad",
    ["", "hello", "sendir,1:1,1,38000,1,1,342", "38000,1,2,342,171", "0100 006D 0001 0000 0010 0020",
     "sendir,1:1,1,9000,1,1,342,171"],
)
def test_parse_bad(bad):
    with pytest.raises(ValueError):
        parse_code(bad)


async def test_client(fake_itach):
    c = ITachClient("127.0.0.1", fake_itach.port)
    info = await c.async_get_info()
    assert info.connectors == ["1:1", "1:2", "1:3"]
    assert info.model == "iTach IP2IR" and info.version == "710-1005-05"
    fake_itach.busy_once = True
    await c.async_send(PRONTO, "1:2")
    sent = [r for r in fake_itach.received if r.startswith("sendir")]
    assert len(sent) == 2 and sent[-1].startswith("sendir,1:2,")
    with pytest.raises(ITachCommandError, match="connector"):
        await c.async_send(LEARNED, "1:9")
    assert await c.async_learn(3) == LEARNED
    await asyncio.sleep(0.1)
    assert "stop_IRL" in fake_itach.received
