from typing import Tuple

from amaranth import ClockSignal, Module, ResetSignal, Signal, Value
from amaranth.asserts import Assert, Assume, Cover, Initial
from amaranth.hdl.ast import Fell, Past, Rose, Stable

from common import Hz
from i2c import I2C


def formal() -> Tuple[Module, list[Signal | Value]]:
    m = Module()
    m.submodules.dut = dut = I2C(speed=Hz(2_000_000), formal=True)

    sync_clk = ClockSignal("sync")
    sync_rst = ResetSignal("sync")

    # past_clk = Signal()
    # m.d.sync += past_clk.eq(sync_clk)

    # m.d.comb += Assume(sync_clk == ~past_clk)
    m.d.comb += Assume(sync_clk == ~Past(sync_clk))
    m.d.comb += Assume(~sync_rst)

    with m.If(Initial()):
        m.d.comb += Assume(~dut.bus.i_stb & ~dut.bus.i_in_fifo_w_en)

    with m.If(Fell(sync_clk)):
        m.d.comb += Assume(Stable(dut.bus.i_stb) & Stable(dut.bus.i_in_fifo_w_en))

    m.d.comb += Assume(dut.bus.i_stb == dut.bus.i_in_fifo_w_en)

    with m.If(dut.bus.i_stb):
        m.d.comb += Assume(dut.bus.i_in_fifo_w_data == 0x17A)

    m.d.comb += Assume(Rose(dut.bus.i_stb, 2) == Fell(dut.bus.i_stb))

    m.d.comb += Cover(Rose(dut.bus.i_stb) & Rose(dut.bus.i_in_fifo_w_en))
    m.d.comb += Cover(Fell(dut.bus.i_stb) & Fell(dut.bus.i_in_fifo_w_en))
    m.d.comb += Cover(~dut.scl_o)
    m.d.comb += Cover(~dut.sda_o)

    return m, [
        sync_clk,
        sync_rst,
        dut.bus.i_stb,
        dut.bus.i_in_fifo_w_en,
        dut.bus.i_in_fifo_w_data,
    ]
