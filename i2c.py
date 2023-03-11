from typing import Optional

from amaranth import Elaboratable, Signal, Module
from amaranth.build import Platform, Attrs
from amaranth.lib.fifo import SyncFIFO
from amaranth_boards.resources import I2CResource


class I2C(Elaboratable):
    i_addr: Signal
    i_rw: Signal
    i_stb: Signal

    fifo: SyncFIFO

    o_busy: Signal
    o_ack: Signal

    _sda: Signal
    _scl: Signal

    __clocking: Signal
    __clk_counter_max: int
    __clk_counter: Signal
    __byte: Signal
    __byte_ix: Signal

    def __init__(self):
        self.i_addr = Signal(7, reset=0x3C)
        self.i_rw = Signal()
        self.i_stb = Signal()

        self.fifo = SyncFIFO(width=8, depth=1)

        self.o_busy = Signal()
        self.o_ack = Signal()

        self._sda = Signal(reset=1)
        self._scl = Signal(reset=1)

        self.__clocking = Signal()
        self.__clk_counter_max = 4
        self.__clk_counter = Signal(range(self.__clk_counter_max))

        self.__byte = Signal(8)
        self.__byte_ix = Signal(range(7))

    def assign(self, res):
        self._scl = res.scl
        self._sda = res.sda

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

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
            self.assign(plat_i2c)

            self.__clk_counter_max = int(platform.default_clk_frequency // 200_000)
            self.__clk_counter = Signal(range(self.__clk_counter_max))

        m.d.comb += self._scl.oe.eq(1)

        with m.If(self.__clocking):
            with m.If(self.__clk_counter < self.__clk_counter_max - 1):
                m.d.sync += self.__clk_counter.eq(self.__clk_counter + 1)
            with m.Else():
                m.d.sync += self.__clk_counter.eq(0)
                m.d.sync += self._scl.o.eq(~self._scl.o)

        HALF_CLOCK = self.__clk_counter == int(self.__clk_counter_max // 2)
        FULL_CLOCK = self.__clk_counter == self.__clk_counter_max - 1

        with m.FSM():
            with m.State("IDLE"):
                m.d.sync += self._sda.oe.eq(1)
                m.d.sync += self._sda.o.eq(1)
                m.d.sync += self._scl.o.eq(1)

                with m.If(self.i_stb & self.fifo.r_rdy):
                    m.d.sync += self.o_busy.eq(1)
                    m.d.sync += self._sda.o.eq(0)
                    m.d.sync += self.__clk_counter.eq(0)
                    m.d.sync += self.__clocking.eq(1)

                    m.d.sync += self.__byte.eq((self.i_addr << 1) | self.i_rw)
                    m.d.sync += self.__byte_ix.eq(0)

                    m.next = "START"
                    # This edge: SDA goes low.

            with m.State("START"):
                with m.Elif(FULL_CLOCK):
                    m.next = "DATA"
                    # This edge: SCL goes low.

            with m.State("DATA"):
                with m.If(HALF_CLOCK):
                    # Next edge: SCL goes high -- send bit. (MSB)
                    m.d.sync += self._sda.o.eq(
                        (self.__byte >> (7 - self.__byte_ix)) & 0x1
                    )
                with m.Elif(FULL_CLOCK):
                    m.next = "DATA_L"

            with m.State("DATA_L"):
                with m.If(FULL_CLOCK):
                    with m.If(self.__byte_ix < 7):
                        m.d.sync += self.__byte_ix.eq(self.__byte_ix + 1)
                        m.next = "DATA"
                        # This edge: SCL goes low. Wait for next SCL^ before next data bit.
                    with m.Else():
                        m.next = "RW"
                        # This edge: SCL goes low. Wait for next SCL^ before R/W.

            with m.State("RW"):
                with m.If(HALF_CLOCK):
                    # Next edge: SCL goes high -- send R/W.
                    # W == 0, R == 1.
                    m.d.sync += self._sda.o.eq(0)
                with m.Elif(FULL_CLOCK):
                    m.next = "RW_L"

            with m.State("RW_L"):
                with m.If(FULL_CLOCK):
                    m.next = "ACK"
                    # This edge: SCL goes low.

            with m.State("ACK"):
                with m.If(HALF_CLOCK):
                    # Next edge: SCL goes high. Let go of SDA.
                    m.d.sync += self._sda.oe.eq(0)
                with m.Elif(FULL_CLOCK):
                    m.next = "ACK_L"

            with m.State("ACK_L"):
                with m.If(HALF_CLOCK):
                    # Next edge: SCL goes low -- read ACK.
                    # SDA should be brought low by the addressee.
                    m.d.sync += self.o_ack.eq(~self._sda.i)
                with m.Elif(FULL_CLOCK):
                    # This edge: SCL goes low.
                    m.next = "FIN"

            with m.State("FIN"):
                with m.If(HALF_CLOCK):
                    m.d.sync += self._sda.oe.eq(1)
                    m.d.sync += self._sda.o.eq(1)
                with m.Elif(FULL_CLOCK):
                    m.d.sync += self.o_busy.eq(0)
                    m.d.sync += self.__clocking.eq(0)
                    m.next = "IDLE"

        return m


__all__ = ["I2C"]
