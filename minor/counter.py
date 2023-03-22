from typing import Optional, cast

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform

import sim

__all__ = ["Counter"]


class Counter(Elaboratable):
    time: Optional[float]
    hz: Optional[int]

    en: Signal

    o_half: Signal
    o_full: Signal

    def __init__(
        self,
        *,
        time: Optional[float] = None,
        hz: Optional[int] = None,
    ):
        assert time or hz
        self.time = time
        self.hz = hz

        self.en = Signal()

        self.o_half = Signal()
        self.o_full = Signal()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        freq = (
            cast(int, platform.default_clk_frequency)
            if platform
            else int(1 / sim.clock())
        )
        if self.time:
            clk_counter_max = int(freq * self.time)
            assertion_msg = f"cannot count to {self.time}s with {freq}Hz clock"
        elif self.hz:
            clk_counter_max = int(freq // self.hz)
            assertion_msg = f"cannot clock at {self.hz}Hz with {freq}Hz clock"
        else:
            raise AssertionError
        clk_counter = Signal(range(clk_counter_max))

        with m.If(self.en):
            with m.If(clk_counter < clk_counter_max - 1):
                m.d.sync += clk_counter.eq(clk_counter + 1)
            with m.Else():
                m.d.sync += clk_counter.eq(0)
        with m.Else():
            m.d.sync += clk_counter.eq(0)

        half_clock_tgt = int(clk_counter_max // 2)
        full_clock_tgt = clk_counter_max - 1
        assert (
            0 < half_clock_tgt < full_clock_tgt
        ), f"{assertion_msg}; !(0 < {half_clock_tgt} < {full_clock_tgt})"

        m.d.comb += self.o_half.eq(clk_counter == half_clock_tgt)
        m.d.comb += self.o_full.eq(clk_counter == full_clock_tgt)

        return m
