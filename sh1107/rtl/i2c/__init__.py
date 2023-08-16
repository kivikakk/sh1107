from typing import Final, Optional, Self, cast

from amaranth import Module, Signal
from amaranth.build import Attrs, Platform
from amaranth.lib import data, enum
from amaranth.lib.fifo import SyncFIFO
from amaranth.lib.wiring import Component, In, Out, Signature
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform
from amaranth_boards.resources import I2CResource

from ..common import Counter, Hz

__all__ = ["I2C", "I2CFormal", "I2CBus", "RW", "Transfer"]


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


I2CBus = Signature(
    {
        "in_fifo_w_data": Out(9),
        "in_fifo_w_en": Out(1),
        "out_fifo_r_en": Out(1),
        "stb": Out(1),
        "ack": In(1, reset=1),
        "busy": In(1),
        "in_fifo_w_rdy": In(1),
        "in_fifo_r_rdy": In(1),
        "out_fifo_r_rdy": In(1),
        "out_fifo_r_data": In(8),
    }
)


I2CHardwareBus = Signature(
    {
        "scl_o": Out(1, reset=1),
        "scl_oe": Out(1, reset=1),
        "sda_o": Out(1, reset=1),
        "sda_oe": Out(1, reset=1),
        "sda_i": In(1, reset=1),
    }
)


class I2C(Component):
    """
    I2C controller.

    FIFO is 9 bits wide and one word deep; to start, write in Cat(rw<1>,
    addr<7>, 1<1>) and strobe stb.

    Write: Feed data one byte at a time into the FIFO as it's emptied, with MSB
    low (i.e. Cat(data<8>, 0<1>)).  If ack goes low, there's been a NACK, and
    the driver will discard any next queued byte and return to idle eventually.
    Idle can be detected when busy goes low.  Similarly, any other error will
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

    speed: Hz

    _in_fifo: SyncFIFO
    _in_fifo_r_data: Transfer

    _out_fifo: SyncFIFO

    c: Counter

    bus: In(I2CBus)
    hw_bus: Out(I2CHardwareBus)

    rw: Signal
    byte: Signal
    byte_ix: Signal

    formal_scl: Optional[Signal]
    formal_start: Optional[Signal]
    formal_repeated_start: Optional[Signal]
    formal_stop: Optional[Signal]

    def __init__(self, *, speed: Hz):
        super().__init__()

        assert speed.value in self.VALID_SPEEDS
        self.speed = speed

        self._in_fifo = SyncFIFO(width=9, depth=1)
        self._in_fifo_r_data = Transfer(target=self._in_fifo.r_data)

        self._out_fifo = SyncFIFO(width=8, depth=1)

        self.c = Counter(hz=speed.value * 2)

        self.rw = Signal(RW)
        self.byte = Signal(8)
        self.byte_ix = Signal(range(8))

        self.formal_scl = None
        self.formal_start = None
        self.formal_repeated_start = None
        self.formal_stop = None

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.in_fifo = self._in_fifo
        m.submodules.out_fifo = self._out_fifo

        m.d.comb += [
            self._in_fifo.w_data.eq(self.bus.in_fifo_w_data),
            self._in_fifo.w_en.eq(self.bus.in_fifo_w_en),
            self.bus.in_fifo_w_rdy.eq(self._in_fifo.w_rdy),
            self.bus.in_fifo_r_rdy.eq(self._in_fifo.r_rdy),
            self._out_fifo.r_en.eq(self.bus.out_fifo_r_en),
            self.bus.out_fifo_r_rdy.eq(self._out_fifo.r_rdy),
            self.bus.out_fifo_r_data.eq(self._out_fifo.r_data),
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
            m.d.comb += [
                plat_i2c.scl.o.eq(self.hw_bus.scl_o),
                plat_i2c.scl.oe.eq(self.hw_bus.scl_oe),
                plat_i2c.sda.o.eq(self.hw_bus.sda_o),
                plat_i2c.sda.oe.eq(self.hw_bus.sda_oe),
                self.hw_bus.sda_i.eq(plat_i2c.sda.i),
            ]

        m.d.comb += self.hw_bus.scl_oe.eq(1)
        # NOTE(Mia): we might need to keep scl_o=0 and toggle scl_oe instead for
        # clock stretching?

        m.submodules.c = c = self.c
        with m.If(c.full):
            m.d.sync += self.hw_bus.scl_o.eq(~self.hw_bus.scl_o)

        m.d.sync += self._in_fifo.r_en.eq(0)

        fh(m, self.formal_start, False)
        fh(m, self.formal_repeated_start, False)
        fh(m, self.formal_stop, False)

        with m.FSM():
            with m.State("IDLE"):
                m.d.sync += [
                    self.hw_bus.sda_oe.eq(1),
                    self.hw_bus.sda_o.eq(1),
                    self.hw_bus.scl_o.eq(1),
                ]

                with m.If(self.bus.stb & self._in_fifo.r_rdy):
                    m.d.sync += [
                        self.bus.busy.eq(1),
                        self.bus.ack.eq(1),
                        self.hw_bus.sda_o.eq(0),
                        c.en.eq(1),
                        self._in_fifo.r_en.eq(1),
                        self.rw.eq(self._in_fifo_r_data.payload.start.rw),
                        self.byte.eq(self._in_fifo_r_data.payload.data),
                        self.byte_ix.eq(0),
                    ]
                    fh(m, self.formal_start, True)

                    m.next = "START: WAIT SCL"

            with m.State("START: WAIT SCL"):
                # SDA is low.
                with m.If(c.full):
                    fh(m, self.formal_scl, False)
                    m.next = "WRITE DATA BIT: SCL LOW"

            # This comes from "START: WAIT SCL" or "WRITE ACK BIT: SCL HIGH".
            with m.State("WRITE DATA BIT: SCL LOW"):
                with m.If(c.half):
                    # Set SDA in prep for SCL high. (MSB)
                    m.d.sync += self.hw_bus.sda_o.eq(
                        (self.byte >> (7 - self.byte_ix)[:3]) & 0x1
                    )
                with m.Elif(c.full):
                    fh(m, self.formal_scl, True)
                    m.next = "WRITE DATA BIT: SCL HIGH"

            with m.State("WRITE DATA BIT: SCL HIGH"):
                with m.If(c.full):
                    fh(m, self.formal_scl, False)
                    with m.If(self.byte_ix == 7):
                        # Let go of SDA.
                        m.d.sync += self.hw_bus.sda_oe.eq(0)
                        m.next = "WRITE ACK BIT: SCL LOW"
                        # Wait for next SCL^ before R/W.
                    with m.Else():
                        m.d.sync += self.byte_ix.eq(self.byte_ix + 1)
                        m.next = "WRITE DATA BIT: SCL LOW"
                        # Wait for next SCL^ before next data bit.

            with m.State("WRITE ACK BIT: SCL LOW"):
                with m.If(c.full):
                    fh(m, self.formal_scl, True)
                    m.next = "WRITE ACK BIT: SCL HIGH"

            with m.State("WRITE ACK BIT: SCL HIGH"):
                with m.If(c.half):
                    # Read ACK. SDA should be brought low by the addressee.
                    # Don't take SDA back until end of the cycle, otherwise it
                    # looks like a STOP condition if sda_o was left high.
                    m.d.sync += self.bus.ack.eq(~self.hw_bus.sda_i)
                    m.next = "COMMON ACK BIT: SCL HIGH"

            with m.State("READ DATA BIT: SCL LOW"):
                with m.If(c.full):
                    fh(m, self.formal_scl, True)
                    m.next = "READ DATA BIT: SCL HIGH"

            with m.State("READ DATA BIT: SCL HIGH"):
                with m.If(c.half):
                    with m.If(self.byte_ix == 7):
                        m.d.sync += [
                            self._out_fifo.w_data.eq(
                                self.byte
                                | (self.hw_bus.sda_i << (7 - self.byte_ix)[:3])
                            ),
                            self._out_fifo.w_en.eq(1),
                        ]
                        m.next = "READ DATA BIT (LAST): SCL HIGH"

                    with m.Else():
                        m.d.sync += [
                            self.byte_ix.eq(self.byte_ix + 1),
                            self.byte.eq(
                                self.byte
                                | (self.hw_bus.sda_i << (7 - self.byte_ix)[:3])
                            ),
                        ]

                with m.If(c.full):
                    fh(m, self.formal_scl, False)
                    m.next = "READ DATA BIT: SCL LOW"

            with m.State("READ DATA BIT (LAST): SCL HIGH"):
                m.d.sync += self._out_fifo.w_en.eq(0)
                with m.If(c.full):
                    fh(m, self.formal_scl, False)
                    m.next = "READ ACK BIT: SCL LOW"

            with m.State("READ ACK BIT: SCL LOW"):
                with m.If(c.half):
                    # Take back SDA & set.
                    # If the next byte is more data, we want to read more, so bring SDA low.
                    m.d.sync += [
                        self.hw_bus.sda_oe.eq(1),
                        self.hw_bus.sda_o.eq(
                            ~(
                                (self._in_fifo.r_rdy)
                                & (self._in_fifo_r_data.kind == Transfer.Kind.DATA)
                            )
                        ),
                    ]
                with m.Elif(c.full):
                    fh(m, self.formal_scl, True)
                    m.next = "COMMON ACK BIT: SCL HIGH"

            with m.State("COMMON ACK BIT: SCL HIGH"):
                with m.If(c.full):
                    fh(m, self.formal_scl, False)
                    with m.If(self._in_fifo.r_rdy):
                        with m.If(
                            self.bus.ack
                            & (self._in_fifo_r_data.kind == Transfer.Kind.DATA)
                            & (self.rw == RW.W)
                        ):
                            m.d.sync += [
                                self.byte.eq(self._in_fifo_r_data.payload.data),
                                self.byte_ix.eq(0),
                                self._in_fifo.r_en.eq(1),
                                self.hw_bus.sda_oe.eq(1),
                                self.hw_bus.sda_o.eq(0),
                            ]
                            m.next = "WRITE DATA BIT: SCL LOW"
                        with m.Elif(
                            self.bus.ack
                            & (self._in_fifo_r_data.kind == Transfer.Kind.DATA)
                            & (self.rw == RW.R)
                        ):
                            m.d.sync += [
                                self.byte.eq(0),
                                self.byte_ix.eq(0),
                                self._in_fifo.r_en.eq(1),
                                self.hw_bus.sda_oe.eq(0),
                            ]
                            m.next = "READ DATA BIT: SCL LOW"
                        with m.Elif(
                            self.bus.ack
                            & (self._in_fifo_r_data.kind == Transfer.Kind.START)
                            & (self.rw == RW.W)
                        ):
                            m.d.sync += [
                                self.rw.eq(self._in_fifo_r_data.payload.start.rw),
                                self.byte.eq(self._in_fifo_r_data.payload.data),
                                self.byte_ix.eq(0),
                                self._in_fifo.r_en.eq(1),
                                self.hw_bus.sda_oe.eq(1),
                                self.hw_bus.sda_o.eq(0),
                            ]
                            m.next = "REP START: SCL LOW"
                        with m.Else():
                            # Consume anything that got queued before the NACK was realised.
                            # TODO: might need to do a few more times
                            m.d.sync += [
                                self._in_fifo.r_en.eq(1),
                                self.hw_bus.sda_oe.eq(1),
                            ]
                            m.next = "FIN: SCL LOW"
                    with m.Else():
                        m.d.sync += self.hw_bus.sda_oe.eq(1)
                        m.next = "FIN: SCL LOW"

            with m.State("REP START: SCL LOW"):
                with m.If(c.half):
                    # Bring SDA high so we can drop it during the SCL high
                    # period.
                    m.d.sync += self.hw_bus.sda_o.eq(1)
                with m.If(c.full):
                    fh(m, self.formal_scl, True)
                    m.next = "REP START: SCL HIGH"

            with m.State("REP START: SCL HIGH"):
                # SDA is high.
                with m.If(c.half):
                    # Bring SDA low mid SCL-high to repeat start.
                    fh(m, self.formal_repeated_start, True)
                    m.d.sync += self.hw_bus.sda_o.eq(0)
                with m.Elif(c.full):
                    fh(m, self.formal_scl, False)
                    m.next = "WRITE DATA BIT: SCL LOW"

            with m.State("FIN: SCL LOW"):
                with m.If(c.half):
                    # Bring SDA low during SCL low.
                    m.d.sync += self.hw_bus.sda_o.eq(0)
                with m.Elif(c.full):
                    fh(m, self.formal_scl, True)
                    m.next = "FIN: SCL HIGH"

            with m.State("FIN: SCL HIGH"):
                with m.If(c.half):
                    # Bring SDA high during SCL high to finish.
                    m.d.sync += self.hw_bus.sda_o.eq(1)
                    fh(m, self.formal_stop, True)
                with m.Elif(c.full):
                    # Turn off the clock to keep SCL high.
                    m.d.sync += [
                        c.en.eq(0),
                        self.bus.busy.eq(0),
                        self.hw_bus.scl_o.eq(1),
                    ]
                    m.next = "IDLE"

        return m


def fh(m: Module, s: Optional[Signal], high: bool):
    if s is not None:
        m.d.sync += s.eq(high)


class I2CFormal(I2C):
    formal_scl: Signal
    formal_start: Signal
    formal_repeated_start: Signal
    formal_stop: Signal

    def __init__(self, *, speed: Hz):
        super().__init__(speed=speed)
        self.formal_scl = Signal(reset=1, name="formal_scl")
        self.formal_start = Signal(name="formal_start")
        self.formal_repeated_start = Signal(name="formal_repeated_start")
        self.formal_stop = Signal(name="formal_stop")
