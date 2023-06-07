from typing import Tuple

from amaranth import ClockSignal, Module, ResetSignal, Signal, Value
from amaranth.asserts import Assert, Assume, Cover, Initial

from common import Hz
from i2c import I2C


def past(m: Module, s: Signal) -> Signal:
    reg = Signal.like(s)
    m.d.sync += reg.eq(s)
    return reg


def formal() -> Tuple[Module, list[Signal | Value]]:
    m = Module()
    m.submodules.dut = dut = I2C(speed=Hz(2_000_000), formal=True)

    in_fifo = dut._in_fifo  # pyright: ignore[reportPrivateUsage]

    sync_clk = ClockSignal("sync")
    sync_rst = ResetSignal("sync")

    sync_clk_past = past(m, sync_clk)
    m.d.comb += Assume(sync_clk == ~sync_clk_past)

    m.d.comb += Assume(~sync_rst)

    i_stb = dut.bus.i_stb
    i_stb_past = past(m, i_stb)

    in_fifo_w_en = in_fifo.w_en
    in_fifo_w_en_past = past(m, in_fifo_w_en)

    in_fifo_w_data = in_fifo.w_data
    in_fifo_w_data_past = past(m, in_fifo_w_data)

    in_fifo_r_en = in_fifo.r_en
    in_fifo_r_en_past = past(m, in_fifo_r_en)

    o_busy = dut.bus.o_busy
    byte_ix = dut.byte_ix

    scl_o = dut.scl_o
    scl_o_past = past(m, scl_o)

    # sda_oe = dut.sda_oe
    # sda_oe_past = past(m, sda_oe)

    sda_o = dut.sda_o
    sda_o_past = past(m, sda_o)

    # Start with no strobes high.
    with m.If(Initial()):
        m.d.comb += Assume(~dut.bus.i_stb & ~dut.bus.i_in_fifo_w_en)

    # Stable inputs on falling clock.
    with m.If(sync_clk_past & ~sync_clk):
        m.d.comb += Assume(
            (i_stb_past == i_stb)
            & (in_fifo_w_en_past == in_fifo_w_en)
            & (in_fifo_w_data_past == in_fifo_w_data)
        )

    # Don't strobe when already busy, and assume the next_byte loop is idle.
    # After strobe, we should either pop the FIFO and start activity, or do
    # neither.
    with m.If(dut.bus.i_stb):
        m.d.comb += Assume(~o_busy & ~in_fifo_r_en)
        m.d.comb += Assume(dut.next_byte == I2C.NextByte.IDLE)
        m.d.sync += Assert(in_fifo_r_en == o_busy)

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
    m.d.comb += Cover(scl_o_past & scl_o & sda_o_past & ~sda_o)

    # SDA released to look for ACK
    # m.d.comb += Cover(sda_oe_past & ~sda_oe)

    # SDA retaken
    # m.d.comb += Cover(~sda_oe_past & sda_oe)

    # STOP condition: SDA rises while SCL high
    # m.d.comb += Cover(scl_o_past & scl_o & ~sda_o_past & sda_o)

    return m, [
        sync_clk,
        sync_rst,
        dut.bus.i_stb,
        dut.bus.i_in_fifo_w_en,
        dut.bus.i_in_fifo_w_data,
    ]
