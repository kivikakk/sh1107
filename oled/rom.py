import random
import struct

from .chars import CHARS
from .sh1107 import Base, Cmd, DataBytes

__all__ = ["ROM"]

random.seed("xyzabc")

init: list[list[Base | DataBytes]] = [
    [
        Cmd.DisplayOn(False),
        Cmd.SetDisplayClockFrequency(1, "Pos15"),
        Cmd.SetDisplayOffset(0),
        Cmd.SetDisplayStartColumn(0),
        Cmd.SetDCDC(True),
        Cmd.SetSegmentRemap("Normal"),
        Cmd.SetCommonOutputScanDirection("Forwards"),
        Cmd.SetContrastControlRegister(0x80),
        Cmd.SetPreDischargePeriod(2, 2),
        Cmd.SetVCOMDeselectLevel(0x40),
        Cmd.SetDisplayReverse(False),
        Cmd.SetMemoryAddressingMode("Page"),
        Cmd.SetLowerColumnAddress(0),
        Cmd.SetHigherColumnAddress(0),
    ]
]
for p in range(0x10):
    if p > 0:
        init.append([])
    init[-1] += [
        Cmd.SetPageAddress(p),
        DataBytes([0x00 for _ in range(0x80)]),
    ]
init.append([Cmd.DisplayOn(True)])
INIT_SEQUENCE = [Cmd.compose(part) for part in init]

TEST_PATTERNS = True
if TEST_PATTERNS:
    disp: list[Base | DataBytes] = []
    disp += [
        Cmd.SetPageAddress(0),
        DataBytes([(x * 2) % 0x100 for x in range(0x80)]),
    ]

    disp2: list[Base | DataBytes] = [
        Cmd.SetSegmentRemap("Flipped"),
        Cmd.SetCommonOutputScanDirection("Backwards"),
    ] + disp
else:
    disp: list[Base | DataBytes] = []
    disp += [
        Cmd.SetPageAddress(0x1),
        Cmd.SetHigherColumnAddress(0x0),
        Cmd.SetLowerColumnAddress(0x8),
        DataBytes([0xFF for _ in range(0x08)]),
    ]

    disp2: list[Base | DataBytes] = [
        Cmd.SetPageAddress(0x1),
        Cmd.SetHigherColumnAddress(0x1),
        Cmd.SetLowerColumnAddress(0x8),
        DataBytes([0xFF for _ in range(0x08)]),
    ]

DISPLAY_SEQUENCE = [Cmd.compose(disp)]
DISPLAY2_SEQUENCE = [Cmd.compose(disp2)]

POWEROFF_SEQUENCE = [Cmd.compose([Cmd.DisplayOn(False)])]

POS1_SEQUENCE = [
    Cmd.compose(
        [
            Cmd.SetPageAddress(0x3),
            Cmd.SetHigherColumnAddress(0x0),
            Cmd.SetLowerColumnAddress(0x8),
        ]
    )
]

POS2_SEQUENCE = [
    Cmd.compose(
        [
            Cmd.SetPageAddress(0x3),
            Cmd.SetHigherColumnAddress(0x1),
            Cmd.SetLowerColumnAddress(0x0),
        ]
    )
]

CHAR_SEQUENCES: list[list[list[int]]] = []
for i, c in enumerate(CHARS):
    rows = list(li.strip() for li in c.splitlines() if li.strip())
    assert len(rows) == 8
    for row in rows:
        assert len(row) == 8, f"char {i:x} has bad row"

    data = []
    for col in range(8):
        byte = 0
        for row in range(8):
            byte = (byte << 1) | (1 if rows[7 - row][col] == "x" else 0)
        data.append(byte)

    CHAR_SEQUENCES.append([Cmd.compose([DataBytes(data)])])

NULL_SEQUENCE: list[list[int]] = [[]]

seqs = (
    INIT_SEQUENCE,
    DISPLAY_SEQUENCE,
    DISPLAY2_SEQUENCE,
    POWEROFF_SEQUENCE,
    POS1_SEQUENCE,
    POS2_SEQUENCE,
    *CHAR_SEQUENCES,
    NULL_SEQUENCE,
)
rom_offset = len(seqs) * 2 * 2

rom = []
index = b""
for parts in seqs:
    index += struct.pack("<HH", rom_offset + len(rom), len(parts[0]))
    for i, part in enumerate(parts):
        rom.extend(part)
        if i == len(parts) - 1:
            rom.extend(struct.pack("<H", 0))
        else:
            nextlen = len(parts[i + 1])
            assert nextlen > 0
            rom.extend(struct.pack("<H", nextlen))

ROM = index + bytes(rom)

# ROM structure:
# "Commands" are 1 or more sequences of bytes to send as individual I2C transmissions.
# The very start of the ROM is an index of pairs of 16-bit numbers, (offset, length).
# There are as many of these as there are commands.
# To execute a command, start at `offset` and write the next `length` bytes as one I2C
# transmission.  The next two bytes are a 16-bit number that defines the length of
# the next transmission, or 0x0000 if finished.
