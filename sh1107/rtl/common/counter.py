from typing import Optional, cast

from amaranth import Elaboratable, Module, Signal
from amaranth.lib.wiring import Component, In, Out

from ...platform import Platform

__all__ = ["Counter"]


class Counter(Component):
    _time: Optional[float]
    _hz: Optional[int]

    en: Out(1)

    half: In(1)
    full: In(1)

    def __init__(
        self,
        *,
        time: Optional[float] = None,
        hz: Optional[int] = None,
    ):
        super().__init__()
        assert time or hz
        self._time = time
        self._hz = hz

    def elaborate(self, platform: Platform) -> Elaboratable:
        m = Module()

        freq = cast(int, platform.default_clk_frequency)
        if self._time:
            clk_counter_max = int(freq * self._time)
            assertion_msg = f"cannot count to {self._time}s with {freq}Hz clock"
        elif self._hz:
            clk_counter_max = int(freq // self._hz)
            assertion_msg = f"cannot clock at {self._hz}Hz with {freq}Hz clock"
        else:
            raise AssertionError

        clk_counter = Signal(range(clk_counter_max))

        half_clock_tgt = int(clk_counter_max // 2)
        full_clock_tgt = clk_counter_max - 1
        assert (
            0 <= half_clock_tgt < full_clock_tgt
        ), f"{assertion_msg}; !(0 <= {half_clock_tgt} < {full_clock_tgt})"

        m.d.comb += [
            self.half.eq(clk_counter == half_clock_tgt),
            self.full.eq(clk_counter == full_clock_tgt),
        ]

        with m.If(self.en & ~self.full):
            m.d.sync += clk_counter.eq(clk_counter + 1)
        with m.Else():
            m.d.sync += clk_counter.eq(0)

        return m
