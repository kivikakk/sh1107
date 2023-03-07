import contextlib
from typing import Optional

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform

from .debounce import Debounce


class Button(Elaboratable):
    DEBOUNCE_SECS = 1e-2

    def __init__(self, *, switch=Signal(), debounce_count=None):
        self.switch = switch

        self.registered = Signal()
        self.debounce = Debounce(secs=self.DEBOUNCE_SECS, count=debounce_count)

    def elaborate(self, _: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.debounce = self.debounce

        m.d.comb += self.debounce.input.eq(self.switch)

        m.d.sync += self.registered.eq(self.debounce.output)

        return m

    @contextlib.contextmanager
    def Down(self, m: Module):
        with m.If(~self.registered & self.debounce.output):
            yield

    @contextlib.contextmanager
    def Up(self, m: Module):
        with m.If(self.registered & ~self.debounce.output):
            yield
