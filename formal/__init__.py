from typing import Optional, Tuple

from amaranth import ClockSignal, Module, ResetSignal, Signal, Value
from amaranth.asserts import Assert, Assume, Cover, Initial
from amaranth.hdl.ast import ValueCastable

from common import Hz
from i2c import I2C, RW, Transfer


def past(
    m: Module, s: Signal, *, cycles: int = 2, stable1: Optional[ValueCastable] = None
) -> Signal:
    if isinstance(s, ClockSignal):
        name = "clk_past"
    else:
        name = f"{s.name}_past"

    curr = s
    for i in range(cycles):
        next = Signal.like(s, name=f"{name}_{i}")
        m.d.sync += next.eq(curr)

        if stable1 is not None and i == 0:
            with m.If(stable1):
                m.d.comb += Assume(curr == next)

        curr = next
    return curr


def formal() -> Tuple[Module, list[Signal | Value]]:
    m = Module()
    m.submodules.dut = dut = I2C(speed=Hz(2_000_000), formal=True)

    in_fifo = dut._in_fifo  # pyright: ignore[reportPrivateUsage]

    sync_clk = ClockSignal("sync")
    sync_rst = ResetSignal("sync")

    sync_clk_past = past(m, sync_clk, cycles=1)
    m.d.comb += Assume(sync_clk == ~sync_clk_past)

    cycle = Signal(range(1000))
    m.d.sync += cycle.eq(cycle + 1)
    pasts_valid = cycle > 1

    sync_clk_falling = sync_clk_past & ~sync_clk

    m.d.comb += Assume(~sync_rst)

    i_stb = dut.bus.i_stb
    i_stb_past = past(m, i_stb, stable1=sync_clk_falling)

    in_fifo_w_en = in_fifo.w_en
    past(m, in_fifo_w_en, stable1=sync_clk_falling)

    in_fifo_w_data = in_fifo.w_data
    past(m, in_fifo_w_data, stable1=sync_clk_falling)

    in_fifo_r_en = in_fifo.r_en
    in_fifo_r_en_past = past(m, in_fifo_r_en)

    in_fifo_r_data = in_fifo.r_data

    o_busy = dut.bus.o_busy
    o_busy_past = past(m, o_busy)

    byte_ix = dut.byte_ix

    scl_o = dut.scl_o
    scl_o_past = past(m, scl_o)

    sda_oe = dut.sda_oe
    sda_oe_past = past(m, sda_oe)

    sda_o = dut.sda_o
    sda_o_past = past(m, sda_o)

    # Start with no strobes high.
    with m.If(Initial()):
        m.d.comb += Assume(~i_stb & ~in_fifo_w_en)

    # Don't strobe when already busy. After strobe, we should either pop the
    # FIFO and start activity, or do neither.
    with m.If(i_stb):
        m.d.comb += Assume(~o_busy & ~in_fifo_r_en)
        m.d.sync += Assert(in_fifo_r_en == o_busy)

    m.d.comb += Assume(o_busy == dut.c.en)

    with m.If(dut.rw == RW.W):
        m.d.comb += Assert(sda_oe | (byte_ix == 7))

    # Cover strobing that both does and doesn't result in popping the FIFO.
    m.d.comb += Cover((i_stb_past & ~i_stb) & (~in_fifo_r_en_past & in_fifo_r_en))
    m.d.comb += Cover((i_stb_past & ~i_stb) & (~in_fifo_r_en_past & ~in_fifo_r_en))

    # Just make sure we see some activity.
    m.d.comb += Cover(scl_o_past & ~scl_o)
    m.d.comb += Cover(sda_o_past & ~sda_o)
    m.d.comb += Cover(o_busy)

    # Get some way into addressing the target.
    m.d.comb += Cover(byte_ix == 1)

    # START condition: SDA falls while SCL high
    start_cond = scl_o_past & scl_o & sda_o_past & ~sda_o
    m.d.comb += Cover(start_cond)
    m.d.comb += Assert(scl_o == dut.formal_scl)
    m.d.comb += Assert(start_cond == dut.formal_start)

    # SDA released to look for ACK
    # m.d.comb += Cover(sda_oe_past & ~sda_oe)

    # SDA retaken
    # m.d.comb += Cover(~sda_oe_past & sda_oe)

    # STOP condition: SDA rises while SCL high
    # m.d.comb += Cover(scl_o_past & scl_o & ~sda_o_past & sda_o)

    # SDA should be stable when SCL is high, unless START or STOP.
    with m.If(scl_o & pasts_valid):
        m.d.comb += Assert((sda_o_past == sda_o) | dut.formal_start | dut.formal_stop)

    # No repeated START for now.
    m.d.comb += Assume((in_fifo_w_data & 0x100) == 0)
    m.d.comb += Assume((in_fifo_r_data & 0x100) == 0)

    return m, [
        sync_clk,
        sync_rst,
        dut.bus.i_stb,
        dut.bus.i_in_fifo_w_en,
        dut.bus.i_in_fifo_w_data,
    ]
