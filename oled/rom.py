import random
import struct

from .sh1107 import Base, Cmd, DataBytes

__all__ = ["ROM"]

random.seed("xyzabc")

init: list[Base | DataBytes] = [
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
    Cmd.DisplayOn(True),
    Cmd.SetMemoryAddressingMode("Page"),
    Cmd.SetLowerColumnAddress(0),
    Cmd.SetHigherColumnAddress(0),
]
for p in range(0x10):
    init += [
        Cmd.SetPageAddress(p),
        DataBytes([(x + p * 8) % 0x100 for x in range(0x80)]),
    ]
INIT_SEQUENCE = Cmd.compose(init)

disp: list[Base | DataBytes] = []
for p in range(0x04):
    disp += [
        Cmd.SetPageAddress(p),
        DataBytes([(x * 2 + p * 8) % 0x100 for x in range(0x80)]),
    ]
DISPLAY_SEQUENCE = Cmd.compose(disp)

disp2: list[Base | DataBytes] = [
    Cmd.SetSegmentRemap("Flipped"),
] + disp
DISPLAY2_SEQUENCE = Cmd.compose(disp2)

POWEROFF_SEQUENCE = Cmd.compose([Cmd.DisplayOn(False)])

rom = []
index = b""

for s in (INIT_SEQUENCE, DISPLAY_SEQUENCE, DISPLAY2_SEQUENCE, POWEROFF_SEQUENCE):
    index += struct.pack("<HH", len(rom), len(s))
    rom.extend(s)

rom_offset = 0x100

assert len(index) < rom_offset

ROM = index + (b"\x00" * (rom_offset - len(index))) + bytes(rom)
