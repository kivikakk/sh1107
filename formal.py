from typing import Tuple, List

from amaranth import Module, Signal, ClockSignal, ResetSignal
from amaranth.asserts import Assert, Cover, Assume, Initial

from .top import Top


def formal() -> Tuple[Module, List[Signal]]:
    m = Module()
    m.submodules.dut = dut = Top()

    sync_clk = ClockSignal("sync")
    sync_rst = ResetSignal("sync")

    past_clk = Signal()
    m.d.sync += past_clk.eq(sync_clk)

    m.d.comb += Assume(sync_clk == ~past_clk)
    m.d.comb += Assume(~sync_rst)

    m.d.comb += Cover(dut.ssa.digit)
    m.d.comb += Cover(dut.ssb.digit)

    past_inv = Signal()
    m.d.sync += past_inv.eq(dut.ssa.inv)
    m.d.comb += Cover(~Initial() & ~past_inv & dut.ssa.inv)

    m.d.comb += Assert(dut.ssa.inv == dut.ssb.inv)

    return m, [sync_clk, sync_rst, dut.rx]
