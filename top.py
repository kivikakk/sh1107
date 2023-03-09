from typing import Optional, Tuple, List

from amaranth import Module, Signal, ClockSignal, ResetSignal, C
from amaranth.build import Platform
from amaranth.asserts import Assert, Cover, Assume, Initial
from amaranth.sim import Simulator

from .main import NEElaboratable, SIM_CLOCK
from .minor import Button
from .i2c import I2C


class Top(NEElaboratable):
    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.i2c = i2c = I2C()

        if platform:
            self.led_busy = platform.request("led", 0)
            self.led_ack = platform.request("led", 1)
            self.button = platform.request("button")

        m.submodules.button = button = Button(switch=self.button)

        with m.If(i2c.i_stb):
            m.d.sync += i2c.i_stb.eq(0)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(button.o_up & i2c.fifo.w_rdy):
                    m.d.sync += i2c.i_addr.eq(0x3C)
                    m.d.sync += i2c.i_rw.eq(0)
                    m.d.sync += i2c.i_stb.eq(1)
                    m.d.sync += i2c.fifo.w_data.eq(0x00)
                    m.d.sync += i2c.fifo.w_en.eq(1)
                    m.next = "FIRST_DONE"
            with m.State("FIRST_DONE"):
                m.d.sync += i2c.i_stb.eq(0)
                m.d.sync += i2c.fifo.w_en.eq(0)
                # Wait until we need the next byte.
                m.next = "WAIT_SECOND"
            with m.State("WAIT_SECOND"):
                with m.If(i2c.fifo.w_rdy):
                    m.d.sync += i2c.fifo.w_data.eq(0xAF)
                    m.d.sync += i2c.fifo.w_en.eq(1)
                    m.next = "SECOND_DONE"
            with m.State("SECOND_DONE"):
                m.d.sync += i2c.fifo.w_en.eq(0)
                m.next = "IDLE"

        m.d.comb += self.led_busy.eq(i2c.o_busy)
        m.d.comb += self.led_ack.eq(i2c.o_ack)

        return m

    @classmethod
    @property
    def sim_args(cls):
        return [], {}

    def prep_sim(self, sim: Simulator) -> List[Signal]:
        def assert_state(name, index=None):
            assert (yield self.uartrx.fsm.state) == self.uartrx.fsm.encoding[name]
            if index is not None:
                assert (yield self.uartrx.index) == index

        def bench():
            assert (yield self.rx)
            yield self.rx.eq(0)
            yield
            yield from assert_state("START")
            yield
            yield from assert_state("ALIGN")
            yield
            yield from assert_state("ALIGN")

            d = C(0b10101100)

            for i in range(8):
                yield self.rx.eq(d[i])
                for _ in range(3):
                    yield
                    yield from assert_state("DATA", i)

            yield self.rx.eq(1)
            for _ in range(3):
                yield
                yield from assert_state("STOP")

            yield
            yield from assert_state("START")
            assert (yield self.uartrx.data == 0b00110101)
            assert (yield self.uartrx.out == 0b10101100)
            assert (yield self.ssa.digit == 0b1010)
            assert (yield self.ssb.digit == 0b1100)

        sim.add_clock(SIM_CLOCK)
        sim.add_sync_process(bench)

        return [
            self.rx,
            self.uartrx.fsm.state,
            self.uartrx.index,
            self.uartrx.out,
            self.uartrx.out_inv,
            self.ssa.digit,
            self.ssb.digit,
        ]

    @classmethod
    def formal(cls) -> Tuple[Module, List[Signal]]:
        m = Module()
        m.submodules.c = c = cls(
            uart_options={
                "parity": None,
                "data_bits": 5,
                "stop_bits": 1,
                "count": 1,
            }
        )

        sync_clk = ClockSignal("sync")
        sync_rst = ResetSignal("sync")

        past_clk = Signal()
        m.d.sync += past_clk.eq(sync_clk)

        m.d.comb += Assume(sync_clk == ~past_clk)
        m.d.comb += Assume(~sync_rst)

        m.d.comb += Cover(c.ssa.digit)
        m.d.comb += Cover(c.ssb.digit)

        past_inv = Signal()
        m.d.sync += past_inv.eq(c.ssa.inv)
        m.d.comb += Cover(~Initial() & ~past_inv & c.ssa.inv)

        m.d.comb += Assert(c.ssa.inv == c.ssb.inv)

        return m, [sync_clk, sync_rst, c.rx]
