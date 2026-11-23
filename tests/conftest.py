"""Fake iTach TCP server + HA fixtures."""
import asyncio

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]

LEARNED = "sendir,1:1,0,38000,1,1,342,171,21,21,21,64,21,1520"


class FakeITach:
    def __init__(self):
        self.received: list[str] = []
        self.server = None
        self.port = None
        self.busy_once = False

    async def start(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()

    async def _handle(self, reader, writer):
        try:
            while True:
                raw = await reader.readuntil(b"\r")
                cmd = raw.decode().strip()
                self.received.append(cmd)
                out = []
                if cmd == "getdevices":
                    out = ["device,0,0 ETHERNET", "device,1,3 IR", "endlistdevices"]
                elif cmd == "getversion":
                    out = ["710-1005-05"]
                elif cmd.startswith("sendir"):
                    parts = cmd.split(",")
                    if self.busy_once:
                        self.busy_once = False
                        out = [f"busyIR,{parts[1]},{parts[2]}"]
                    elif parts[1] == "1:9":
                        out = ["ERR_1:9,003"]
                    else:
                        out = [f"completeir,{parts[1]},{parts[2]}"]
                elif cmd == "get_IRL":
                    out = ["IR Learner Enabled"]
                    writer.write(("\r".join(out) + "\r").encode())
                    await writer.drain()
                    await asyncio.sleep(0.05)
                    out = [LEARNED]
                elif cmd == "stop_IRL":
                    out = ["IR Learner Disabled"]
                else:
                    out = ["ERR_0:0,001"]
                writer.write(("\r".join(out) + "\r").encode())
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()


@pytest.fixture
async def fake_itach(socket_enabled):
    f = FakeITach()
    await f.start()
    yield f
    await f.stop()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
