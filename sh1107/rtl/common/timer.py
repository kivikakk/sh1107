from typing import Optional

from amaranth import Module
from amaranth.build import Platform
from amaranth.lib.wiring import Component, In, Out

from .counter import Counter

__all__ = ["Timer"]


class Timer(Component):
    """
    A timer.

    When the input is low, the timer is reset and the output is low.

    When the input is held high, the timer advances.  After the
    configured time elapses, the output is brought high.
    """

    time: float

    i: Out(1)
    o: In(1)

    def __init__(self, *, time: float):
        super().__init__()
        self.time = time

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.c = c = Counter(time=self.time)
        m.d.comb += c.en.eq(self.i)

        with m.If(~self.i):
            m.d.sync += self.o.eq(0)

        with m.If(c.full):
            m.d.sync += self.o.eq(1)

        return m
