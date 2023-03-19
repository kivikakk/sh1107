import unittest

from . import sh1107


class TestSH1107Command(unittest.TestCase):
    PAIRS = [
        ([0x07], sh1107.SetLowerColumnAddress(0x7)),
        ([0x13], sh1107.SetHigherColumnAddress(0x3)),
        ([0x18], None),
        ([0x20], sh1107.SetMemoryAddressingMode("Page")),
        ([0x21], sh1107.SetMemoryAddressingMode("Column")),
        ([0x81, 0x7F], sh1107.SetContrastControlRegister(0x7F)),
        ([0x81, 0x00], sh1107.SetContrastControlRegister(0x00)),
        ([0xA0], sh1107.SetSegmentRemap("Normal")),
        ([0xA1], sh1107.SetSegmentRemap("Flipped")),
        ([0xA8, 0x00], sh1107.SetMultiplexRatio(0x01)),
        ([0xA8, 0x7F], sh1107.SetMultiplexRatio(0x80)),
        ([0xA8, 0xA7], sh1107.SetMultiplexRatio(0x28), [0xA8, 0x27]),
        ([0xA4], sh1107.SetEntireDisplayOn(False)),
        ([0xA5], sh1107.SetEntireDisplayOn(True)),
        ([0xA6], sh1107.SetDisplayReverse(False)),
        ([0xA7], sh1107.SetDisplayReverse(True)),
        ([0xD3, 0x00], sh1107.SetDisplayOffset(0)),
        ([0xD3, 0x7F], sh1107.SetDisplayOffset(0x7F)),
        ([0xD3, 0xC8], sh1107.SetDisplayOffset(0x48), [0xD3, 0x48]),
        ([0xAD, 0x8A], sh1107.SetDCDC(False)),
        ([0xAD, 0x8B], sh1107.SetDCDC(True)),
        ([0xAE], sh1107.DisplayOn(False)),
        ([0xAF], sh1107.DisplayOn(True)),
        ([0xB0], sh1107.SetPageAddress(0x0)),
        ([0xB9], sh1107.SetPageAddress(0x9)),
        ([0xC0], sh1107.SetCommonOutputScanDirection("Forwards")),
        ([0xC5], sh1107.SetCommonOutputScanDirection("Forwards"), [0xC0]),
        ([0xC8], sh1107.SetCommonOutputScanDirection("Backwards")),
        ([0xCF], sh1107.SetCommonOutputScanDirection("Backwards"), [0xC8]),
        ([0xD5, 0b01010000], sh1107.SetDisplayClockFrequency(1, "Zero")),
        ([0xD5, 0b11001010], sh1107.SetDisplayClockFrequency(11, "Pos35")),
        ([0xD5, 0b00010111], sh1107.SetDisplayClockFrequency(8, "Neg20")),
        ([0xD9, 0b00100010], sh1107.SetPreDischargePeriod(2, 2)),
        ([0xD9, 0b11111111], sh1107.SetPreDischargePeriod(15, 15)),
        ([0xDB, 0x00], sh1107.SetVCOMDeselectLevel(0x00)),
        ([0xDB, 0x3F], sh1107.SetVCOMDeselectLevel(0x3F)),
        ([0xDB, 0xAA], sh1107.SetVCOMDeselectLevel(0xAA)),
        ([0xDC, 0x03], sh1107.SetDisplayStartColumn(0x03)),
        ([0xDC, 0x66], sh1107.SetDisplayStartColumn(0x66)),
        ([0xDC, 0xAF], sh1107.SetDisplayStartColumn(0x2F), [0xDC, 0x2F]),
        ([0xE0], sh1107.ReadModifyWrite()),
        ([0xEE], sh1107.End()),
        ([0xE3], sh1107.Nop()),
    ]

    CONTROL_BYTES = [
        ([0x00], sh1107.ControlByte(False, "Command")),
        ([0x80], sh1107.ControlByte(True, "Command")),
        ([0x40], sh1107.ControlByte(False, "Data")),
        ([0xC0], sh1107.ControlByte(True, "Data")),
    ]

    COMPOSE_PAIRS = [
        (
            [
                sh1107.SetDisplayClockFrequency(7, "Neg5"),
                sh1107.SetDCDC(True),
                sh1107.SetSegmentRemap("Normal"),
                sh1107.SetVCOMDeselectLevel(0x40),
                sh1107.SetMemoryAddressingMode("Page"),
                sh1107.DisplayOn(True),
                sh1107.SetPageAddress(0),
                sh1107.SetLowerColumnAddress(0),
                sh1107.SetHigherColumnAddress(0),
                sh1107.DataBytes(
                    [
                        0xFF,
                        0x77,
                    ]
                ),
                sh1107.SetPageAddress(0x8),
                sh1107.DataBytes(
                    [
                        0x11,
                        0x88,
                    ]
                ),
            ],
            [
                0x80,  # Co/C
                0xD5,  # SetDisplayClockFrequency
                0x80,  # Co/C
                0x46,  # 7, Neg5
                0x80,  # Co/C
                0xAD,  # SetDCDC
                0x80,  # Co/C
                0x8B,  # on
                0x80,  # Co/C
                0xA0,  # SetSegmentRemap Normal
                0x80,  # Co/C
                0xDB,  # SetVCOMDeselectLevel
                0x80,  # Co/C
                0x40,  # 0x40
                0x80,  # Co/C
                0x20,  # SetMemoryAddressingMode Page
                0x80,  # Co/C
                0xAF,  # DisplayOn True
                0x80,  # Co/C
                0xB0,  # SetPageAddress 0
                0x80,  # Co/C
                0x00,  # SetLowerColumnAddress 0
                0x80,  # Co/C
                0x10,  # SetHigherColumnAddress 0
                0xC0,  # Co/D
                0xFF,  # DataBytes
                0xC0,  # Co/D
                0x77,  # DataBytes
                0x80,  # Co/C
                0xB8,  # SetPageAddress 0x8
                0x40,  # !Co/D
                0x11,  # DataBytes
                0x88,  # DataBytes
            ],
        ),
    ]

    def test_parse(self):
        for data, value, *_ in self.PAIRS:
            self.assertEqual(sh1107.SH1107Command.parse(data), value)

    def test_to_bytes(self):
        for data, value, *maybe in self.PAIRS:
            if value is None:
                continue
            if len(maybe) == 1:
                data = maybe[0]
            self.assertEqual(value.to_bytes(), data)

    def test_control_bytes(self):
        for data, value in self.CONTROL_BYTES:
            self.assertEqual(sh1107.ControlByte.parse(data), value)
            self.assertEqual(value.to_bytes(), data)

    def test_compose(self):
        for cmds, bytes in self.COMPOSE_PAIRS:
            self.assertEqual(sh1107.SH1107Command.compose(cmds), bytes)


if __name__ == "__main__":
    unittest.main()
