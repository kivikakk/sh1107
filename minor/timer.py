from typing import Optional, cast

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform

import sim

__all__ = ["Timer"]


class Timer(Elaboratable):
    """
    A timer.

    When the input is low, the timer is reset and the output is low.

    When the input is held high, the timer advances.  After the
    configured time elapses, the output is brought high.
    """

    time: float

    i: Signal
    o: Signal

    def __init__(self, *, time: float):
        self.time = time

        self.i = Signal()
        self.o = Signal()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        freq = (
            cast(int, platform.default_clk_frequency)
            if platform
            else int(1 // sim.clock())
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
