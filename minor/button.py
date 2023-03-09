from typing import Optional, Final

from amaranth import Elaboratable, Module, Signal, Value
from amaranth.build import Platform

from .debounce import Debounce


class Button(Elaboratable):
    DEBOUNCE_SECS: Final[float] = 1e-2

    __switch: Signal
    __registered: Signal
    __debounce: Debounce

    o_down: Value
    o_up: Value

    def __init__(self, *, switch: Signal = Signal(), debounce_count: int = 0):
        self.__switch = switch

        self.__registered = Signal()
        self.__debounce = Debounce(secs=self.DEBOUNCE_SECS, count=debounce_count)

        self.o_down = ~self.__registered & self.__debounce.output
        self.o_up = self.__registered & ~self.__debounce.output

    def elaborate(self, _: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.debounce = self.__debounce

        m.d.comb += self.__debounce.input.eq(self.__switch)

        m.d.sync += self.__registered.eq(self.__debounce.output)

        return m
