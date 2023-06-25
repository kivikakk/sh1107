from typing import Final, Optional

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform

from .debounce import Debounce
from .timer import Timer

__all__ = ["Button", "ButtonWithHold"]


class Button(Elaboratable):
    """
    A simple debounced button.

    o_down strobes when the button is registered as pressed down.
    o_up strobes when the button is registered as released.
    """

    i: Signal

    o_down: Signal
    o_up: Signal

    debounce: Debounce
    __registered: Signal

    def __init__(self, *, in_sim: bool = False):
        self.debounce = Debounce(in_sim=in_sim)
        self.__registered = Signal()

        self.i = Signal()

        self.o_down = Signal()
        self.o_up = Signal()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.debounce = self.debounce

        m.d.comb += self.debounce.i.eq(self.i)
        m.d.sync += self.__registered.eq(self.debounce.o)

        m.d.comb += [
            self.o_down.eq(~self.__registered & self.debounce.o),
            self.o_up.eq(self.__registered & ~self.debounce.o),
        ]

        return m


class ButtonWithHold(Button):
    """
    Adds a configurable hold signal to Button.

    When o_up strobes, o_held will be high if the button was held for the
    configure hold time.
    """

    DEFAULT_HOLD_TIME: Final[float] = 1.5
    SIM_HOLD_TIME: Final[float] = 1e-2

    hold_time: float

    o_held: Signal

    def __init__(self, *, hold_time: Optional[float] = None, in_sim: bool = False):
        super().__init__(in_sim=in_sim)

        self.hold_time = hold_time or (
            self.SIM_HOLD_TIME if in_sim else self.DEFAULT_HOLD_TIME
        )

        self.o_held = Signal()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = super().elaborate(platform)

        m.submodules.timer = timer = Timer(time=self.hold_time)

        holding = Signal()
        with m.If(self.o_down):
            m.d.sync += [
                holding.eq(1),
                self.o_held.eq(0),
            ]
        with m.If(self.o_up):
            m.d.sync += holding.eq(0)

        m.d.comb += timer.i.eq(holding)
        with m.If(timer.o):
            m.d.sync += self.o_held.eq(1)

        return m
