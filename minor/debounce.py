from typing import Optional

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform

from ..main import SIM_CLOCK


class Debounce(Elaboratable):
    def __init__(self, *, secs=None, count=None):
        self.input = Signal()
        self.output = Signal()

        if count is None:
            self.secs = secs
            self.set_clks_per_sec(1//SIM_CLOCK)
        else:
            self.set_count(count)

    def set_clks_per_sec(self, clks_per_sec):
        self.set_count(int(clks_per_sec * self.secs))

    def set_count(self, count):
        self.count = count
        self.timer = Signal(range(self.count+1))

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        if platform:
            self.set_clks_per_sec(platform.default_clk_frequency)

        with m.If(self.input == self.output):
            m.d.sync += self.timer.eq(0)
        with m.Else():
            with m.If(self.timer == self.count):
                m.d.sync += self.output.eq(self.input)
                m.d.sync += self.timer.eq(0)
            with m.Else():
                m.d.sync += self.timer.eq(self.timer + 1)

        return m
