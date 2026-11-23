"""Convert Flipper Zero .ir signals into Global Caché IR codes.

Supports `type: raw` signals and these parsed protocols:
NEC, NECext, NEC42, NEC42ext, Samsung32, RC5, RC5X, RC6, SIRC, SIRC15, SIRC20.
"""

from __future__ import annotations

import re

_FIELD_RE = re.compile(r"^\s*([A-Za-z_]+)\s*:\s*(.*?)\s*$")
_BLOCK_HINT = re.compile(r"^\s*(protocol|type|data)\s*:", re.IGNORECASE | re.MULTILINE)

SUPPORTED = "NEC, NECext, NEC42, NEC42ext, Samsung32, RC5, RC5X, RC6, SIRC, SIRC15, SIRC20, raw"


def looks_like_flipper(text: str) -> bool:
    return bool(_BLOCK_HINT.search(text))


def _fields(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = _FIELD_RE.match(line)
        if m:
            out[m.group(1).lower()] = m.group(2)
    return out


def _le_value(field: str | None, what: str) -> int:
    """Flipper stores numbers as 4 little-endian hex bytes: '1C 00 00 00'."""
    if not field:
        raise ValueError(f"Flipper signal is missing '{what}'")
    try:
        return int.from_bytes(bytes(int(b, 16) for b in field.split()), "little")
    except ValueError as err:
        raise ValueError(f"Bad Flipper {what} '{field}'") from err


def _bits_lsb(value: int, count: int) -> list[int]:
    return [(value >> i) & 1 for i in range(count)]


def _pulse_distance(bits, header, one, zero, stop_mark, frame_us=None, min_gap=10_000):
    """Mark/space timings for NEC-style 'pulse distance' protocols (µs)."""
    t = list(header)
    for b in bits:
        t += one if b else zero
    t.append(stop_mark)
    gap = max(min_gap, (frame_us - sum(t)) if frame_us else min_gap)
    t.append(gap)
    return t


def _manchester(levels: list[int], half: int) -> list[int]:
    """levels: 1=mark, 0=space per half-bit slot -> merged durations, starting with a mark."""
    while levels and levels[0] == 0:
        levels = levels[1:]
    out: list[int] = []
    prev = None
    for lv in levels:
        if lv == prev:
            out[-1] += half
        else:
            out.append(half)
            prev = lv
    if len(out) % 2:  # ended on a mark -> add trailing gap
        out.append(0)
    return out


def _nec(proto: str, addr: int, cmd: int) -> tuple[int, list[int], int]:
    hdr, one, zero = (9000, 4500), (560, 1690), (560, 560)
    if proto == "nec":
        a, c = addr & 0xFF, cmd & 0xFF
        bits = _bits_lsb(a, 8) + _bits_lsb(a ^ 0xFF, 8) + _bits_lsb(c, 8) + _bits_lsb(c ^ 0xFF, 8)
    elif proto == "necext":
        bits = _bits_lsb(addr & 0xFFFF, 16) + _bits_lsb(cmd & 0xFFFF, 16)
    elif proto == "nec42":
        a, c = addr & 0x1FFF, cmd & 0xFF
        bits = _bits_lsb(a, 13) + _bits_lsb(a ^ 0x1FFF, 13) + _bits_lsb(c, 8) + _bits_lsb(c ^ 0xFF, 8)
    else:  # nec42ext
        bits = _bits_lsb(addr & 0x3FFFFFF, 26) + _bits_lsb(cmd & 0xFFFF, 16)
    return 38000, _pulse_distance(bits, hdr, one, zero, 560, frame_us=108_000), 1


def _samsung(addr: int, cmd: int):
    a, c = addr & 0xFF, cmd & 0xFF
    bits = _bits_lsb(a, 8) + _bits_lsb(a, 8) + _bits_lsb(c, 8) + _bits_lsb(c ^ 0xFF, 8)
    return 38000, _pulse_distance(bits, (4500, 4500), (560, 1690), (560, 560), 560, frame_us=108_000), 1


def _sirc(proto: str, addr: int, cmd: int):
    abits = {"sirc": 5, "sirc15": 8, "sirc20": 13}[proto]
    bits = _bits_lsb(cmd & 0x7F, 7) + _bits_lsb(addr & ((1 << abits) - 1), abits)
    t = [2400, 600]
    for b in bits:
        t += [1200 if b else 600, 600]
    t[-1] = max(600, 45_000 - sum(t[:-1]))  # frames repeat every 45 ms
    return 40000, t, 3  # Sony devices want the frame sent 3 times


def _rc5(proto: str, addr: int, cmd: int):
    half = 889
    cmd7 = cmd & (0x7F if proto == "rc5x" else 0x3F)
    field = 0 if cmd7 & 0x40 else 1
    bits = [1, field, 0] + [(addr >> i) & 1 for i in range(4, -1, -1)] + [(cmd7 >> i) & 1 for i in range(5, -1, -1)]
    levels: list[int] = []
    for b in bits:  # RC5: 1 = space->mark, 0 = mark->space
        levels += [0, 1] if b else [1, 0]
    t = _manchester(levels, half)
    t[-1] += max(10_000, 114_000 - sum(t))
    return 36000, t, 1


def _rc6(addr: int, cmd: int):
    half = 444
    levels = [1] * 6 + [0] * 2  # leader 2666 mark / 889 space
    def put(bit, width=1):  # RC6: 1 = mark->space, 0 = space->mark
        nonlocal levels
        levels += ([1] * width + [0] * width) if bit else ([0] * width + [1] * width)
    put(1)  # start bit
    for _ in range(3):
        put(0)  # mode 0
    put(0, 2)  # toggle/trailer bit, double width
    for i in range(7, -1, -1):
        put((addr >> i) & 1)
    for i in range(7, -1, -1):
        put((cmd >> i) & 1)
    t = _manchester(levels, half)
    t[-1] += max(10_000, 107_000 - sum(t))
    return 36000, t, 1


def _raw(f: dict[str, str]):
    try:
        freq = int(float(f.get("frequency", "38000")))
        data = [int(x) for x in f.get("data", "").split()]
    except ValueError as err:
        raise ValueError("Flipper raw signal has bad frequency/data") from err
    if not data:
        raise ValueError("Flipper raw signal has no data")
    if len(data) % 2:
        data.append(max(10_000, 4 * max(data)))
    return freq, data, 1


def flipper_to_gc(text: str) -> tuple[int, int, list[int], str]:
    """One Flipper signal block -> (freq, repeat, carrier-cycle pulses, description)."""
    f = _fields(text)
    kind = f.get("type", "parsed" if "protocol" in f else "raw").lower()
    if kind == "raw":
        freq, us, repeat = _raw(f)
        desc = "raw"
    else:
        proto = f.get("protocol", "").strip()
        p = proto.lower()
        addr = _le_value(f.get("address"), "address")
        cmd = _le_value(f.get("command"), "command")
        if p in ("nec", "necext", "nec42", "nec42ext"):
            freq, us, repeat = _nec(p, addr, cmd)
        elif p == "samsung32":
            freq, us, repeat = _samsung(addr, cmd)
        elif p in ("sirc", "sirc15", "sirc20"):
            freq, us, repeat = _sirc(p, addr, cmd)
        elif p in ("rc5", "rc5x"):
            freq, us, repeat = _rc5(p, addr, cmd)
        elif p == "rc6":
            freq, us, repeat = _rc6(addr, cmd)
        else:
            raise ValueError(
                f"Flipper protocol '{proto or '?'}' isn't supported yet (supported: {SUPPORTED}). "
                "Tip: on the Flipper, learn the button as a RAW signal instead."
            )
        desc = f"{proto} addr 0x{addr:X} cmd 0x{cmd:X}"
    pulses = [max(1, round(d * freq / 1_000_000)) for d in us]
    return freq, repeat, pulses, desc


def split_ir_file(text: str) -> list[tuple[str, str]]:
    """Split a Flipper .ir file into (name, block text) pairs."""
    blocks: list[tuple[str, str]] = []
    name, lines = None, []

    def flush():
        if name is not None and any(_BLOCK_HINT.match(l) for l in lines):
            blocks.append((name, "\n".join(lines)))

    for line in text.splitlines():
        m = _FIELD_RE.match(line)
        if m and m.group(1).lower() == "name":
            flush()
            name, lines = m.group(2), []
        elif name is not None and not line.strip().startswith("#"):
            lines.append(line.strip())
    flush()
    if not blocks:
        raise ValueError("No signals found – is this a Flipper Zero .ir file?")
    return blocks
