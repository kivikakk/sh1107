from typing import Optional, Final

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform

from sim.config import SIM_CLOCK


class Debounce(Elaboratable):
    HOLD_TIME: Final[float] = 1e-2

    i: Signal
    o: Signal

    __clk_counter_max: int
    __clk_counter: Signal

    def __init__(self):
        self.i = Signal()
        self.o = Signal()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        freq = platform.default_clk_frequency if platform else int(1 / SIM_CLOCK)
        self.__clk_counter_max = int(freq * self.HOLD_TIME)
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
