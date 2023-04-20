from enum import Enum
from typing import Any, Callable, Literal, Optional, TypeAlias

from amaranth.lib.enum import IntEnum

import sim
from oled import OLED, Top
from oled.sh1107 import Base, Cmd, DataBytes

__all__ = ["Connector"]


class Value:
    value: int
    stable: bool

    def __init__(self, value: int, stable: bool):
        self.value = value
        self.stable = stable

    @property
    def stable_high(self) -> bool:
        return bool(self.stable and self.value)

    @property
    def stable_low(self) -> bool:
        return bool(self.stable and not self.value)

    @property
    def falling(self) -> bool:
        return bool(not self.stable and not self.value)

    @property
    def rising(self) -> bool:
        return bool(not self.stable and self.value)


Level: TypeAlias = int
DEBUG: int = 0
INFO: int = 1
WARN: int = 2


class ByteReceiver:
    class State(IntEnum):
        IDLE = 0
        START_SDA_LOW = 1
        WAIT_BIT_SCL_RISE = 2
        WAIT_BIT_SCL_FALL = 3
        WAIT_ACK_SCL_RISE = 4
        WAIT_ACK_SCL_FALL = 5

    class Result(IntEnum):
        PASS = 0
        ACK_NACK = 1
        RELEASE_SDA = 2
        FISH = 3
        ERROR = 4

    state: State
    bits: list[Literal[0, 1]]
    byte: int

    def __init__(self):
        self.state = self.State.IDLE
        self.bits = []
        self.byte = 0

    def process(
        self,
        scl_o: Value,
        scl_oe: Value,
        sda_o: Value,
        sda_oe: Value,
    ) -> Result:
        match self.state:
            case self.State.IDLE:
                if (
                    scl_oe.stable_high
                    and scl_o.stable_high
                    and sda_oe.stable_high
                    and sda_o.falling
                ):
                    self.state = self.State.START_SDA_LOW
                    self.bits = []
                    self.byte = 0
                    return self.Result.RELEASE_SDA

            case self.State.START_SDA_LOW:
                if (
                    scl_oe.stable_high
                    and scl_o.falling
                    and sda_oe.stable_high
                    and sda_o.stable_low
                ):
                    self.state = self.State.WAIT_BIT_SCL_RISE
                elif not all(s.stable for s in [scl_oe, scl_o, sda_oe, sda_o]):
                    self.state = self.State.IDLE

            case self.State.WAIT_BIT_SCL_RISE:
                if (
                    scl_oe.stable_high
                    and scl_o.rising
                    and sda_oe.stable_high
                    and sda_o.stable
                ):
                    assert sda_o.value == 0 or sda_o.value == 1
                    self.bits.append(sda_o.value)
                    self.byte = (self.byte << 1) | sda_o.value
                    self.state = self.State.WAIT_BIT_SCL_FALL
                elif not scl_oe.stable_high or not sda_oe.stable_high:
                    self.state = self.State.IDLE
                    return self.Result.ERROR

            case self.State.WAIT_BIT_SCL_FALL:
                if (
                    scl_oe.stable_high
                    and scl_o.falling
                    and sda_oe.stable_high
                    and sda_o.stable
                ):
                    if len(self.bits) == 8:
                        self.state = self.State.WAIT_ACK_SCL_RISE
                        return self.Result.ACK_NACK
                    else:
                        self.state = self.State.WAIT_BIT_SCL_RISE
                elif (
                    scl_oe.stable_high
                    and scl_o.stable_high
                    and sda_oe.stable_high
                    and sda_o.rising
                ):
                    if self.bits == [0]:
                        self.state = self.State.IDLE
                        return self.Result.FISH
                    else:
                        self.state = self.State.IDLE
                        return self.Result.ERROR
                elif not all(s.stable for s in [scl_oe, scl_o, sda_oe, sda_o]):
                    self.state = self.State.IDLE
                    return self.Result.ERROR

            case self.State.WAIT_ACK_SCL_RISE:
                if sda_oe.falling:
                    pass
                elif scl_oe.stable_high and scl_o.rising and sda_oe.stable_low:
                    self.state = self.State.WAIT_ACK_SCL_FALL
                elif not all(s.stable for s in [scl_oe, scl_o, sda_oe, sda_o]):
                    self.state = self.State.IDLE
                    return self.Result.ERROR

            case self.State.WAIT_ACK_SCL_FALL:
                if scl_oe.stable_high and scl_o.falling:
                    self.state = self.State.WAIT_BIT_SCL_RISE
                    self.bits = []
                    self.byte = 0
                    return self.Result.RELEASE_SDA
                elif not all(s.stable for s in [scl_oe, scl_o]):
                    self.state = self.State.IDLE
                    return self.Result.ERROR

        return self.Result.PASS


class Connector:
    top: Top
    process_cb: Callable[[list[Base | DataBytes]], None]
    addr: int

    press_button: bool

    _pressing_button: bool
    _known_last_command: Optional[OLED.Command]
    _track_min: Level
    _tracked: dict[str, Any]

    def __init__(
        self,
        top: Top,
        process_cb: Callable[[list[Base | DataBytes]], None],
        *,
        addr: int = 0x3C,
    ):
        self.top = top
        self.process_cb = process_cb
        self.addr = addr

        self.press_button = False

        self._known_last_command = None
        self._pressing_button = False
        self._track_min = INFO
        self._tracked = {}

    def sim_process(self) -> sim.Generator:
        switch = self.top.sim_switch
        i2c = self.top.oled.i2c

        byte_receiver = ByteReceiver()
        bytes: Optional[list[int]] = None

        while True:
            if self.press_button:
                self.press_button = False
                self._pressing_button = True
                yield switch.eq(1)
            elif self._pressing_button:
                self._pressing_button = False
                yield switch.eq(0)

            self.track(INFO, "command", (yield self.top.o_last_cmd), OLED.Command)

            scl_o = self.track(DEBUG, "scl.o", (yield i2c.scl_o))
            scl_oe = self.track(DEBUG, "scl.oe", (yield i2c.scl_oe))
            sda_o = self.track(DEBUG, "sda.o", (yield i2c.sda_o))
            sda_oe = self.track(DEBUG, "sda.oe", (yield i2c.sda_oe))

            self.track(INFO, "result", (yield self.top.oled.o_result), OLED.Result)
            self.track(DEBUG, "remain", (yield self.top.oled.remain))
            self.track(DEBUG, "offset", (yield self.top.oled.offset))

            self.track(DEBUG, "offlens_rd.addr", (yield self.top.oled.offlens_rd.addr))
            self.track(DEBUG, "offlens_rd.data", (yield self.top.oled.offlens_rd.data))

            self.track(DEBUG, "rom_rd.addr", (yield self.top.oled.rom_rd.addr))
            self.track(DEBUG, "rom_rd.data", (yield self.top.oled.rom_rd.data))

            match byte_receiver.process(scl_o, scl_oe, sda_o, sda_oe):
                case ByteReceiver.Result.PASS:
                    pass

                case ByteReceiver.Result.ACK_NACK:
                    # we are being asked to ACK if appropriate
                    byte = byte_receiver.byte
                    if bytes is None:
                        # check if we're being addressed
                        addr, rw = byte >> 1, byte & 1
                        if addr == self.addr and rw == 0:
                            yield i2c.sda_i.eq(0)
                            bytes = []
                        elif addr == self.addr and rw == 1:
                            print("NYI: read")
                        else:
                            pass
                    else:
                        bytes.append(byte)
                        yield i2c.sda_i.eq(0)

                        Cmd.parse(bytes)

                case ByteReceiver.Result.RELEASE_SDA:
                    yield i2c.sda_i.eq(1)

                case ByteReceiver.Result.ERROR:
                    yield i2c.sda_i.eq(1)
                    print("got error, resetting with: ", bytes)
                    bytes = None

                case ByteReceiver.Result.FISH:
                    assert bytes
                    self.process_cb(Cmd.parse(bytes))
                    bytes = None

            self.track(DEBUG, "state", byte_receiver.state, ByteReceiver.State)

            yield

    def track(
        self,
        level: Level,
        name: str,
        value: Any,
        type: Optional[type] = None,
        *,
        show: bool = True,
    ) -> Value:
        orig = value
        if type:
            try:
                value = type(value)
            except ValueError:
                pass
        if isinstance(value, Enum):
            value = value.name
        stable = True
        if name not in self._tracked:
            self._tracked[name] = value
        elif self._tracked[name] != value:
            stable = False
            self._tracked[name] = value
            if show and level >= self._track_min:
                print(f"{name}: -> {value}")
        return Value(orig, stable)
