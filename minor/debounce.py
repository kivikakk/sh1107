from typing import Optional

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform


class Debounce(Elaboratable):
    i: Signal
    o: Signal

    __clk_counter_max: int
    __clk_counter: Signal

    def __init__(self):
        self.i = Signal()
        self.o = Signal()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        if platform:
            self.__clk_counter_max = int(platform.default_clk_frequency * 1e-2)
            self.__clk_counter = Signal(range(self.__clk_counter_max))
        else:
            self.__clk_counter_max = 2
            self.__clk_counter = Signal(range(self.__clk_counter_max))

        FULL_CLOCK = self.__clk_counter == self.__clk_counter_max - 1

        with m.If(self.i == self.o):
            m.d.sync += self.__clk_counter.eq(0)
        with m.Elif(FULL_CLOCK):
            m.d.sync += self.o.eq(self.i)
            m.d.sync += self.__clk_counter.eq(0)
        with m.Else():
            m.d.sync += self.__clk_counter.eq(self.__clk_counter + 1)

        return m
