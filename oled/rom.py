import random
import struct

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
# for p in range(0x10):
for p in range(0x1):
    if p > 0:
        init.append([])
    init[-1] += [
        Cmd.SetPageAddress(p),
        DataBytes([0x00 for _ in range(0x80)]),
    ]
init.append([Cmd.DisplayOn(True)])
INIT_SEQUENCE = [Cmd.compose(part) for part in init]

disp: list[Base | DataBytes] = []
disp += [
    Cmd.SetPageAddress(0),
    DataBytes([(x * 2) % 0x100 for x in range(0x80)]),
]
DISPLAY_SEQUENCE = [Cmd.compose(disp)]

disp2: list[Base | DataBytes] = [
    Cmd.SetSegmentRemap("Flipped"),
] + disp
DISPLAY2_SEQUENCE = [Cmd.compose(disp2)]

POWEROFF_SEQUENCE = [Cmd.compose([Cmd.DisplayOn(False)])]

NULL_SEQUENCE: list[list[int]] = [[]]

seqs = (
    INIT_SEQUENCE,
    DISPLAY_SEQUENCE,
    DISPLAY2_SEQUENCE,
    POWEROFF_SEQUENCE,
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
