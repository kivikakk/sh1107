from typing import Final, Optional

from amaranth import Elaboratable, Module
from amaranth.lib.wiring import Component, In, Out

from ...platform import Platform
from .timer import Timer

__all__ = ["Debounce"]


class Debounce(Component):
    DEFAULT_HOLD_TIME: Final[float] = 1e-2
    SIM_HOLD_TIME: Final[float] = 1e-4

    hold_time: float

    i: In(1)
    o: Out(1)

    def __init__(self, *, hold_time: Optional[float] = None):
        super().__init__()
        self.hold_time = hold_time or 0

    def elaborate(self, platform: Platform) -> Elaboratable:
        self.hold_time = self.hold_time or (
            self.SIM_HOLD_TIME if platform.simulation else self.DEFAULT_HOLD_TIME
        )

        m = Module()

        m.submodules.timer = timer = Timer(time=self.hold_time)

        m.d.comb += timer.i.eq(self.i != self.o)
        with m.If(timer.o):
            m.d.sync += self.o.eq(self.i)

        return m
