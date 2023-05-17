from typing import Final, Optional, Self, cast

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Attrs, Platform
from amaranth.lib import data, enum
from amaranth.lib.fifo import SyncFIFO
from amaranth.lib.io import Pin
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform
from amaranth_boards.resources import (
    I2CResource,  # pyright: ignore[reportUnknownVariableType]
)

from common import Counter, Hz

__all__ = ["I2C", "RW", "Transfer"]


class RW(enum.IntEnum, shape=1):
    W = 0
    R = 1


class Transfer(data.Struct):
    class Kind(enum.Enum, shape=1):
        DATA = 0
        START = 1

    @classmethod
    def C_start(cls, rw: RW, addr: int) -> Self:
        return cast(
            cls,
            cls.const(
                {
                    "kind": Transfer.Kind.START,
                    "payload": {"start": {"rw": rw, "addr": addr}},
                }
            ),
        )

    @classmethod
    def C_data(cls, data: int) -> Self:
        return cast(
            cls,
            cls.const({"kind": Transfer.Kind.DATA, "payload": {"data": data}}),
        )

    payload: data.UnionLayout(
        {
            "data": 8,
            "start": data.StructLayout(
                {
                    "rw": RW,
                    "addr": 7,
                }
            ),
        }
    )
    kind: Kind


class I2C(Elaboratable):
    """
    I2C controller.

    FIFO is 9 bits wide and one word deep; to start, write in Cat(rw<1>,
    addr<7>, 1<1>) (the MSB is ignored here, though, since you need to start
    with an address), and strobe i_stb on the cycle after.

    Write: Feed data one byte at a time into the FIFO as it's emptied, with MSB
    low (i.e. Cat(data<8>, 0<1>)).  If o_ack goes low, there's been a NACK, and
    the driver will discard the next queued byte and return to idle eventually.
    Idle can be detected when o_busy goes low.  Similarly, any other error will
    cause a return to idle.  To issue a repeated start, instead write Cat(rw<1>,
    addr<7>, 1<1>).

    Read: Not yet implemented.
    """

    VALID_SPEEDS: Final[list[int]] = [
        100_000,
        400_000,
        1_000_000,
        2_000_000,  # XXX: for vsh
    ]
    DEFAULT_SPEED: Final[int] = 1_000_000

    class NextByte(enum.Enum):
        IDLE = 0
        WANTED = 1
        R_EN_LATCHED = 2
        R_EN_UNLATCHED = 3
        READY = 4

    speed: Hz

    fifo: SyncFIFO
    fifo_r_data: Transfer
    i_stb: Signal

    o_busy: Signal
    o_ack: Signal

    sda: Pin
    scl: Pin

    scl_o: Signal
    scl_oe: Signal
    sda_o: Signal
    sda_oe: Signal
    sda_i: Signal

    rw: Signal
    byte: Transfer
    byte_ix: Signal

    next_byte: Signal

    def __init__(self, *, speed: Hz):
        assert speed.value in self.VALID_SPEEDS
        self.speed = speed

        self.fifo = SyncFIFO(width=9, depth=1)
        self.fifo_r_data = Transfer(target=self.fifo.r_data)
        self.i_stb = Signal()

        self.o_busy = Signal()
        self.o_ack = Signal(reset=1)

        self.assign(scl=Pin(1, "io", name="scl"), sda=Pin(1, "io", name="sda"))
        self.sda_i.reset = 1

        self.rw = Signal(RW)
        self.byte = Transfer()  # NextByte caches the whole FIFO word here.
        self.byte_ix = Signal(range(8))  # ... but we never write the whole thing out.

        self.next_byte = Signal(I2C.NextByte)

    def assign(self, *, scl: Pin, sda: Pin):
        self.scl = scl
        self.sda = sda

        self.scl_o = cast(Signal, scl.o)
        self.scl_oe = cast(Signal, scl.oe)
        self.sda_o = cast(Signal, sda.o)
        self.sda_oe = cast(Signal, sda.oe)
        self.sda_i = cast(Signal, sda.i)

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.fifo = self.fifo

        match platform:
            case ICEBreakerPlatform():
                platform.add_resources(
                    [
                        I2CResource(
                            0,
                            scl="2",
                            sda="1",
                            conn=("pmod", 0),
                            attrs=Attrs(IO_STANDARD="SB_LVCMOS", PULLUP=1),
                        ),
                    ]
                )
                plat_i2c = platform.request("i2c")
            case OrangeCrabR0_2_85FPlatform():
                platform.add_resources(
                    [
                        I2CResource(
                            0,
                            scl="scl",
                            sda="sda",
                            conn=("io", 0),
                            attrs=Attrs(IO_TYPE="LVCMOS33", PULLMODE="UP"),
                        )
                    ]
                )
                plat_i2c = platform.request("i2c")
            case _:
                plat_i2c = None

        if plat_i2c is not None:
            self.assign(scl=cast(Pin, plat_i2c.scl), sda=cast(Pin, plat_i2c.sda))

        m.d.comb += self.scl_oe.eq(1)
        # NOTE(Mia): we might need to keep scl_o=0 and toggle scl_oe instead for
        # clock stretching?

        m.submodules.c = c = Counter(hz=self.speed.value * 2)
        with m.If(c.o_full):
            m.d.sync += self.scl_o.eq(~self.scl_o)

        # TODO(Ch): what's the nicer way of doing this, i wonder?
        with m.Switch(self.next_byte):
            with m.Case(I2C.NextByte.IDLE):
                pass
            with m.Case(I2C.NextByte.WANTED):
                with m.If(self.fifo.r_rdy):
                    m.d.sync += self.fifo.r_en.eq(1)
                    m.d.sync += self.next_byte.eq(I2C.NextByte.R_EN_LATCHED)
            with m.Case(I2C.NextByte.R_EN_LATCHED):
                m.d.sync += self.fifo.r_en.eq(0)
                m.d.sync += self.next_byte.eq(I2C.NextByte.R_EN_UNLATCHED)
            with m.Case(I2C.NextByte.R_EN_UNLATCHED):
                m.d.sync += self.byte.eq(self.fifo_r_data)
                m.d.sync += self.next_byte.eq(I2C.NextByte.READY)

        with m.FSM():
            with m.State("IDLE"):
                m.d.sync += self.sda_oe.eq(1)
                m.d.sync += self.sda_o.eq(1)
                m.d.sync += self.scl_o.eq(1)

                with m.If(self.i_stb):
                    m.d.sync += self.o_busy.eq(1)
                    m.d.sync += self.o_ack.eq(1)
                    m.d.sync += self.next_byte.eq(I2C.NextByte.IDLE)
                    m.d.sync += self.sda_o.eq(0)
                    m.d.sync += c.en.eq(1)
                    m.d.sync += self.fifo.r_en.eq(1)

                    m.next = "START: LATCHED R_EN"

            with m.State("START: LATCHED R_EN"):
                m.d.sync += self.fifo.r_en.eq(0)
                m.next = "START: UNLATCHED R_EN"

            with m.State("START: UNLATCHED R_EN"):
                m.d.sync += self.rw.eq(self.fifo_r_data.payload.start.rw)
                m.d.sync += self.byte.eq(self.fifo_r_data)
                m.d.sync += self.byte_ix.eq(0)
                m.next = "START: WAIT SCL"

            with m.State("START: WAIT SCL"):
                # SDA is low.
                with m.If(c.o_full):
                    m.next = "DATA BIT: SCL LOW"

            # This comes from "START: WAIT SCL" or "ACK BIT: SCL HIGH".
            with m.State("DATA BIT: SCL LOW"):
                with m.If(c.o_half):
                    # Set SDA in prep for SCL high. (MSB)
                    m.d.sync += self.sda_o.eq((self.byte >> (7 - self.byte_ix)) & 0x1)
                with m.Elif(c.o_full):
                    m.next = "DATA BIT: SCL HIGH"

            with m.State("DATA BIT: SCL HIGH"):
                with m.If(c.o_full):
                    with m.If(self.byte_ix < 7):
                        m.d.sync += self.byte_ix.eq(self.byte_ix + 1)
                        m.next = "DATA BIT: SCL LOW"
                        # Wait for next SCL^ before next data bit.
                    with m.Else():
                        m.d.sync += self.next_byte.eq(I2C.NextByte.WANTED)
                        m.next = "ACK BIT: SCL LOW"
                        # Wait for next SCL^ before R/W.

            with m.State("ACK BIT: SCL LOW"):
                with m.If(c.o_half):
                    # Let go of SDA.
                    m.d.sync += self.sda_oe.eq(0)
                with m.Elif(c.o_full):
                    m.next = "ACK BIT: SCL HIGH"

            with m.State("ACK BIT: SCL HIGH"):
                with m.If(c.o_half):
                    # Read ACK. SDA should be brought low by the addressee.
                    m.d.sync += self.o_ack.eq(~self.sda_i)
                    m.d.sync += self.sda_oe.eq(1)
                with m.Elif(c.o_full):
                    with m.If(self.next_byte == I2C.NextByte.READY):
                        with m.If(self.o_ack & (self.byte.kind == Transfer.Kind.DATA)):
                            m.d.sync += self.byte_ix.eq(0)
                            m.next = "DATA BIT: SCL LOW"
                        with m.Elif(
                            self.o_ack & (self.byte.kind == Transfer.Kind.START)
                        ):
                            m.d.sync += self.rw.eq(self.byte.payload.start.rw)
                            m.d.sync += self.byte.eq(self.byte)
                            m.d.sync += self.byte_ix.eq(0)
                            m.next = "REP START: SCL LOW"
                        with m.Else():
                            # Consume anything that got queued before the NACK was realised.
                            m.d.sync += self.next_byte.eq(I2C.NextByte.WANTED)
                            m.next = "FIN: SCL LOW"
                    with m.Else():
                        m.next = "FIN: SCL LOW"

            with m.State("REP START: SCL LOW"):
                with m.If(c.o_half):
                    # Bring SDA high so we can drop it during the SCL high
                    # period.
                    m.d.sync += self.sda_o.eq(1)
                with m.If(c.o_full):
                    m.next = "REP START: SCL HIGH"

            with m.State("REP START: SCL HIGH"):
                # SDA is high.
                with m.If(c.o_half):
                    # Bring SDA low mid SCL-high to repeat start.
                    m.d.sync += self.sda_o.eq(0)
                with m.Elif(c.o_full):
                    m.next = "DATA BIT: SCL LOW"

            with m.State("FIN: SCL LOW"):
                with m.If(c.o_half):
                    # Bring SDA low during SCL low.
                    m.d.sync += self.sda_o.eq(0)
                with m.Elif(c.o_full):
                    m.next = "FIN: SCL HIGH"

            with m.State("FIN: SCL HIGH"):
                with m.If(c.o_half):
                    # Bring SDA high during SCL high to finish.
                    m.d.sync += self.sda_o.eq(1)
                with m.Elif(c.o_full):
                    # Turn off the clock to keep SCL high.
                    m.d.sync += c.en.eq(0)
                    m.d.sync += self.o_busy.eq(0)
                    m.d.sync += self.scl_o.eq(1)
                    m.next = "IDLE"

        return m
