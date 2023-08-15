import math
import struct
from argparse import ArgumentParser, Namespace

from ..base import path
from ..proto import Cmd, DataBytes
from ..target import Target
from .chars import CHARS

__all__ = [
    "add_main_arguments",
    "ROM_LENGTH",
    "ROM_ABITS",
    "ROM_CONTENT",
    "SEQ_COUNT",
    "OFFSET_INIT",
    "OFFSET_DISPLAY_ON",
    "OFFSET_DISPLAY_OFF",
    "OFFSET_SCROLL",
    "OFFSET_CHAR",
]


def add_main_arguments(parser: ArgumentParser):
    parser.set_defaults(func=main)
    parser.add_argument(
        "-p",
        "--program",
        dest="target",
        choices=Target.platform_targets,
        help="program the ROM onto the specified board",
    )


def main(args: Namespace):
    out = path("rom.bin")
    with open(out, "wb") as f:
        f.write(ROM_CONTENT)

    if args.target:
        Target[args.target].flash_rom(out)


INIT_SEQUENCE = Cmd.compose(
    [
        Cmd.DisplayOn(False),
        Cmd.SetDisplayClockFrequency(1, "Zero"),
        Cmd.SetDisplayOffset(0),
        Cmd.SetDisplayStartLine(0),
        Cmd.SetDCDC(True),
        Cmd.SetSegmentRemap("Normal"),
        Cmd.SetCommonOutputScanDirection("Forwards"),
        Cmd.SetContrastControlRegister(0x80),
        Cmd.SetMultiplexRatio(0x80),
        Cmd.SetPreDischargePeriod(2, 2),
        Cmd.SetVCOMDeselectLevel(0x35),
        Cmd.SetDisplayReverse(False),
        Cmd.SetMemoryAddressingMode("Page"),
        Cmd.SetPageAddress(0),
        Cmd.SetHigherColumnAddress(0),
        Cmd.SetLowerColumnAddress(0),
        Cmd.DisplayOn(True),
    ]
)

DISPLAY_ON_SEQUENCE = Cmd.compose([Cmd.DisplayOn(True)])

DISPLAY_OFF_SEQUENCE = Cmd.compose([Cmd.DisplayOn(False)])

SCROLL_SEQUENCE, SCROLL_OFFSETS = Cmd.compose_with_offsets(
    [
        Cmd.SetMemoryAddressingMode("Vertical"),
        Cmd.SetPageAddress(0),
        "InitialHigherColumnAddress",
        Cmd.SetHigherColumnAddress(0),
    ],
    *[
        [
            f"LowerColumnAddress{i}",
            Cmd.SetLowerColumnAddress(i),
            DataBytes([0x00] * 16),
        ]
        for i in range(8)
    ],
    [
        Cmd.SetMemoryAddressingMode("Page"),
        "DisplayStartLine",
        Cmd.SetDisplayStartLine(0),
    ],
)

CHAR_SEQUENCES: list[list[list[int]]] = []
for cols in CHARS:
    CHAR_SEQUENCES.append(Cmd.compose([DataBytes(cols)]))
assert len(CHAR_SEQUENCES) == 256

NULL_SEQUENCE: list[list[int]] = [[]]

seqs = (
    INIT_SEQUENCE,
    DISPLAY_ON_SEQUENCE,
    DISPLAY_OFF_SEQUENCE,
    SCROLL_SEQUENCE,
    *CHAR_SEQUENCES,
    NULL_SEQUENCE,
)
SEQ_COUNT = len(seqs)

OFFSET_INIT = 0x00
OFFSET_DISPLAY_ON = 0x01
OFFSET_DISPLAY_OFF = 0x02
OFFSET_SCROLL = 0x03
OFFSET_CHAR = 0x04

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

ROM_CONTENT = index + bytes(rom)

ROM_LENGTH = len(ROM_CONTENT)
ROM_ABITS = math.ceil(math.log2(ROM_LENGTH))

# ROM structure:
# "Commands" are 1 or more sequences of bytes to send as individual I2C transmissions.
# The very start of the ROM is an index of pairs of 16-bit numbers, (offset, length).
# There are as many of these as there are commands.
# To execute a command, start at `offset` and write the next `length` bytes as one I2C
# transmission.  The next two bytes are a 16-bit number that defines the length of
# the next transmission, or 0x0000 if finished.
