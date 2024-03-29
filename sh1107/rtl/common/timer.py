from amaranth import Elaboratable, Module
from amaranth.lib.wiring import Component, In, Out

from ...platform import Platform
from .counter import Counter

__all__ = ["Timer"]


class Timer(Component):
    """
    A timer.

    When the input is low, the timer is reset and the output is low.

    When the input is held high, the timer advances.  After the
    configured time elapses, the output is brought high.
    """

    _time: float

    i: Out(1)
    o: In(1)

    def __init__(self, *, time: float):
        super().__init__()
        self._time = time

    def elaborate(self, platform: Platform) -> Elaboratable:
        m = Module()

        m.submodules.c = c = Counter(time=self._time)
        m.d.comb += c.en.eq(self.i)

        with m.If(~self.i):
            m.d.sync += self.o.eq(0)

        with m.If(c.full):
            m.d.sync += self.o.eq(1)

        return m
