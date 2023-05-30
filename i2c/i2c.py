from typing import Final, Optional, Self, cast

from amaranth import Elaboratable, Module, Record, Signal
from amaranth.build import Attrs, Platform
from amaranth.hdl.rec import DIR_FANIN, DIR_FANOUT
from amaranth.lib import data, enum
from amaranth.lib.fifo import SyncFIFO
from amaranth.lib.io import Pin
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform
from amaranth_boards.resources import (
    I2CResource,  # pyright: ignore[reportUnknownVariableType]
)

from common import Counter, Hz

__all__ = ["I2C", "I2CBus", "RW", "Transfer"]


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


class I2CBus(Record):
    def __init__(self):
        super().__init__(
            [
                ("i_in_fifo_w_data", 9, DIR_FANIN),
                ("i_in_fifo_w_en", 1, DIR_FANIN),
                ("i_out_fifo_r_en", 1, DIR_FANIN),
                ("i_stb", 1, DIR_FANIN),
                ("o_ack", 1, DIR_FANOUT),
                ("o_busy", 1, DIR_FANOUT),
                ("o_in_fifo_w_rdy", 1, DIR_FANOUT),
                ("o_in_fifo_r_rdy", 1, DIR_FANOUT),
                ("o_out_fifo_r_rdy", 1, DIR_FANOUT),
                ("o_out_fifo_r_data", 8, DIR_FANOUT),
            ]
        )
        self.fields["o_ack"].reset = 1


class I2C(Elaboratable):
    """
    I2C controller.

    FIFO is 9 bits wide and one word deep; to start, write in Cat(rw<1>,
    addr<7>, 1<1>) (the MSB is ignored here, though, since you need to start
    with an address), and strobe i_stb on the cycle after.

    Write: Feed data one byte at a time into the FIFO as it's emptied, with MSB
    low (i.e. Cat(data<8>, 0<1>)).  If o_ack goes low, there's been a NACK, and
    the driver will discard any next queued byte and return to idle eventually.
    Idle can be detected when o_busy goes low.  Similarly, any other error will
    cause a return to idle.  To issue a repeated start, instead write Cat(rw<1>,
    addr<7>, 1<1>).

    Read: Not yet implemented.
    """

    VALID_SPEEDS: Final[list[int]] = [
        100_000,
        400_000,
        1_000_000,
        2_000_000,  # for vsh
    ]
    DEFAULT_SPEED: Final[int] = 1_000_000

    class NextByte(enum.Enum):
        IDLE = 0
        WANTED = 1
        READY = 2

    speed: Hz

    _in_fifo: SyncFIFO
    _in_fifo_r_data: Transfer

    _out_fifo: SyncFIFO

    bus: I2CBus

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

        self._in_fifo = SyncFIFO(width=9, depth=1)
        self._in_fifo_r_data = Transfer(target=self._in_fifo.r_data)

        self._out_fifo = SyncFIFO(width=8, depth=1)

        self.bus = I2CBus()

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

        m.submodules.in_fifo = self._in_fifo
        m.submodules.out_fifo = self._out_fifo

        m.d.comb += [
            self._in_fifo.w_data.eq(self.bus.i_in_fifo_w_data),
            self._in_fifo.w_en.eq(self.bus.i_in_fifo_w_en),
            self.bus.o_in_fifo_w_rdy.eq(self._in_fifo.w_rdy),
            self.bus.o_in_fifo_r_rdy.eq(self._in_fifo.r_rdy),
            self._out_fifo.r_en.eq(self.bus.i_out_fifo_r_en),
            self.bus.o_out_fifo_r_rdy.eq(self._out_fifo.r_rdy),
            self.bus.o_out_fifo_r_data.eq(self._out_fifo.r_data),
        ]

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
                with m.If(self._in_fifo.r_rdy):
                    m.d.sync += [
                        self._in_fifo.r_en.eq(1),
                        self.byte.eq(self._in_fifo_r_data),
                        self.next_byte.eq(I2C.NextByte.READY),
                    ]
            with m.Case(I2C.NextByte.READY):
                m.d.sync += self._in_fifo.r_en.eq(0)

        with m.FSM():
            with m.State("IDLE"):
                m.d.sync += [
                    self.sda_oe.eq(1),
                    self.sda_o.eq(1),
                    self.scl_o.eq(1),
                ]

                with m.If(self.bus.i_stb):
                    m.d.sync += [
                        self.bus.o_busy.eq(1),
                        self.bus.o_ack.eq(1),
                        self.next_byte.eq(I2C.NextByte.IDLE),
                        self.sda_o.eq(0),
                        c.en.eq(1),
                        self._in_fifo.r_en.eq(1),
                        self.rw.eq(self._in_fifo_r_data.payload.start.rw),
                        self.byte.eq(self._in_fifo_r_data),
                        self.byte_ix.eq(0),
                    ]

                    m.next = "START: WAIT SCL"

            with m.State("START: WAIT SCL"):
                m.d.sync += self._in_fifo.r_en.eq(0)
                # SDA is low.
                with m.If(c.o_full):
                    m.next = "WRITE DATA BIT: SCL LOW"

            # This comes from "START: WAIT SCL" or "WRITE ACK BIT: SCL HIGH".
            with m.State("WRITE DATA BIT: SCL LOW"):
                with m.If(c.o_half):
                    # Set SDA in prep for SCL high. (MSB)
                    m.d.sync += self.sda_o.eq(
                        (self.byte.payload.data >> (7 - self.byte_ix)) & 0x1
                    )
                with m.Elif(c.o_full):
                    m.next = "WRITE DATA BIT: SCL HIGH"

            with m.State("WRITE DATA BIT: SCL HIGH"):
                with m.If(c.o_full):
                    with m.If(self.byte_ix == 7):
                        m.d.sync += self.next_byte.eq(I2C.NextByte.WANTED)
                        m.next = "WRITE ACK BIT: SCL LOW"
                        # Wait for next SCL^ before R/W.
                    with m.Else():
                        m.d.sync += self.byte_ix.eq(self.byte_ix + 1)
                        m.next = "WRITE DATA BIT: SCL LOW"
                        # Wait for next SCL^ before next data bit.

            with m.State("WRITE ACK BIT: SCL LOW"):
                with m.If(c.o_half):
                    # Let go of SDA.
                    m.d.sync += self.sda_oe.eq(0)
                with m.Elif(c.o_full):
                    m.next = "WRITE ACK BIT: SCL HIGH"

            with m.State("WRITE ACK BIT: SCL HIGH"):
                with m.If(c.o_half):
                    # Read ACK. SDA should be brought low by the addressee.
                    m.d.sync += [
                        self.bus.o_ack.eq(~self.sda_i),
                        self.sda_oe.eq(1),
                    ]
                    m.next = "COMMON ACK BIT: SCL HIGH"

            with m.State("READ DATA BIT: SCL LOW"):
                with m.If(c.o_full):
                    m.next = "READ DATA BIT: SCL HIGH"

            with m.State("READ DATA BIT: SCL HIGH"):
                with m.If(c.o_half):
                    with m.If(self.byte_ix == 7):
                        m.d.sync += [
                            self._out_fifo.w_data.eq(
                                self.byte.payload.data
                                | (self.sda_i << (7 - self.byte_ix))
                            ),
                            self._out_fifo.w_en.eq(1),
                        ]
                        m.next = "READ DATA BIT (LAST): SCL HIGH"

                    with m.Else():
                        m.d.sync += [
                            self.byte_ix.eq(self.byte_ix + 1),
                            self.byte.payload.data.eq(
                                self.byte.payload.data
                                | (self.sda_i << (7 - self.byte_ix))
                            ),
                        ]

                with m.If(c.o_full):
                    m.next = "READ DATA BIT: SCL LOW"

            with m.State("READ DATA BIT (LAST): SCL HIGH"):
                m.d.sync += self._out_fifo.w_en.eq(0)
                with m.If(c.o_full):
                    m.next = "READ ACK BIT: SCL LOW"

            with m.State("READ ACK BIT: SCL LOW"):
                with m.If(c.o_half):
                    # Take back SDA & set.
                    # If the next byte is more data, we want to read more, so bring SDA low.
                    m.d.sync += [
                        self.sda_oe.eq(1),
                        self.sda_o.eq(
                            ~(
                                (self.next_byte == I2C.NextByte.READY)
                                & (self.byte.kind == Transfer.Kind.DATA)
                            )
                        ),
                    ]
                with m.Elif(c.o_full):
                    m.next = "COMMON ACK BIT: SCL HIGH"

            with m.State("COMMON ACK BIT: SCL HIGH"):
                with m.If(c.o_full):
                    with m.If(self.next_byte == I2C.NextByte.READY):
                        with m.If(
                            self.bus.o_ack
                            & (self.byte.kind == Transfer.Kind.DATA)
                            & (self.rw == RW.W)
                        ):
                            m.d.sync += self.byte_ix.eq(0)
                            m.next = "WRITE DATA BIT: SCL LOW"
                        with m.Elif(
                            self.bus.o_ack
                            & (self.byte.kind == Transfer.Kind.DATA)
                            & (self.rw == RW.R)
                        ):
                            m.d.sync += [
                                self.next_byte.eq(I2C.NextByte.IDLE),
                                self.byte.payload.data.eq(0),
                                self.byte_ix.eq(0),
                                self.sda_oe.eq(0),
                            ]
                            m.next = "READ DATA BIT: SCL LOW"
                        with m.Elif(
                            self.bus.o_ack
                            & (self.byte.kind == Transfer.Kind.START)
                            & (self.rw == RW.W)
                        ):
                            m.d.sync += [
                                self.rw.eq(self.byte.payload.start.rw),
                                self.byte.eq(self.byte),
                                self.byte_ix.eq(0),
                            ]
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
                    m.next = "WRITE DATA BIT: SCL LOW"

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
                    m.d.sync += [
                        c.en.eq(0),
                        self.bus.o_busy.eq(0),
                        self.scl_o.eq(1),
                    ]
                    m.next = "IDLE"

        return m
