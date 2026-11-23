import pytest

from custom_components.itach_gc.flipper import flipper_to_gc, split_ir_file
from custom_components.itach_gc.itach import parse_code

USER_FILE = """Filetype: IR signals file
Version: 1
# 
name: On_toggle
type: parsed
protocol: NEC
address: 01 00 00 00
command: 12 00 00 00
# 
name: Color
type: parsed
protocol: NEC
address: 01 00 00 00
command: 05 00 00 00
# 
name: Heat
type: parsed
protocol: NEC
address: 01 00 00 00
command: 18 00 00 00
# 
name: Weird
type: parsed
protocol: Kaseikyo
address: 41 54 32 00
command: 1B 00 00 00
# 
name: Raw_power
type: raw
frequency: 38000
duty_cycle: 0.330000
data: 9024 4512 579 552 579 1683 579
"""


def _decode_nec(pulses):
    """Read back the 32 NEC bits from carrier-cycle pulses @38kHz."""
    assert pulses[0] == 342 and pulses[1] == 171
    bits = [1 if pulses[3 + 2 * i] > 40 else 0 for i in range(32)]
    val = lambda chunk: sum(b << i for i, b in enumerate(chunk))
    return [val(bits[i:i + 8]) for i in range(0, 32, 8)]


def test_split_file():
    blocks = split_ir_file(USER_FILE)
    assert [n for n, _ in blocks] == ["On_toggle", "Color", "Heat", "Weird", "Raw_power"]
    assert "name:" not in blocks[0][1]


def test_nec_matches_spec():
    _, block = split_ir_file(USER_FILE)[0]
    freq, repeat, pulses, desc = flipper_to_gc(block)
    assert freq == 38000 and repeat == 1
    assert _decode_nec(pulses) == [0x01, 0xFE, 0x12, 0xED]
    assert len(pulses) == 2 + 64 + 2
    total_us = sum(pulses) / freq * 1e6
    assert 107_000 < total_us < 109_000  # standard 108 ms NEC frame
    assert desc == "NEC addr 0x1 cmd 0x12"


def test_parse_code_accepts_flipper_block():
    ir = parse_code(split_ir_file(USER_FILE)[2][1])
    assert ir.source == "flipper" and ir.offset == 1
    assert ir.to_sendir("1:1").startswith("sendir,1:1,1,38000,1,1,342,171,")


def test_raw_and_other_protocols():
    ir = parse_code(split_ir_file(USER_FILE)[4][1])
    assert ir.numeric_pulses()[:3] == [343, 171, 22] and len(ir.pulses) % 2 == 0
    for proto in ("NECext", "NEC42", "NEC42ext", "Samsung32", "RC5", "RC5X", "RC6", "SIRC", "SIRC15", "SIRC20"):
        ir = parse_code(f"type: parsed\nprotocol: {proto}\naddress: 01 00 00 00\ncommand: 15 00 00 00")
        assert len(ir.pulses) % 2 == 0, proto
    sirc = parse_code("protocol: SIRC\naddress: 01 00 00 00\ncommand: 15 00 00 00")
    assert sirc.freq == 40000 and sirc.repeat == 3
    assert sirc.numeric_pulses()[:2] == [96, 24]


def test_unsupported():
    with pytest.raises(ValueError, match="Kaseikyo"):
        parse_code(split_ir_file(USER_FILE)[3][1])
    with pytest.raises(ValueError):
        split_ir_file("hello")
