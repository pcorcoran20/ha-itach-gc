"""Tiny async client + IR code helpers for Global Caché iTach devices.

This module deliberately has no Home Assistant imports so it can be tested
on its own.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
import logging
import re

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 4998

_ERRORS = {
    "001": "Invalid command (command not found)",
    "002": "Invalid module address",
    "003": "Invalid connector address",
    "004": "Invalid ID value",
    "005": "Invalid frequency value",
    "006": "Invalid repeat value",
    "007": "Invalid offset value",
    "008": "Invalid pulse count",
    "009": "Invalid pulse data",
    "010": "Uneven amount of on/off statements",
    "011": "No carriage return found",
    "012": "Repeat count exceeded",
    "013": "IR command sent to input connector",
    "014": "Blaster command sent to non-blaster connector",
    "015": "No carriage return before buffer full",
    "016": "No carriage return",
    "017": "Bad command syntax",
    "018": "Sensor command sent to non-input connector",
    "019": "Repeated IR transmission failure",
    "020": "Above designated IR on/off pair limit",
    "021": "Symbol odd boundary",
    "022": "Undefined symbol",
    "023": "Unknown option",
    "024": "Invalid baud rate setting",
    "025": "Invalid flow control setting",
    "026": "Invalid parity setting",
    "027": "Settings are locked",
}

_PRONTO_RE = re.compile(r"^[0-9a-fA-F]{4}(\s+[0-9a-fA-F]{4})+$")
_RAW_RE = re.compile(r"^[\d\s,]+$")
_PULSE_RE = re.compile(r"^[0-9A-O]+$")
_CONNECTOR_RE = re.compile(r"^\d+:\d+$")


class ITachError(Exception):
    """Base error."""


class ITachConnectionError(ITachError):
    """Could not talk to the iTach."""


class ITachCommandError(ITachError):
    """The iTach rejected a command."""


def _describe_error(line: str) -> str:
    match = re.search(r"(\d{3})\s*$", line)
    if match and match.group(1) in _ERRORS:
        return f"{_ERRORS[match.group(1)]} ({line})"
    return line


@dataclass
class IRCode:
    """A parsed IR code in Global Caché terms."""

    freq: int
    repeat: int
    offset: int
    pulses: list[str]
    source: str  # sendir | pronto | raw | compressed
    connector: str | None = None

    @property
    def compressed(self) -> bool:
        return any(not p.isdigit() for p in self.pulses)

    def numeric_pulses(self) -> list[int] | None:
        if self.compressed:
            return None
        return [int(p) for p in self.pulses]

    def to_sendir(
        self, connector: str | None = None, cmd_id: int = 1, repeat: int | None = None
    ) -> str:
        conn = connector or self.connector or "1:1"
        rep = repeat or self.repeat
        return (
            f"sendir,{conn},{cmd_id},{self.freq},{rep},{self.offset},"
            + ",".join(self.pulses)
        )


def _int(value: str, what: str) -> int:
    try:
        return int(value.strip())
    except ValueError as err:
        raise ValueError(f"{what} must be a number, got '{value.strip()}'") from err


def _parse_pronto(text: str) -> IRCode:
    words = [int(w, 16) for w in text.split()]
    if len(words) < 6:
        raise ValueError("Pronto code is too short")
    if words[0] != 0x0000:
        raise ValueError(
            "Only raw/learned Pronto codes (starting with 0000) are supported"
        )
    freq_code, once, rep = words[1], words[2], words[3]
    if freq_code == 0:
        raise ValueError("Pronto frequency word can't be 0000")
    needed = 4 + 2 * (once + rep)
    if len(words) < needed:
        raise ValueError(
            f"Pronto code says it has {once + rep} burst pairs but only "
            f"{(len(words) - 4) // 2} are present"
        )
    freq = round(1_000_000 / (freq_code * 0.241246))
    pulses = [str(w) for w in words[4:needed]]
    offset = 2 * once + 1 if once and rep else 1
    return IRCode(freq=freq, repeat=1, offset=offset, pulses=pulses, source="pronto")


def parse_code(code: str) -> IRCode:
    """Parse a sendir string, bare GC data or Pronto hex. Raises ValueError."""
    text = (code or "").strip()
    if not text:
        raise ValueError("Code is empty")

    connector = None
    if text.lower().startswith("sendir"):
        parts = [p.strip() for p in text.split(",")]
        if len(parts) < 8:
            raise ValueError("sendir code is too short")
        connector = parts[1]
        if not _CONNECTOR_RE.match(connector):
            raise ValueError(f"Bad connector '{connector}' (expected e.g. 1:1)")
        body = parts[3:]
        source = "sendir"
    elif _PRONTO_RE.match(text):
        ir = _parse_pronto(text)
        _validate(ir)
        return ir
    elif _RAW_RE.match(text) and "," in text:
        body = [p.strip() for p in text.split(",")]
        source = "raw"
    else:
        raise ValueError(
            "Unrecognised format. Paste a Global Caché 'sendir,…' string, "
            "bare GC data (freq,repeat,offset,on,off,…) or Pronto hex (0000 …)"
        )

    body = [p for p in body if p != ""]
    if len(body) < 5:
        raise ValueError("Code needs a frequency, repeat, offset and pulse data")
    ir = IRCode(
        freq=_int(body[0], "Frequency"),
        repeat=_int(body[1], "Repeat"),
        offset=_int(body[2], "Offset"),
        pulses=body[3:],
        source=source,
        connector=connector,
    )
    if ir.compressed:
        ir.source = "compressed"
    _validate(ir)
    return ir


def _validate(ir: IRCode) -> None:
    if not 15_000 <= ir.freq <= 500_000:
        raise ValueError(f"Frequency {ir.freq} Hz is outside 15000–500000")
    if not 1 <= ir.repeat <= 50:
        raise ValueError(f"Repeat {ir.repeat} must be between 1 and 50")
    if ir.offset < 1 or ir.offset % 2 == 0:
        raise ValueError(f"Offset {ir.offset} must be an odd number ≥ 1")
    for p in ir.pulses:
        if not _PULSE_RE.match(p):
            raise ValueError(f"Bad pulse value '{p}'")
    nums = ir.numeric_pulses()
    if nums is not None:
        if len(nums) % 2:
            raise ValueError(
                f"Pulse data must be on/off pairs, got an odd count ({len(nums)})"
            )
        if ir.offset > len(nums):
            raise ValueError(f"Offset {ir.offset} is past the end of the pulses")
        if any(not 1 <= n <= 65535 for n in nums):
            raise ValueError("Pulse values must be between 1 and 65535")


@dataclass
class ITachInfo:
    connectors: list[str]
    model: str
    version: str | None


class ITachClient:
    """Talks to an iTach over its TCP API (port 4998)."""

    def __init__(self, host: str, port: int = DEFAULT_PORT, timeout: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._lock = asyncio.Lock()
        self._cmd_id = 0

    async def _open(self):
        try:
            async with asyncio.timeout(self.timeout):
                return await asyncio.open_connection(self.host, self.port)
        except (OSError, TimeoutError) as err:
            raise ITachConnectionError(
                f"Can't connect to {self.host}:{self.port} ({err or 'timeout'})"
            ) from err

    @staticmethod
    async def _readline(reader: asyncio.StreamReader) -> str:
        while True:
            raw = await reader.readuntil(b"\r")
            line = raw.decode("ascii", errors="replace").strip()
            if line:
                return line

    async def _exchange(
        self, payload: str, done: Callable[[str], bool], timeout: float | None = None
    ) -> list[str]:
        reader, writer = await self._open()
        lines: list[str] = []
        try:
            writer.write((payload + "\r").encode("ascii"))
            await writer.drain()
            async with asyncio.timeout(timeout or self.timeout):
                while True:
                    line = await self._readline(reader)
                    _LOGGER.debug("%s <- %s", self.host, line)
                    if line.startswith("ERR") or line.startswith("unknowncommand"):
                        raise ITachCommandError(_describe_error(line))
                    lines.append(line)
                    if done(line):
                        return lines
        except TimeoutError as err:
            raise ITachConnectionError(
                f"Timed out waiting for {self.host} (got {lines or 'nothing'})"
            ) from err
        except (OSError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as err:
            raise ITachConnectionError(f"Connection to {self.host} failed: {err}") from err
        finally:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    async def async_get_info(self) -> ITachInfo:
        async with self._lock:
            lines = await self._exchange(
                "getdevices", lambda l: l.startswith("endlistdevices")
            )
            try:
                version = (await self._exchange("getversion", lambda l: True))[0]
            except ITachError:
                version = None
        connectors: list[str] = []
        net = ""
        for line in lines:
            m = re.match(r"device,(\d+),(\d+)\s+(\S+)", line)
            if not m:
                continue
            module, count, kind = int(m.group(1)), int(m.group(2)), m.group(3).upper()
            if module == 0:
                net = kind
            elif "IR" in kind:
                connectors += [f"{module}:{i}" for i in range(1, count + 1)]
        model = {"WIFI": "iTach WF2IR", "ETHERNET": "iTach IP2IR"}.get(net, "iTach")
        return ITachInfo(connectors=connectors or ["1:1"], model=model, version=version)

    async def async_send(
        self, code: IRCode | str, connector: str | None = None, repeat: int | None = None
    ) -> None:
        ir = parse_code(code) if isinstance(code, str) else code
        async with self._lock:
            for attempt in range(6):
                self._cmd_id = self._cmd_id % 65000 + 1
                cmd = ir.to_sendir(connector, self._cmd_id, repeat)
                _LOGGER.debug("%s -> %s", self.host, cmd)
                lines = await self._exchange(
                    cmd,
                    lambda l: l.startswith(("completeir", "busyIR")),
                    timeout=max(self.timeout, 10),
                )
                if not lines[-1].startswith("busyIR"):
                    return
                await asyncio.sleep(0.15 * (attempt + 1))
        raise ITachCommandError("iTach stayed busy, IR not sent")

    async def async_learn(self, timeout: float = 15) -> str:
        """Put the iTach in IR-learning mode and return the first code it sees."""
        reader, writer = await self._open()
        try:
            writer.write(b"get_IRL\r")
            await writer.drain()
            async with asyncio.timeout(timeout):
                while True:
                    line = await self._readline(reader)
                    _LOGGER.debug("%s learn <- %s", self.host, line)
                    if "Unavailable" in line:
                        raise ITachCommandError(
                            "IR learner unavailable (is a connector set to sensor/LED mode?)"
                        )
                    if line.startswith("ERR"):
                        raise ITachCommandError(_describe_error(line))
                    if line.lower().startswith("sendir"):
                        return line
        except TimeoutError as err:
            raise ITachError("No IR signal received – try again closer to the iTach") from err
        except (OSError, asyncio.IncompleteReadError) as err:
            raise ITachConnectionError(f"Connection to {self.host} failed: {err}") from err
        finally:
            with suppress(Exception):
                writer.write(b"stop_IRL\r")
                await writer.drain()
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()
