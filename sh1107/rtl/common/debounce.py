from typing import Final, Optional

from amaranth import Elaboratable, Module
from amaranth.build import Platform
from amaranth.lib.wiring import In, Out

from ...base import Config, ConfigComponent
from .timer import Timer

__all__ = ["Debounce"]


class Debounce(ConfigComponent):
    DEFAULT_HOLD_TIME: Final[float] = 1e-2
    SIM_HOLD_TIME: Final[float] = 1e-4

    hold_time: float

    i: In(1)
    o: Out(1)

    def __init__(self, *, config: Config):
        super().__init__(config=config)
        self.hold_time = (
            self.SIM_HOLD_TIME if config.target.simulation else self.DEFAULT_HOLD_TIME
        )

    def elaborate(self, platform: Optional[Platform]) -> Elaboratable:
        m = Module()

        m.submodules.timer = timer = Timer(time=self.hold_time)

        m.d.comb += timer.i.eq(self.i != self.o)
        with m.If(timer.o):
            m.d.sync += self.o.eq(self.i)

        return m
