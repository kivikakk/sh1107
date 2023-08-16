from typing import Final, Optional

from amaranth import Module, Signal
from amaranth.build import Platform
from amaranth.lib.wiring import In, Out

from ...base import Config, ConfigComponent
from .debounce import Debounce
from .timer import Timer

__all__ = ["Button", "ButtonWithHold"]


class Button(ConfigComponent):
    """
    A simple debounced button.

    down strobes when the button is registered as pressed down.
    up strobes when the button is registered as released.
    """

    i: Out(1)

    down: In(1)
    up: In(1)

    debounce: Debounce

    def __init__(self, *, config: Config):
        super().__init__(config=config)
        self.debounce = Debounce(config=config)

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.debounce = self.debounce

        registered = Signal()
        m.d.comb += self.debounce.i.eq(self.i)
        m.d.sync += registered.eq(self.debounce.o)

        m.d.comb += [
            self.down.eq(~registered & self.debounce.o),
            self.up.eq(registered & ~self.debounce.o),
        ]

        return m


class ButtonWithHold(Button):
    """
    Adds a configurable hold signal to Button.

    When up strobes, held will be high if the button was held for the
    configure hold time.
    """

    DEFAULT_HOLD_TIME: Final[float] = 1.5
    SIM_HOLD_TIME: Final[float] = 1e-2

    hold_time: float

    held: In(1)

    def __init__(self, *, hold_time: Optional[float] = None, config: Config):
        super().__init__(config=config)

        self.hold_time = hold_time or (
            self.SIM_HOLD_TIME if config.target.simulation else self.DEFAULT_HOLD_TIME
        )

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = super().elaborate(platform)

        m.submodules.timer = timer = Timer(time=self.hold_time)

        holding = Signal()
        with m.If(self.down):
            m.d.sync += [
                holding.eq(1),
                self.held.eq(0),
            ]
        with m.If(self.up):
            m.d.sync += holding.eq(0)

        m.d.comb += timer.i.eq(holding)
        with m.If(timer.o):
            m.d.sync += self.held.eq(1)

        return m
