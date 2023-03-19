from typing import Optional, List, Final

from amaranth import Elaboratable, Signal, Module
from amaranth.lib.io import Pin
from amaranth.build import Platform, Attrs
from amaranth.lib.fifo import SyncFIFO
from amaranth_boards.resources import I2CResource

from .config import SIM_CLOCK


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

    _sda: Pin
    _scl: Pin

    _scl_o: Signal
    _scl_oe: Signal
    _sda_o: Signal
    _sda_oe: Signal
    _sda_i: Signal

    __clocking: Signal
    __clk_counter_max: int
    __clk_counter: Signal
    _byte: Signal
    _byte_ix: Signal

    def __init__(self, *, speed: Speed):
        self.speed = speed

        self.i_addr = Signal(7, reset=0x3C)
        self.i_rw = Signal()
        self.i_stb = Signal()

        self.fifo = SyncFIFO(width=8, depth=1)

        self.o_busy = Signal()
        self.o_ack = Signal(reset=1)

        self.assign(scl=Pin(1, "io"), sda=Pin(1, "io"))
        self._sda_i.reset = 1

        self.__clocking = Signal()
        self._byte = Signal(8)
        self._byte_ix = Signal(range(7))

    def assign(self, *, scl, sda):
        self._scl = scl
        self._sda = sda

        self._scl_o = scl.o
        self._scl_oe = scl.oe
        self._sda_o = sda.o
        self._sda_oe = sda.oe
        self._sda_i = sda.i

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.fifo = self.fifo

        if platform:
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
            self.assign(scl=plat_i2c.scl, sda=plat_i2c.sda)

        freq = platform.default_clk_frequency if platform else int(1 / SIM_CLOCK)
        self.__clk_counter_max = int(freq // (self.speed.hz * 2))
        self.__clk_counter = Signal(range(self.__clk_counter_max))

        m.d.comb += self._scl_oe.eq(1)

        with m.If(self.__clocking):
            with m.If(self.__clk_counter < self.__clk_counter_max - 1):
                m.d.sync += self.__clk_counter.eq(self.__clk_counter + 1)
            with m.Else():
                m.d.sync += self.__clk_counter.eq(0)
                m.d.sync += self._scl_o.eq(~self._scl_o)

        half_clock_tgt = int(self.__clk_counter_max // 2)
        full_clock_tgt = self.__clk_counter_max - 1
        assert (
            0 < half_clock_tgt < full_clock_tgt
        ), f"cannot clock at {self.speed}Hz with {freq}Hz clock; !(0 < {half_clock_tgt} < {full_clock_tgt})"
        HALF_CLOCK = self.__clk_counter == half_clock_tgt
        FULL_CLOCK = self.__clk_counter == full_clock_tgt

        with m.FSM():
            with m.State("IDLE"):
                m.d.sync += self._sda_oe.eq(1)
                m.d.sync += self._sda_o.eq(1)
                m.d.sync += self._scl_o.eq(1)

                with m.If(self.i_stb & self.fifo.r_rdy):
                    m.d.sync += self.o_busy.eq(1)
                    m.d.sync += self._sda_o.eq(0)
                    m.d.sync += self.__clk_counter.eq(0)
                    m.d.sync += self.__clocking.eq(1)

                    m.d.sync += self._byte.eq((self.i_addr << 1) | self.i_rw)
                    m.d.sync += self._byte_ix.eq(0)

                    m.next = "START"
                    # This edge: SDA goes low.

            with m.State("START"):
                with m.If(FULL_CLOCK):
                    m.next = "DATA"
                    # This edge: SCL goes low.

            # This comes from ACK_L.
            with m.State("DATA_OBTAIN"):
                m.d.sync += self._byte.eq(self.fifo.r_data)
                m.d.sync += self._byte_ix.eq(0)
                m.d.sync += self.fifo.r_en.eq(0)
                m.next = "DATA"

            with m.State("DATA"):
                with m.If(HALF_CLOCK):
                    # Next edge: SCL goes high -- send bit. (MSB)
                    m.d.sync += self._sda_o.eq(
                        (self._byte >> (7 - self._byte_ix)) & 0x1
                    )
                with m.Elif(FULL_CLOCK):
                    m.next = "DATA_L"

            with m.State("DATA_L"):
                with m.If(FULL_CLOCK):
                    with m.If(self._byte_ix < 7):
                        m.d.sync += self._byte_ix.eq(self._byte_ix + 1)
                        m.next = "DATA"
                        # This edge: SCL goes low. Wait for next SCL^ before next data bit.
                    with m.Else():
                        m.next = "ACK"
                        # This edge: SCL goes low. Wait for next SCL^ before R/W.

            with m.State("ACK"):
                with m.If(HALF_CLOCK):
                    # Next edge: SCL goes high. Let go of SDA.
                    m.d.sync += self._sda_oe.eq(0)
                with m.Elif(FULL_CLOCK):
                    m.next = "ACK_L"

            with m.State("ACK_L"):
                with m.If(HALF_CLOCK):
                    # Next edge: SCL goes low -- read ACK.
                    # SDA should be brought low by the addressee.
                    m.d.sync += self.o_ack.eq(~self._sda_i)
                    m.d.sync += self._sda_oe.eq(1)
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
                    m.d.sync += self._sda_o.eq(0)
                with m.Elif(FULL_CLOCK):
                    # This edge: SCL goes high.
                    m.next = "STOP"

            with m.State("STOP"):
                with m.If(HALF_CLOCK):
                    # Next edge: we'll stop clocking.  Bring SDA high.
                    m.d.sync += self._sda_o.eq(1)
                with m.Elif(FULL_CLOCK):
                    # This edge: stop clocking.  Ensure we keep SCL high.
                    m.d.sync += self.__clocking.eq(0)
                    m.d.sync += self.o_busy.eq(0)
                    m.d.sync += self._scl_o.eq(1)
                    m.next = "IDLE"

        return m


__all__ = ["I2C", "Speed"]
