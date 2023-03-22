from typing import Final, Optional

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform

from .timer import Timer

__all__ = ["Debounce"]


class Debounce(Elaboratable):
    DEFAULT_HOLD_TIME: Final[float] = 1e-2
    SIM_HOLD_TIME: Final[float] = 1e-4

    hold_time: float

    i: Signal
    o: Signal

    def __init__(self, *, in_sim: bool = False):
        self.hold_time = self.SIM_HOLD_TIME if in_sim else self.DEFAULT_HOLD_TIME

        self.i = Signal()
        self.o = Signal()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.timer = timer = Timer(time=self.hold_time)

        m.d.comb += timer.i.eq(self.i != self.o)
        with m.If(timer.o):
            m.d.sync += self.o.eq(self.i)

        return m
