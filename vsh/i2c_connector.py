import typing
from typing import Literal

from amaranth import Record, Signal
from amaranth.hdl.ast import Statement
from amaranth.lib.enum import IntEnum

from i2c import I2C
from .shared import LOW_STATES, SIGNALS, Value, track

__all__ = ["I2CConnector"]


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


Tick = typing.Generator[
    Signal | Record | Statement | None,
    bool | int,
    None | Literal["addressed", "error", "fish"] | int,
]


class I2CConnector:
    i2c: I2C
    addr: int

    byte_receiver: ByteReceiver
    addressed: bool

    def __init__(self, i2c: I2C, addr: int):
        self.i2c = i2c
        self.addr = addr

        self.byte_receiver = ByteReceiver()
        self.addressed = False

    # Made to be embedded in OLEDConnector.
    def sim_tick(self) -> Tick:
        scl_o = track(SIGNALS, "scl.o", (yield self.i2c.scl_o))
        scl_oe = track(SIGNALS, "scl.oe", (yield self.i2c.scl_oe))
        sda_o = track(SIGNALS, "sda.o", (yield self.i2c.sda_o))
        sda_oe = track(SIGNALS, "sda.oe", (yield self.i2c.sda_oe))

        result = self.byte_receiver.process(scl_o, scl_oe, sda_o, sda_oe)
        track(LOW_STATES, "state", self.byte_receiver.state, ByteReceiver.State)
        match result:
            case ByteReceiver.Result.PASS:
                pass

            case ByteReceiver.Result.ACK_NACK:
                # we are being asked to ACK if appropriate
                byte = self.byte_receiver.byte
                if not self.addressed:
                    # check if we're being addressed
                    addr, rw = byte >> 1, byte & 1
                    if addr == self.addr and rw == 0:
                        yield self.i2c.sda_i.eq(0)
                        self.addressed = True
                        return "addressed"
                    elif addr == self.addr and rw == 1:
                        print("NYI: read")
                    else:
                        pass
                else:
                    yield self.i2c.sda_i.eq(0)
                    return byte

            case ByteReceiver.Result.RELEASE_SDA:
                yield self.i2c.sda_i.eq(1)

            case ByteReceiver.Result.ERROR:
                yield self.i2c.sda_i.eq(1)
                print("got error, resetting")
                self.addressed = False
                return "error"

            case ByteReceiver.Result.FISH:
                if not self.addressed:
                    print("command parser fish while unaddressed")
                self.addressed = False
                return "fish"

    def reset(self):
        self.addressed = False
