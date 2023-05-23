from typing import Tuple

from amaranth import ClockSignal, Module, ResetSignal, Signal, Value

# from amaranth.asserts import Assert, Cover, Assume, Initial
from amaranth.asserts import Assume, Cover

from common import Hz
from i2c import I2C


def formal() -> Tuple[Module, list[Signal | Value]]:
    # XXX(Ari): Next time we work on this, please note some changes I've made
    # to main.sby, specifically around the "techmap" call.
    # See https://github.com/amaranth-lang/amaranth/issues/526.
    m = Module()
    m.submodules.dut = dut = I2C(speed=Hz(100_000))

    sync_clk = ClockSignal("sync")
    sync_rst = ResetSignal("sync")

    past_clk = Signal()
    m.d.sync += past_clk.eq(sync_clk)

    m.d.comb += Assume(sync_clk == ~past_clk)
    m.d.comb += Assume(~sync_rst)

    m.d.comb += Cover(~dut.scl_o)

    # past_inv = Signal()
    # m.d.sync += past_inv.eq(dut.ssa.inv)
    # m.d.comb += Cover(~Initial() & ~past_inv & dut.ssa.inv)

    # m.d.comb += Assert(dut.ssa.inv == dut.ssb.inv)

    return m, [
        sync_clk,
        sync_rst,
        dut.i_stb,
        dut.rw,
        dut.i_fifo_w_data,
        dut.i_fifo_w_en,
    ]
