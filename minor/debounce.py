from typing import Optional, Final

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform

from .timer import Timer

__all__ = ["Debounce"]


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
