from typing import Optional, Final, cast

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform

from config import SIM_CLOCK


__all__ = ["Debounce"]


class Timer(Elaboratable):
    time: float

    i: Signal
    o: Signal

    def __init__(self, *, time: float):
        self.time = time

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        freq = (
            cast(int, platform.default_clk_frequency)
            if platform
            else int(1 / SIM_CLOCK)
        )
        max = int(freq * self.time)
        counter = Signal(range(max))

        FULL_COUNT = counter == max - 1

        with m.If(self.i):
            with m.If(FULL_COUNT):
                m.d.sync += self.o.eq(1)
            with m.Else():
                m.d.sync += counter.eq(counter + 1)
        with m.Else():
            m.d.sync += self.o.eq(0)
            m.d.sync += counter.eq(0)

        return m


class Debounce(Elaboratable):
    HOLD_TIME: Final[float] = 1e-2

    i: Signal
    o: Signal

    def __init__(self):
        self.i = Signal()
        self.o = Signal()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.timer = timer = Timer(time=self.HOLD_TIME)

        m.d.comb += timer.i.eq(self.i != self.o)
        with m.If(timer.o):
            m.d.sync += self.o.eq(self.i)

        return m
