from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional, Self, Tuple, Type, cast

from amaranth.lib.enum import IntEnum

__all__ = ["Base", "Cmd", "DataBytes", "ControlByte"]


def _enyom(enum: Type[IntEnum], value: Enum | int | str) -> Any:
    if isinstance(value, enum):
        return value
    elif isinstance(value, int):
        return enum(value)
    elif isinstance(value, str):
        return enum[value]
    else:
        raise TypeError


class SH1107Sequence:
    def __repr__(self) -> str:
        def repr_v(v: Any) -> str:
            if isinstance(v, Enum):
                return v.name
            elif isinstance(v, int):
                return hex(v)
            elif isinstance(v, list):
                els = ", ".join(repr_v(vv) for vv in cast(list[Any], v))
                return f"[{els}]"
            else:
                return repr(v)

        ppdict = " ".join(f"{k}={repr_v(v)}" for k, v in self.__dict__.items())
        return f"<{self.__class__.__name__} {ppdict}>"

    def __eq__(self, other: Any):
        if type(other) is not type(self):
            return NotImplemented
        return self.__dict__ == other.__dict__


class DC(IntEnum):
    Command = 0b0
    Data = 0b1


class ControlByte(SH1107Sequence):
    def __init__(self, continuation: bool, dc: DC | int | str):
        self.continuation = continuation
        self.dc = _enyom(DC, dc)

    @classmethod
    def parse_one(cls, b: int) -> Optional[Self]:
        if b & 0x3F:
            return None
        return cls((b & 0x80) == 0x80, DC((b & 0x40) == 0x40))

    def to_byte(self) -> int:
        return (self.continuation << 7) | (self.dc << 6)


class DataBytes(SH1107Sequence):
    def __init__(self, data: list[int]):
        self.data = data

    def to_bytes(self) -> list[int]:
        return self.data


class Base(SH1107Sequence, ABC):
    """
    Return parsed sequence, True if cmd is prefix of this(/any) sequence, False if no
    match at all.
    """

    @classmethod
    @abstractmethod
    def parse_one(cls, cmd: list[int]) -> Self | bool:
        for subclass in cls.__subclasses__():
            result = subclass.parse_one(cmd)
            if result is not False:
                return result
        return False

    @abstractmethod
    def to_bytes(self) -> list[int]:
        ...

    def to_byte(self) -> int:
        bytes = self.to_bytes()
        assert len(bytes) == 1
        return bytes[0]


class ParseState(Enum):
    Control = 1
    Command = 2
    Data = 3


class Cmd:
    class Parser:
        valid_finish: bool  # this may be inferrable based on state+continuation
        unrecoverable: bool  # exclusive with valid_finish

        state: ParseState
        continuation: bool

        bytes: list[int]
        partial_cmd: list[int]

        def __init__(self):
            self.valid_finish = False
            self.unrecoverable = False

            self.state = ParseState.Control
            self.continuation = True

            self.bytes = []
            self.partial_cmd = []

        def feed(self, bytes_in: list[int]) -> list[Base | DataBytes]:
            assert not self.unrecoverable

            self.bytes.extend(bytes_in)

            cmds: list[Base | DataBytes] = []

            while self.bytes:
                b = self.bytes[0]
                self.valid_finish = False
                match self.state:
                    case ParseState.Control:
                        cb = ControlByte.parse_one(b)
                        if cb is None:
                            self.unrecoverable = True
                            return cmds
                        self.continuation = cb.continuation

                        if self.partial_cmd and cb.dc != DC.Command:
                            # partial command followed by data
                            self.unrecoverable = True
                            return cmds

                        self.state = (
                            ParseState.Command
                            if cb.dc == DC.Command
                            else ParseState.Data
                        )

                        self.valid_finish = (
                            not self.partial_cmd
                        )  # may be just setting mode for read

                    case ParseState.Command:
                        self.partial_cmd.append(b)
                        px = Base.parse_one(self.partial_cmd)
                        if px is False:
                            self.unrecoverable = True
                            return cmds

                        if px is not True:
                            self.partial_cmd = []
                            cmds.append(px)

                        if self.continuation:
                            self.state = ParseState.Control
                        else:
                            self.valid_finish = px is not True

                    case ParseState.Data:
                        if cmds and isinstance(cmds[-1], DataBytes):
                            cmds[-1].data.append(b)
                        else:
                            cmds.append(DataBytes([b]))

                        if self.continuation:
                            self.state = ParseState.Control
                        else:
                            self.valid_finish = True

                self.bytes = self.bytes[1:]

            return cmds

    @staticmethod
    def compose(*cmds_in: list[Base | DataBytes]) -> list[list[int]]:
        return Cmd.compose_with_offsets(*cmds_in)[0]

    @staticmethod
    def compose_with_offsets(
        *seqs: list[Base | DataBytes | str],
    ) -> Tuple[list[list[int]], dict[str, int]]:
        curr_offset = 0
        offsets: dict[str, int] = {}
        result: list[list[int]] = []

        for seq in seqs:
            bytes = Cmd._compose_with_offsets_single(seq, offsets, curr_offset)
            result.append(bytes)
            curr_offset += len(bytes)

        return result, offsets

    @staticmethod
    def _compose_with_offsets_single(
        cmds: list[Base | DataBytes | str],
        offsets: dict[str, int],
        curr_offset: int,
    ) -> list[int]:
        dcs: list[bool | None] = []
        for cmd in cmds:
            if isinstance(cmd, str):
                dcs.append(None)
            else:
                dcs.append(isinstance(cmd, DataBytes))

        out: list[int] = []
        finished_control = False
        for i, cmd in enumerate(cmds):
            if isinstance(cmd, str):
                offsets[cmd] = curr_offset + len(out)
                continue

            if not finished_control:
                if all(dc is None or dc == dcs[i] for dc in dcs[i:]):
                    finished_control = True
                    out.append(ControlByte(False, DC(dcs[i])).to_byte())

            if not finished_control:
                for byte in cmd.to_bytes():
                    out.append(ControlByte(True, DC(dcs[i])).to_byte())
                    out.append(byte)
            else:
                out.extend(cmd.to_bytes())

        return out

    class SetLowerColumnAddress(Base):
        # POR is 0x0
        def __init__(self, lower: int):
            assert 0 <= lower <= 0x0F
            self.lower = lower

        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if len(cmd) != 1 or not (0 <= cmd[0] <= 0x0F):
                return False
            return cls(cmd[0])

        def to_bytes(self) -> list[int]:
            return [self.lower]

    class SetHigherColumnAddress(Base):
        # POR is 0x0
        def __init__(self, higher: int):
            assert 0 <= higher <= 0x07
            self.higher = higher

        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if len(cmd) != 1 or not (0x10 <= cmd[0] <= 0x17):
                return False
            return cls(cmd[0] & ~0x10)

        def to_bytes(self) -> list[int]:
            return [0x10 | self.higher]

    class SetMemoryAddressingMode(Base):
        class Mode(IntEnum):
            Page = 0b0  # Column address increments (POR)
            Vertical = 0b1  # Page address increments

        mode: Mode

        def __init__(self, mode: Mode | int | str):
            self.mode = _enyom(self.Mode, mode)

        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if len(cmd) != 1 or not (0x20 <= cmd[0] <= 0x21):
                return False
            return cls(cls.Mode(cmd[0] & ~0x20))

        def to_bytes(self) -> list[int]:
            return [0x20 | self.mode]

    class SetContrastControlRegister(Base):
        # POR is 0x80
        def __init__(self, level: int):
            assert 0 <= level <= 0xFF
            self.level = level

        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if cmd[0] != 0x81 or len(cmd) > 2:
                return False
            elif len(cmd) < 2:
                return True
            return cls(cmd[1])

        def to_bytes(self) -> list[int]:
            return [0x81, self.level]

    class SetSegmentRemap(Base):
        class Adc(IntEnum):
            Normal = 0b0  # POR
            Flipped = 0b1  # (Vertically)

        adc: Adc

        def __init__(self, adc: Adc | int | str):
            self.adc = _enyom(self.Adc, adc)

        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if len(cmd) != 1 or not (0xA0 <= cmd[0] <= 0xA1):
                return False
            return cls(cls.Adc(cmd[0] & ~0xA0))

        def to_bytes(self) -> list[int]:
            return [0xA0 | self.adc]

    class SetMultiplexRatio(Base):
        """
        Seems to mean: how many columns to actually draw.  Needs to be called
        for different sizes of display to work correctly.

        POR is 128
        """

        def __init__(self, ratio: int):
            assert 0x01 <= ratio <= 0x80
            self.ratio = ratio

        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if cmd[0] != 0xA8 or len(cmd) > 2:
                return False
            elif len(cmd) < 2:
                return True
            return cls((cmd[1] & 0x7F) + 1)

        def to_bytes(self) -> list[int]:
            return [0xA8, self.ratio - 1]

    class SetEntireDisplayOn(Base):
        # POR is off
        def __init__(self, on: bool):
            self.on = on

        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if len(cmd) != 1 or not (0xA4 <= cmd[0] <= 0xA5):
                return False
            return cls(cmd[0] == 0xA5)

        def to_bytes(self) -> list[int]:
            return [0xA4 | self.on]

    class SetDisplayReverse(Base):
        # POR is off
        def __init__(self, reverse: bool):
            self.reverse = reverse

        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if len(cmd) != 1 or not (0xA6 <= cmd[0] <= 0xA7):
                return False
            return cls(cmd[0] == 0xA7)

        def to_bytes(self) -> list[int]:
            return [0xA6 | self.reverse]

    class SetDisplayOffset(Base):
        """
        This appears to do exactly the same thing as SetDisplayStartLine on my
        hardware; the image is scrolled (and wrapped) left.

        Internally this appears to be done by changing which COMx is used for
        each column, but I'm not sure it .. matters?  It doesn't appear to have
        any different effect when we change COM scan direction or remap seg
        either.

        POR is 0
        """

        def __init__(self, offset: int):
            assert 0 <= offset <= 0x7F
            self.offset = offset

        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if cmd[0] != 0xD3 or len(cmd) > 2:
                return False
            elif len(cmd) < 2:
                return True
            return cls(cmd[1] & 0x7F)

        def to_bytes(self) -> list[int]:
            return [0xD3, self.offset]

    class SetDCDC(Base):
        # POR is on
        def __init__(self, on: bool):
            self.on = on

        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if cmd[0] != 0xAD or len(cmd) > 2:
                return False
            elif len(cmd) < 2:
                return True
            return cls(cmd[1] == 0x8B)

        def to_bytes(self) -> list[int]:
            return [0xAD, 0x8A | self.on]

    class DisplayOn(Base):
        # POR is off
        def __init__(self, on: bool):
            self.on = on

        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if len(cmd) != 1 or not (0xAE <= cmd[0] <= 0xAF):
                return False
            return cls(cmd[0] == 0xAF)

        def to_bytes(self) -> list[int]:
            return [0xAE | self.on]

    class SetPageAddress(Base):
        # POR is 0
        def __init__(self, page: int):
            assert 0 <= page <= 0xF
            self.page = page

        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if len(cmd) != 1 or not (0xB0 <= cmd[0] <= 0xBF):
                return False
            return cls(cmd[0] & ~0xB0)

        def to_bytes(self) -> list[int]:
            return [0xB0 | self.page]

    class SetCommonOutputScanDirection(Base):
        class Direction(IntEnum):
            Forwards = 0b0  # POR
            Backwards = 0b1

        direction: Direction

        def __init__(self, direction: Direction | str | int):
            self.direction = _enyom(self.Direction, direction)

        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if len(cmd) != 1 or not (0xC0 <= cmd[0] <= 0xCF):
                return False
            return cls(cls.Direction((cmd[0] & 8) == 8))

        def to_bytes(self) -> list[int]:
            return [0xC0 | (self.direction << 3)]

    class SetDisplayClockFrequency(Base):
        # POR is 1 / 0%
        class Freq(IntEnum):
            Neg25 = 0b0000
            Neg20 = 0b0001
            Neg15 = 0b0010
            Neg10 = 0b0011
            Neg5 = 0b0100
            Zero = 0b0101  # POR
            Pos5 = 0b0110
            Pos10 = 0b0111
            Pos15 = 0b1000
            Pos20 = 0b1001
            Pos25 = 0b1010
            Pos30 = 0b1011
            Pos35 = 0b1100
            Pos40 = 0b1101
            Pos45 = 0b1110
            Pos50 = 0b1111

            def __int__(self) -> int:
                match self:
                    case self.Neg25:
                        return -25
                    case self.Neg20:
                        return -20
                    case self.Neg15:
                        return -15
                    case self.Neg10:
                        return -10
                    case self.Neg5:
                        return -5
                    case self.Zero:
                        return 0
                    case self.Pos5:
                        return 5
                    case self.Pos10:
                        return 10
                    case self.Pos15:
                        return 15
                    case self.Pos20:
                        return 20
                    case self.Pos25:
                        return 25
                    case self.Pos30:
                        return 30
                    case self.Pos35:
                        return 35
                    case self.Pos40:
                        return 40
                    case self.Pos45:
                        return 45
                    case self.Pos50:
                        return 50

        freq: Freq

        def __init__(self, ratio: int, freq: Freq | str | int):
            assert 1 <= ratio <= 16
            self.ratio = ratio
            self.freq = _enyom(self.Freq, freq)

        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if cmd[0] != 0xD5 or len(cmd) > 2:
                return False
            elif len(cmd) < 2:
                return True
            return cls((cmd[1] & 0xF) + 1, cls.Freq(cmd[1] >> 4))

        def to_bytes(self) -> list[int]:
            return [0xD5, (self.freq << 4) | (self.ratio - 1)]

    class SetPreDischargePeriod(Base):
        # POR is 2/2
        def __init__(self, precharge: int, discharge: int):
            assert 0 <= precharge <= 15
            assert 1 <= discharge <= 15
            self.precharge = precharge
            self.discharge = discharge

        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if cmd[0] != 0xD9 or len(cmd) > 2:
                return False
            elif len(cmd) < 2:
                return True
            return cls(cmd[1] & 0xF, cmd[1] >> 4)

        def to_bytes(self) -> list[int]:
            return [0xD9, (self.discharge << 4) | self.precharge]

    class SetVCOMDeselectLevel(Base):
        # POR is 0x35
        # Meaningful values range from 0x00 to 0x40;
        # 0x40–0xFF are all β₁=1.0
        # Vcomh = β₁ * Vref
        #       = (0.430 + level * 0.006415) * Vref
        def __init__(self, level: int):
            assert 0 <= level <= 0xFF
            self.level = level

        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if cmd[0] != 0xDB or len(cmd) > 2:
                return False
            elif len(cmd) < 2:
                return True
            return cls(cmd[1])

        def to_bytes(self) -> list[int]:
            return [0xDB, self.level]

    class SetDisplayStartLine(Base):
        """
        The datasheet says this is the one to use for smooth scrolling. Notably,
        it specifies the _column address_ for COM0.  If you start at 0 and go up
        through 127, you'll smoothly move the contents of the display left
        (wrapping around to the right), one pixel at a time.

        Note that it has nothing to do with rows — this is a horizontal scroll
        only.

        POR is 0
        """

        def __init__(self, column: int):
            assert 0 <= column <= 0x7F
            self.column = column

        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if cmd[0] != 0xDC or len(cmd) > 2:
                return False
            elif len(cmd) < 2:
                return True
            return cls(cmd[1] & 0x7F)

        def to_bytes(self) -> list[int]:
            return [0xDC, self.column]

    class ReadModifyWrite(Base):
        # Must be paired with End command.  End causes
        # column/page address to return to where it was before RMW.
        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if len(cmd) != 1 or cmd[0] != 0xE0:
                return False
            return cls()

        def to_bytes(self) -> list[int]:
            return [0xE0]

    class End(Base):
        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if len(cmd) != 1 or cmd[0] != 0xEE:
                return False
            return cls()

        def to_bytes(self) -> list[int]:
            return [0xEE]

    class Nop(Base):
        @classmethod
        def parse_one(cls, cmd: list[int]) -> Self | bool:
            if len(cmd) != 1 or cmd[0] != 0xE3:
                return False
            return cls()

        def to_bytes(self) -> list[int]:
            return [0xE3]
