from typing import Optional

from amaranth import Elaboratable, Signal, Module, C
from amaranth.build import Platform, Attrs
from amaranth_boards.resources import I2CResource


class I2C(Elaboratable):
    def __init__(self):
        self.i_stb = Signal()
        self.o_busy = Signal()
        self.o_ack = Signal()

        self._sda = Signal(reset=1)
        self._scl = Signal(reset=1)

        self.__clocking = Signal()
        self.__address_ix = Signal(range(7))

    def assign(self, res: I2CResource):
        self._scl = res.scl
        self._sda = res.sda

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        if platform:
            platform.add_resources([
                I2CResource(
                    0, scl="2", sda="1",
                    conn=("pmod", 0),
                    attrs=Attrs(
                        IO_STANDARD="SB_LVCMOS",
                        PULLUP=1,
                    ),
                ),
            ])
            plat_i2c = platform.request("i2c")
            self.assign(plat_i2c)

            clk_counter_max = int(platform.default_clk_frequency // 200_000)
        else:
            clk_counter_max = 4

        m.d.comb += self._scl.oe.eq(1)

        clk_counter = Signal(range(clk_counter_max))
        with m.If(self.__clocking):
            with m.If(clk_counter < clk_counter_max - 1):
                m.d.sync += clk_counter.eq(clk_counter + 1)
            with m.Else():
                m.d.sync += clk_counter.eq(0)
                m.d.sync += self._scl.o.eq(~self._scl.o)

        with m.FSM():
            with m.State('IDLE'):
                m.d.sync += self._sda.oe.eq(1)
                m.d.sync += self._sda.o.eq(1)
                m.d.sync += self._scl.o.eq(1)

                with m.If(self.i_stb):
                    m.d.sync += self.o_busy.eq(1)
                    m.d.sync += self._sda.o.eq(0)
                    m.d.sync += clk_counter.eq(0)
                    m.d.sync += self.__clocking.eq(1)
                    m.d.sync += self.__address_ix.eq(0)
                    m.next = 'START'
                    # This edge: SDA goes low.

            with m.State('START'):
                with m.If(clk_counter == clk_counter_max - 1):
                    m.next = 'ADDRESS'
                    # This edge: SCL goes low.

            with m.State('ADDRESS'):
                with m.If(clk_counter == clk_counter_max - 1):
                    m.next = 'ADDRESS_L'
                    # This edge: SCL goes high -- send address bit. (MSB)
                    m.d.sync += self._sda.o.eq((C(0x3c, 7)
                                               >> (6 - self.__address_ix))[0])

            with m.State('ADDRESS_L'):
                with m.If(clk_counter == clk_counter_max - 1):
                    with m.If(self.__address_ix == 6):
                        m.next = 'RW'
                        # This edge: SCL goes low. Wait for next SCL^ before R/W.
                    with m.Else():
                        m.d.sync += self.__address_ix.eq(self.__address_ix + 1)
                        m.next = 'ADDRESS'
                        # This edge: SCL goes low. Wait for next SCL^ before next address bit.

            with m.State('RW'):
                with m.If(clk_counter == clk_counter_max - 1):
                    m.next = 'RW_L'
                    # This edge: SCL goes high -- send R/W.
                    m.d.sync += self._sda.o.eq(1)

            with m.State('RW_L'):
                with m.If(clk_counter == clk_counter_max - 1):
                    m.next = 'ACK'
                    # This edge: SCL goes low. Wait for next SCL^ before reading ACK.
                    m.d.sync += self._sda.oe.eq(0)

            with m.State('ACK'):
                with m.If(clk_counter == clk_counter_max - 1):
                    m.next = 'ACK_L'
                    # This edge: SCL goes high -- read ACK.
                    m.d.sync += self.o_ack.eq(self._sda.i)

            with m.State('ACK_L'):
                with m.If(clk_counter == clk_counter_max - 1):
                    # This edge: SCL goes low.  XXX
                    m.d.sync += self._sda.oe.eq(1)
                    m.next = 'FIN'

            with m.State('FIN'):
                with m.If(clk_counter == clk_counter_max - 1):
                    m.d.sync += self.o_busy.eq(0)
                    m.d.sync += self._sda.o.eq(1)
                    m.d.sync += self.__clocking.eq(0)
                    m.next = 'IDLE'

        return m

    def refactored_wait(self):
        pass


__all__ = ["I2C"]
