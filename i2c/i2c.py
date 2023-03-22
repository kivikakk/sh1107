from typing import Final, List, Optional, cast

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Attrs, Platform
from amaranth.lib.fifo import SyncFIFO
from amaranth.lib.io import Pin
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform
from amaranth_boards.resources import (
    I2CResource,  # pyright: reportUnknownVariableType=false
)

import sim

__all__ = ["I2C", "Speed"]


class Speed:
    hz: int

    VALID_SPEEDS: Final[List[int]] = [
        100_000,
        400_000,
        1_000_000,
    ]

    def __init__(self, hz: int | str):
        hz = int(hz)
        assert hz in self.VALID_SPEEDS
        self.hz = hz

    def __repr__(self) -> str:
        return f"{self.hz}Hz"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Speed):
            return NotImplemented
        return self.hz == other.hz

    def __hash__(self) -> int:
        return hash(self.hz)


class I2C(Elaboratable):
    speed: Speed

    i_addr: Signal
    i_rw: Signal
    i_stb: Signal

    fifo: SyncFIFO

    o_busy: Signal
    o_ack: Signal

    sda: Pin
    scl: Pin

    scl_o: Signal
    scl_oe: Signal
    sda_o: Signal
    sda_oe: Signal
    sda_i: Signal

    __clocking: Signal
    __clk_counter_max: int
    __clk_counter: Signal
    byte: Signal
    byte_ix: Signal

    def __init__(self, *, speed: Speed):
        self.speed = speed

        self.i_addr = Signal(7, reset=0x3C)
        self.i_rw = Signal()
        self.i_stb = Signal()

        self.fifo = SyncFIFO(width=8, depth=1)

        self.o_busy = Signal()
        self.o_ack = Signal(reset=1)

        self.assign(scl=Pin(1, "io"), sda=Pin(1, "io"))
        self.sda_i.reset = 1

        self.__clocking = Signal()
        self.byte = Signal(8)
        self.byte_ix = Signal(range(7))

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

        freq = (
            cast(int, platform.default_clk_frequency)
            if platform
            else int(1 / sim.clock())
        )
        self.__clk_counter_max = int(freq // (self.speed.hz * 2))
        self.__clk_counter = Signal(range(self.__clk_counter_max))
        # TODO: Timer

        m.d.comb += self.scl_oe.eq(1)

        with m.If(self.__clocking):
            with m.If(self.__clk_counter < self.__clk_counter_max - 1):
                m.d.sync += self.__clk_counter.eq(self.__clk_counter + 1)
            with m.Else():
                m.d.sync += self.__clk_counter.eq(0)
                m.d.sync += self.scl_o.eq(~self.scl_o)

        half_clock_tgt = int(self.__clk_counter_max // 2)
        full_clock_tgt = self.__clk_counter_max - 1
        assert (
            0 < half_clock_tgt < full_clock_tgt
        ), f"cannot clock at {self.speed}Hz with {freq}Hz clock; !(0 < {half_clock_tgt} < {full_clock_tgt})"
        HALF_CLOCK = self.__clk_counter == half_clock_tgt
        FULL_CLOCK = self.__clk_counter == full_clock_tgt

        with m.FSM():
            with m.State("IDLE"):
                m.d.sync += self.sda_oe.eq(1)
                m.d.sync += self.sda_o.eq(1)
                m.d.sync += self.scl_o.eq(1)

                with m.If(self.i_stb & self.fifo.r_rdy):
                    m.d.sync += self.o_busy.eq(1)
                    m.d.sync += self.sda_o.eq(0)
                    m.d.sync += self.__clk_counter.eq(0)
                    m.d.sync += self.__clocking.eq(1)

                    m.d.sync += self.byte.eq((self.i_addr << 1) | self.i_rw)
                    m.d.sync += self.byte_ix.eq(0)

                    m.next = "START"
                    # This edge: SDA goes low.

            with m.State("START"):
                with m.If(FULL_CLOCK):
                    m.next = "DATA"
                    # This edge: SCL goes low.

            # This comes from ACK_L.
            with m.State("DATA_OBTAIN"):
                m.d.sync += self.byte.eq(self.fifo.r_data)
                m.d.sync += self.byte_ix.eq(0)
                m.d.sync += self.fifo.r_en.eq(0)
                m.next = "DATA"

            with m.State("DATA"):
                with m.If(HALF_CLOCK):
                    # Next edge: SCL goes high -- send bit. (MSB)
                    m.d.sync += self.sda_o.eq((self.byte >> (7 - self.byte_ix)) & 0x1)
                with m.Elif(FULL_CLOCK):
                    m.next = "DATA_L"

            with m.State("DATA_L"):
                with m.If(FULL_CLOCK):
                    with m.If(self.byte_ix < 7):
                        m.d.sync += self.byte_ix.eq(self.byte_ix + 1)
                        m.next = "DATA"
                        # This edge: SCL goes low. Wait for next SCL^ before next data bit.
                    with m.Else():
                        m.next = "ACK"
                        # This edge: SCL goes low. Wait for next SCL^ before R/W.

            with m.State("ACK"):
                with m.If(HALF_CLOCK):
                    # Next edge: SCL goes high. Let go of SDA.
                    m.d.sync += self.sda_oe.eq(0)
                with m.Elif(FULL_CLOCK):
                    m.next = "ACK_L"

            with m.State("ACK_L"):
                with m.If(HALF_CLOCK):
                    # Next edge: SCL goes low -- read ACK.
                    # SDA should be brought low by the addressee.
                    m.d.sync += self.o_ack.eq(~self.sda_i)
                    m.d.sync += self.sda_oe.eq(1)
                with m.Elif(FULL_CLOCK):
                    # This edge: SCL goes low.
                    with m.If(self.fifo.r_rdy):
                        m.d.sync += self.fifo.r_en.eq(1)
                        with m.If(self.o_ack):
                            m.next = "DATA_OBTAIN"
                        with m.Else():
                            m.next = "FIN_EMPTY"
                    with m.Else():
                        m.next = "FIN"

            with m.State("FIN_EMPTY"):
                m.d.sync += self.fifo.r_en.eq(0)
                m.next = "FIN"

            with m.State("FIN"):
                with m.If(HALF_CLOCK):
                    # Next edge: SCL goes high -- bring SDA low.
                    m.d.sync += self.sda_o.eq(0)
                with m.Elif(FULL_CLOCK):
                    # This edge: SCL goes high.
                    m.next = "STOP"

            with m.State("STOP"):
                with m.If(HALF_CLOCK):
                    # Next edge: we'll stop clocking.  Bring SDA high.
                    m.d.sync += self.sda_o.eq(1)
                with m.Elif(FULL_CLOCK):
                    # This edge: stop clocking.  Ensure we keep SCL high.
                    m.d.sync += self.__clocking.eq(0)
                    m.d.sync += self.o_busy.eq(0)
                    m.d.sync += self.scl_o.eq(1)
                    m.next = "IDLE"

        return m