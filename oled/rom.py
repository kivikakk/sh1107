import struct

from .chars import CHARS
from .sh1107 import Cmd, DataBytes

__all__ = ["ROM", "SEQ_COUNT", "OFFSET_DISPLAY_ON", "OFFSET_DISPLAY_OFF", "OFFSET_CHAR"]

DISPLAY_ON_SEQUENCE: list[list[int]] = [
    Cmd.compose(
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
            Cmd.SetPageAddress(0),
            Cmd.SetLowerColumnAddress(0),
            Cmd.SetHigherColumnAddress(0),
            Cmd.DisplayOn(True),
        ]
    )
]

DISPLAY_OFF_SEQUENCE = [Cmd.compose([Cmd.DisplayOn(False)])]

CHAR_SEQUENCES: list[list[list[int]]] = []
for cols in CHARS:
    CHAR_SEQUENCES.append([Cmd.compose([DataBytes(cols)])])
assert len(CHAR_SEQUENCES) == 256

NULL_SEQUENCE: list[list[int]] = [[]]

seqs = (
    DISPLAY_ON_SEQUENCE,
    DISPLAY_OFF_SEQUENCE,
    *CHAR_SEQUENCES,
    NULL_SEQUENCE,
)
SEQ_COUNT = len(seqs)

OFFSET_DISPLAY_ON = 0x00
OFFSET_DISPLAY_OFF = 0x01
OFFSET_CHAR = 0x02

rom_offset = SEQ_COUNT * 2 * 2

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
