from abc import ABC, abstractmethod
from typing import Any, List, Optional, Self, Type, cast

from amaranth.lib.enum import Enum, IntEnum


def _enyom(enum: Type[IntEnum], value: Enum | int | str):
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
            if isinstance(v, int):
                return hex(v)
            elif isinstance(v, list):
                els = ", ".join(repr_v(vv) for vv in cast(List[Any], v))
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
    def __init__(self, data: List[int]):
        self.data = data

    def to_bytes(self) -> List[int]:
        return self.data


class SH1107Command(SH1107Sequence, ABC):
    @classmethod
    @abstractmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        for subclass in cls.__subclasses__():
            result = subclass.parse_one(cmd)
            if result is not None:
                return result

    @abstractmethod
    def to_bytes(self) -> List[int]:
        ...

    @classmethod
    def compose(cls, cmds: List[Self | DataBytes]) -> List[int]:
        dcs: List[bool] = []
        for cmd in cmds:
            dcs.append(isinstance(cmd, DataBytes))

        out: List[int] = []
        finished_control = False
        for i, cmd in enumerate(cmds):
            if not finished_control:
                if all(dc == dcs[i] for dc in dcs[i:]):
                    finished_control = True
                    out.append(ControlByte(False, DC(dcs[i])).to_byte())

            if not finished_control:
                for byte in cmd.to_bytes():
                    out.append(ControlByte(True, DC(dcs[i])).to_byte())
                    out.append(byte)
            else:
                out.extend(cmd.to_bytes())

        return out

    @classmethod
    def parse(cls, msg: List[int]) -> Optional[List[Self | DataBytes]]:
        class State(Enum):
            Control = 1
            ControlPartialCommand = 2
            Command = 3
            Data = 4

        continuation = True
        state: State = State.Control
        partial: List[int] = []

        out: List[Self | DataBytes] = []
        for b in msg:
            match state:
                case State.Control | State.ControlPartialCommand:
                    cb = ControlByte.parse_one(b)
                    assert cb is not None
                    continuation = cb.continuation
                    if state == State.ControlPartialCommand:
                        assert cb.dc == DC.Command, "received data in partial command"
                        state = State.Command
                    else:
                        state = State.Command if cb.dc == DC.Command else State.Data
                        partial = []

                case State.Command:
                    partial.append(b)
                    px = cls.parse_one(partial)
                    if px is not None:
                        partial = []
                        out.append(px)
                        if continuation:
                            state = State.Control
                    elif continuation:
                        state = State.ControlPartialCommand

                case State.Data:
                    partial.append(b)
                    if continuation:
                        state = State.Control
                        if isinstance(out[-1], DataBytes):
                            out[-1].data.extend(partial)
                        else:
                            out.append(DataBytes(partial))
                        partial = []

        match state:
            case State.Control:
                raise ValueError("Message ended in control state")
            case State.ControlPartialCommand:
                raise ValueError("Message ended in control state with partial command")
            case State.Command:
                assert not partial, "Message ended with partial command"
            case State.Data:
                assert not continuation, "Message ended in data state"
                if isinstance(out[-1], DataBytes):
                    out[-1].data.extend(partial)
                else:
                    out.append(DataBytes(partial))

        return out


class SetLowerColumnAddress(SH1107Command):
    # POR is 0x0
    def __init__(self, lower: int):
        assert 0 <= lower <= 0x0F
        self.lower = lower

    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 1 or not (0 <= cmd[0] <= 0x0F):
            return None
        return cls(cmd[0])

    def to_bytes(self) -> List[int]:
        return [self.lower]


class SetHigherColumnAddress(SH1107Command):
    # POR is 0x0
    def __init__(self, higher: int):
        assert 0 <= higher <= 0x07
        self.higher = higher

    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 1 or not (0x10 <= cmd[0] <= 0x17):
            return None
        return cls(cmd[0] & ~0x10)

    def to_bytes(self) -> List[int]:
        return [0x10 | self.higher]


class SetMemoryAddressingMode(SH1107Command):
    class Mode(IntEnum):
        Page = 0b0  # Column address increments (POR)
        Column = 0b1  # Page address increments

    def __init__(self, mode: Mode | int | str):
        self.mode = _enyom(self.Mode, mode)

    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 1 or not (0x20 <= cmd[0] <= 0x21):
            return None
        return cls(cls.Mode(cmd[0] & ~0x20))

    def to_bytes(self) -> List[int]:
        return [0x20 | self.mode]


class SetContrastControlRegister(SH1107Command):
    # POR is 0x80
    def __init__(self, level: int):
        assert 0 <= level <= 0xFF
        self.level = level

    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 2 or cmd[0] != 0x81:
            return None
        return cls(cmd[1])

    def to_bytes(self) -> List[int]:
        return [0x81, self.level]


class SetSegmentRemap(SH1107Command):
    class Adc(IntEnum):
        Normal = 0b0  # POR
        Flipped = 0b1  # (Vertically)

    def __init__(self, adc: Adc | int | str):
        self.adc = _enyom(self.Adc, adc)

    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 1 or not (0xA0 <= cmd[0] <= 0xA1):
            return None
        return cls(cls.Adc(cmd[0] & ~0xA0))

    def to_bytes(self) -> List[int]:
        return [0xA0 | self.adc]


# NOTE(AEC): I really don't quite understand what this does and
# need to play around with it on the hardware.
class SetMultiplexRatio(SH1107Command):
    # POR is 128
    def __init__(self, ratio: int):
        assert 0x01 <= ratio <= 0x80
        self.ratio = ratio

    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 2 or cmd[0] != 0xA8:
            return None
        return cls((cmd[1] & 0x7F) + 1)

    def to_bytes(self) -> List[int]:
        return [0xA8, self.ratio - 1]


class SetEntireDisplayOn(SH1107Command):
    # POR is off
    def __init__(self, on: bool):
        self.on = on

    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 1 or not (0xA4 <= cmd[0] <= 0xA5):
            return None
        return cls(cmd[0] == 0xA5)

    def to_bytes(self) -> List[int]:
        return [0xA4 | self.on]


class SetDisplayReverse(SH1107Command):
    # POR is off
    def __init__(self, reverse: bool):
        self.reverse = reverse

    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 1 or not (0xA6 <= cmd[0] <= 0xA7):
            return None
        return cls(cmd[0] == 0xA7)

    def to_bytes(self) -> List[int]:
        return [0xA6 | self.reverse]


class SetDisplayOffset(SH1107Command):
    # POR is 0
    def __init__(self, offset: int):
        assert 0 <= offset <= 0x7F
        self.offset = offset

    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 2 or cmd[0] != 0xD3:
            return None
        return cls(cmd[1] & 0x7F)

    def to_bytes(self) -> List[int]:
        return [0xD3, self.offset]


class SetDCDC(SH1107Command):
    # POR is on
    def __init__(self, on: bool):
        self.on = on

    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 2 or cmd[0] != 0xAD:
            return None
        return cls(cmd[1] == 0x8B)

    def to_bytes(self) -> List[int]:
        return [0xAD, 0x8A | self.on]


class DisplayOn(SH1107Command):
    # POR is off
    def __init__(self, on: bool):
        self.on = on

    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 1 or not (0xAE <= cmd[0] <= 0xAF):
            return None
        return cls(cmd[0] == 0xAF)

    def to_bytes(self) -> List[int]:
        return [0xAE | self.on]


class SetPageAddress(SH1107Command):
    # POR is 0
    def __init__(self, page: int):
        assert 0 <= page <= 0xF
        self.page = page

    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 1 or not (0xB0 <= cmd[0] <= 0xBF):
            return None
        return cls(cmd[0] & ~0xB0)

    def to_bytes(self) -> List[int]:
        return [0xB0 | self.page]


class SetCommonOutputScanDirection(SH1107Command):
    class Direction(IntEnum):
        Forwards = 0b0  # POR
        Backwards = 0b1

    def __init__(self, direction: Direction | str | int):
        self.direction = _enyom(self.Direction, direction)

    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 1 or not (0xC0 <= cmd[0] <= 0xCF):
            return None
        return cls(cls.Direction((cmd[0] & 8) == 8))

    def to_bytes(self) -> List[int]:
        return [0xC0 | (self.direction << 3)]


class SetDisplayClockFrequency(SH1107Command):
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

    def __init__(self, ratio: int, freq: Freq | str | int):
        assert 1 <= ratio <= 16
        self.ratio = ratio
        self.freq = _enyom(self.Freq, freq)

    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 2 or cmd[0] != 0xD5:
            return None
        return cls((cmd[1] & 0xF) + 1, cls.Freq(cmd[1] >> 4))

    def to_bytes(self) -> List[int]:
        return [0xD5, (self.freq << 4) | (self.ratio - 1)]


class SetPreDischargePeriod(SH1107Command):
    # POR is 2/2
    def __init__(self, precharge: int, discharge: int):
        assert 0 <= precharge <= 15
        assert 1 <= discharge <= 15
        self.precharge = precharge
        self.discharge = discharge

    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 2 or cmd[0] != 0xD9:
            return None
        return cls(cmd[1] & 0xF, cmd[1] >> 4)

    def to_bytes(self) -> List[int]:
        return [0xD9, (self.discharge << 4) | self.precharge]


class SetVCOMDeselectLevel(SH1107Command):
    # POR is 0x35
    # Meaningful values range from 0x00 to 0x40;
    # 0x40–0xFF are all β₁=1.0
    # Vcomh = β₁ * Vref
    #       = (0.430 + level * 0.006415) * Vref
    def __init__(self, level: int):
        assert 0 <= level <= 0xFF
        self.level = level

    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 2 or cmd[0] != 0xDB:
            return None
        return cls(cmd[1])

    def to_bytes(self) -> List[int]:
        return [0xDB, self.level]


class SetDisplayStartColumn(SH1107Command):
    # POR is 0
    def __init__(self, column: int):
        assert 0 <= column <= 0x7F
        self.column = column

    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 2 or cmd[0] != 0xDC:
            return None
        return cls(cmd[1] & 0x7F)

    def to_bytes(self) -> List[int]:
        return [0xDC, self.column]


class ReadModifyWrite(SH1107Command):
    # Must be paired with End command.  End causes
    # column/page address to return to where it was before RMW.
    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 1 or cmd[0] != 0xE0:
            return None
        return cls()

    def to_bytes(self) -> List[int]:
        return [0xE0]


class End(SH1107Command):
    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 1 or cmd[0] != 0xEE:
            return None
        return cls()

    def to_bytes(self) -> List[int]:
        return [0xEE]


class Nop(SH1107Command):
    @classmethod
    def parse_one(cls, cmd: List[int]) -> Optional[Self]:
        if len(cmd) != 1 or cmd[0] != 0xE3:
            return None
        return cls()

    def to_bytes(self) -> List[int]:
        return [0xE3]
