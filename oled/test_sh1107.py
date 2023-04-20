import unittest
from typing import Literal, Tuple

from .sh1107 import Base, Cmd, ControlByte, DataBytes, ParseState


class TestSH1107Command(unittest.TestCase):
    PAIRS = [
        ([0x07], Cmd.SetLowerColumnAddress(0x7)),
        ([0x13], Cmd.SetHigherColumnAddress(0x3)),
        ([0x18], None),
        ([0x20], Cmd.SetMemoryAddressingMode("Page")),
        ([0x21], Cmd.SetMemoryAddressingMode("Column")),
        ([0x81], None),
        ([0x81, 0x7F], Cmd.SetContrastControlRegister(0x7F)),
        ([0x81, 0x00], Cmd.SetContrastControlRegister(0x00)),
        ([0xA0], Cmd.SetSegmentRemap("Normal")),
        ([0xA1], Cmd.SetSegmentRemap("Flipped")),
        ([0xA8, 0x00], Cmd.SetMultiplexRatio(0x01)),
        ([0xA8, 0x7F], Cmd.SetMultiplexRatio(0x80)),
        ([0xA8, 0xA7], Cmd.SetMultiplexRatio(0x28), [0xA8, 0x27]),
        ([0xA4], Cmd.SetEntireDisplayOn(False)),
        ([0xA5], Cmd.SetEntireDisplayOn(True)),
        ([0xA6], Cmd.SetDisplayReverse(False)),
        ([0xA7], Cmd.SetDisplayReverse(True)),
        ([0xD3, 0x00], Cmd.SetDisplayOffset(0)),
        ([0xD3, 0x7F], Cmd.SetDisplayOffset(0x7F)),
        ([0xD3, 0xC8], Cmd.SetDisplayOffset(0x48), [0xD3, 0x48]),
        ([0xAD, 0x8A], Cmd.SetDCDC(False)),
        ([0xAD, 0x8B], Cmd.SetDCDC(True)),
        ([0xAE], Cmd.DisplayOn(False)),
        ([0xAF], Cmd.DisplayOn(True)),
        ([0xB0], Cmd.SetPageAddress(0x0)),
        ([0xB9], Cmd.SetPageAddress(0x9)),
        ([0xC0], Cmd.SetCommonOutputScanDirection("Forwards")),
        ([0xC5], Cmd.SetCommonOutputScanDirection("Forwards"), [0xC0]),
        ([0xC8], Cmd.SetCommonOutputScanDirection("Backwards")),
        ([0xCF], Cmd.SetCommonOutputScanDirection("Backwards"), [0xC8]),
        ([0xD5, 0b01010000], Cmd.SetDisplayClockFrequency(1, "Zero")),
        ([0xD5, 0b11001010], Cmd.SetDisplayClockFrequency(11, "Pos35")),
        ([0xD5, 0b00010111], Cmd.SetDisplayClockFrequency(8, "Neg20")),
        ([0xD9, 0b00100010], Cmd.SetPreDischargePeriod(2, 2)),
        ([0xD9, 0b11111111], Cmd.SetPreDischargePeriod(15, 15)),
        ([0xDB, 0x00], Cmd.SetVCOMDeselectLevel(0x00)),
        ([0xDB, 0x3F], Cmd.SetVCOMDeselectLevel(0x3F)),
        ([0xDB, 0xAA], Cmd.SetVCOMDeselectLevel(0xAA)),
        ([0xDC, 0x03], Cmd.SetDisplayStartColumn(0x03)),
        ([0xDC, 0x66], Cmd.SetDisplayStartColumn(0x66)),
        ([0xDC, 0xAF], Cmd.SetDisplayStartColumn(0x2F), [0xDC, 0x2F]),
        ([0xE0], Cmd.ReadModifyWrite()),
        ([0xEE], Cmd.End()),
        ([0xE3], Cmd.Nop()),
    ]

    CONTROL_BYTES = [
        (0x00, ControlByte(False, "Command")),
        (0x80, ControlByte(True, "Command")),
        (0x40, ControlByte(False, "Data")),
        (0xC0, ControlByte(True, "Data")),
    ]

    COMPOSE_PAIRS: list[Tuple[list[Base | DataBytes], list[int]]] = [
        (
            [
                Cmd.SetDisplayClockFrequency(7, "Neg5"),
                Cmd.SetDCDC(True),
                Cmd.SetSegmentRemap("Normal"),
                Cmd.SetVCOMDeselectLevel(0x40),
                Cmd.SetMemoryAddressingMode("Page"),
                Cmd.DisplayOn(True),
                Cmd.SetPageAddress(0),
                Cmd.SetLowerColumnAddress(0),
                Cmd.SetHigherColumnAddress(0),
                DataBytes(
                    [
                        0xFF,
                        0x77,
                    ]
                ),
                Cmd.SetPageAddress(0x8),
                DataBytes(
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

    PARSE_PARTIAL: list[
        Tuple[
            list[int],
            list[Base | DataBytes],
            list[int],
            Literal["Ctrl", "Cmd", "Data"],
            bool,
            Literal["F", "M", "U"],
        ]
    ] = [
        # 0x80 0xD5 0x80 0x46 0x00 0xAF:
        # Co/C SetDisplayClockFrequency Co/C 7, Neg5 !Co/C DisplayOn True
        #
        # (input, output, leftover, end state, end continuation, fish ok/more needed/unrecoverable)
        #
        ([0x80], [], [0x80], "Cmd", True, "M"),
        ([0x80, 0xD5], [], [0x80, 0xD5], "Ctrl", True, "M"),
        ([0x80, 0xD5, 0x80], [], [0x80, 0xD5, 0x80], "Cmd", True, "M"),
        (
            [0x80, 0xD5, 0x80, 0x46],
            [Cmd.SetDisplayClockFrequency(7, "Neg5")],
            [],
            "Ctrl",
            True,
            "M",
        ),
        (
            [0x80, 0xD5, 0x80, 0x46, 0x00],
            [Cmd.SetDisplayClockFrequency(7, "Neg5")],
            [0x00],
            "Cmd",
            False,
            "M",
        ),
        (
            [0x80, 0xD5, 0x80, 0x46, 0x00, 0xAF],
            [Cmd.SetDisplayClockFrequency(7, "Neg5"), Cmd.DisplayOn(True)],
            [],
            "Cmd",
            False,
            "F",
        ),
        (
            [0x80, 0xD5, 0x80, 0x46, 0x00, 0xAF, 0xAE],
            [
                Cmd.SetDisplayClockFrequency(7, "Neg5"),
                Cmd.DisplayOn(True),
                Cmd.DisplayOn(False),
            ],
            [],
            "Cmd",
            False,
            "F",
        ),
        (
            [0x80, 0xAF, 0x80, 0xD5],
            [Cmd.DisplayOn(True)],
            [0x80, 0xD5],
            "Ctrl",
            True,
            "M",
        ),
        (
            [0x80, 0xAF, 0x80, 0xD5, 0x80],
            [Cmd.DisplayOn(True)],
            [0x80, 0xD5, 0x80],
            "Cmd",
            True,
            "M",
        ),
        (
            [0x80, 0xAF, 0x80, 0xD5, 0x00],
            [Cmd.DisplayOn(True)],
            [0x80, 0xD5, 0x00],
            "Cmd",
            False,
            "M",
        ),
        (
            [0x80, 0xAF, 0x00],
            [Cmd.DisplayOn(True)],
            [0x00],
            "Cmd",
            False,
            "M",
        ),
        (
            [0x80, 0xAF, 0x00, 0xD5],
            [Cmd.DisplayOn(True)],
            [0x00, 0xD5],
            "Cmd",
            False,
            "M",
        ),
        (
            [0x80, 0xAF, 0x00, 0xD5, 0x46],
            [Cmd.DisplayOn(True), Cmd.SetDisplayClockFrequency(7, "Neg5")],
            [],
            "Cmd",
            False,
            "F",
        ),
        (
            [0x00, 0xAF, 0x80],
            [Cmd.DisplayOn(True)],
            [0x80],
            "Cmd",
            False,
            "M",  # TODO: 0x80 invalid start of command byte, will never match = unrecov
        ),
        (
            [0x00],
            [],
            [0x00],
            "Cmd",
            False,
            "M",  # empty section invalid
        ),
        (
            [0x00, 0xAF],
            [Cmd.DisplayOn(True)],
            [],
            "Cmd",
            False,
            "F",
        ),
        (
            [0x80, 0xAF],
            [Cmd.DisplayOn(True)],
            [],
            "Ctrl",
            True,
            "M",
        ),
        (
            [0x40],
            [],
            [0x40],
            "Data",
            False,
            "M",  # empty section invalid
        ),
        (
            [0x40, 0xAA],
            [DataBytes([0xAA])],
            [],
            "Data",
            False,
            "F",
        ),
        (
            [0x40],
            [],
            [0x40],
            "Data",
            False,
            "M",
        ),
        (
            [0x40, 0xAA, 0x40],
            [DataBytes([0xAA, 0x40])],
            [],
            "Data",
            False,
            "F",
        ),
        (
            [0x40, 0xAA, 0x40, 0xAA],
            [DataBytes([0xAA, 0x40, 0xAA])],
            [],
            "Data",
            False,
            "F",
        ),
        (
            [0xC0],
            [],
            [0xC0],
            "Data",
            True,
            "M",
        ),
        (
            [0xC0, 0xAA],
            [DataBytes([0xAA])],
            [],
            "Ctrl",
            True,
            "M",
        ),
    ]

    def test_parse_one(self):
        for data, value, *_ in self.PAIRS:
            self.assertEqual(Base.parse_one(data), value)

    def test_to_bytes(self):
        for data, value, *maybe in self.PAIRS:
            if value is None:
                continue
            if len(maybe) == 1:
                data = maybe[0]
            self.assertEqual(value.to_bytes(), data)

    def test_control_bytes(self):
        for b, cb in self.CONTROL_BYTES:
            self.assertEqual(ControlByte.parse_one(b), cb)
            self.assertEqual(cb.to_byte(), b)

    def test_compose(self):
        for cmds, bytes in self.COMPOSE_PAIRS:
            self.assertEqual(Cmd.compose(cmds), bytes)

    def test_parse(self):
        for cmds, bytes in self.COMPOSE_PAIRS:
            self.assertParseComplete(bytes, cmds)

    def assertParseComplete(self, bytes: list[int], cmds: list[Base | DataBytes]):
        parser = Cmd.Parser()
        result = parser.feed(bytes)
        self.assertEqual(result, cmds)
        self.assertTrue(parser.valid_finish)  # implies not unrecoverable

    def test_parse_partial(self):
        # (input, output, leftover, end state, end continuation, fish ok/more needed/unrecoverable)

        for bytes, cmds, leftover, state, continuation, fmu in self.PARSE_PARTIAL:
            print(bytes, cmds, leftover, state, continuation, fmu)
            parser = Cmd.Parser()
            result = parser.feed(bytes)
            print(result)
            print()
            self.assertEqual(result, cmds)
            self.assertEqual(parser.bytes, leftover)
            match state:
                case "Ctrl":
                    self.assertIn(
                        parser.state,
                        [ParseState.Control, ParseState.ControlPartialCommand],
                    )
                case "Cmd":
                    self.assertEqual(parser.state, ParseState.Command)
                case "Data":
                    self.assertEqual(parser.state, ParseState.Data)
            self.assertEqual(parser.continuation, continuation)
            match fmu:
                case "F":
                    self.assertTrue(parser.valid_finish)
                    self.assertFalse(parser.unrecoverable)
                case "M":
                    self.assertFalse(parser.valid_finish)
                    self.assertFalse(parser.unrecoverable)
                case "U":
                    self.assertFalse(parser.valid_finish)
                    self.assertTrue(parser.unrecoverable)


if __name__ == "__main__":
    unittest.main()
