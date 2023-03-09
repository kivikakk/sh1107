from typing import Optional

from amaranth import Elaboratable, Signal, Module
from amaranth.build import Platform, Attrs, Resource, Subsignal, Pins
from amaranth_boards.resources import I2CResource


class I2C(Elaboratable):
    def __init__(self):
        self.scl = Signal()

        self._sda = Signal()
        self._scl = Signal()

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
                    attrs=Attrs(IO_STANDARD="SB_LVCMOS"),
                ),
            ])
            plat_i2c = platform.request("i2c")
            self.assign(plat_i2c)

            clk_counter_max = int(platform.default_clk_frequency // 200_000)
        else:
            clk_counter_max = 4

        m.d.comb += self._scl.oe.eq(1)

        clk_counter = Signal(range(clk_counter_max))
        with m.If(clk_counter == clk_counter_max - 1):
            m.d.sync += self._scl.o.eq(~self._scl.o)
            m.d.sync += clk_counter.eq(0)
        with m.Else():
            m.d.sync += clk_counter.eq(clk_counter + 1)

        m.d.sync += self._sda.o.eq(0)

        m.d.comb += self.scl.eq(self._scl.o)

        return m


__all__ = ["I2C"]
