from typing import Optional

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform

from .debounce import Debounce


class Button(Elaboratable):
    i_switch: Signal

    o_down: Signal
    o_up: Signal

    __registered: Signal
    __debounce: Debounce

    def __init__(self):
        self.__registered = Signal()
        self.__debounce = Debounce()

        self.i_switch = Signal()

        self.o_down = Signal()
        self.o_up = Signal()

    def elaborate(self, _: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.debounce = self.__debounce

        m.d.comb += self.__debounce.i.eq(self.i_switch)
        m.d.sync += self.__registered.eq(self.__debounce.o)

        m.d.comb += self.o_down.eq(~self.__registered & self.__debounce.o)
        m.d.comb += self.o_up.eq(self.__registered & ~self.__debounce.o)

        return m
