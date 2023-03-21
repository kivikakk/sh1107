from typing import Optional

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform

from .debounce import Debounce
from .timer import Timer

__all__ = ["Button", "ButtonWithHold"]


class Button(Elaboratable):
    """
    A simple debounced button.

    o_down strobes when the button starts to be pressed.
    o_up strobes when the button has been released.
    """

    i_switch: Signal

    o_down: Signal
    o_up: Signal

    __registered: Signal
    _debounce: Debounce

    def __init__(self):
        self.__registered = Signal()
        self._debounce = Debounce()

        self.i_switch = Signal()

        self.o_down = Signal()
        self.o_up = Signal()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.debounce = self._debounce

        m.d.comb += self._debounce.i.eq(self.i_switch)
        m.d.sync += self.__registered.eq(self._debounce.o)

        m.d.comb += self.o_down.eq(~self.__registered & self._debounce.o)
        m.d.comb += self.o_up.eq(self.__registered & ~self._debounce.o)

        return m


class ButtonWithHold(Button):
    """
    Adds a configurable hold signal to Button.

    When o_up strobes, o_held will be high if the button was held for the
    configure hold time.
    """

    hold_time: float

    o_held: Signal

    def __init__(self, *, hold_time: float = 1.5):
        super().__init__()

        self.hold_time = hold_time

        self.o_held = Signal()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = super().elaborate(platform)

        m.submodules.timer = timer = Timer(time=self.hold_time)

        holding = Signal()
        with m.If(self.o_down):
            m.d.sync += holding.eq(1)
            m.d.sync += self.o_held.eq(0)
        with m.If(self.o_up):
            m.d.sync += holding.eq(0)

        m.d.comb += timer.i.eq(holding)
        with m.If(timer.o):
            m.d.sync += self.o_held.eq(1)

        return m
