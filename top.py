import sys
from typing import Optional, Tuple, List

from amaranth import Elaboratable, Module, Signal, ClockSignal, ResetSignal, C
from amaranth.build import Platform, Resource, Subsignal, Pins, Attrs
from amaranth.asserts import Assert, Cover, Assume, Initial
from amaranth.sim import Simulator

from main import NEElaboratable, SIM_CLOCK
from .minor import Button


class Top(NEElaboratable):
    def __init__(self):
        pass

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        ctr = Signal(range(10240))

        if platform:
            platform.add_resources([
                Resource(
                    "i2c",
                    0,
                    Subsignal("sda", Pins("1", dir="io", conn=(
                        "pmod", 0)), Attrs(IO_STANDARD="SB_LVCMOS")),
                    Subsignal("scl", Pins("2", dir="o", conn=(
                        "pmod", 0)), Attrs(IO_STANDARD="SB_LVCMOS")),
                ),
            ])

            self.led1 = platform.request("led", 0)
            self.led2 = platform.request("led", 1)
            self.ssa_sig = platform.request("display_7seg", 0)
            self.ssb_sig = platform.request("display_7seg", 1)

            if True:
                connector = platform.connectors["pmod", 0]
                pmod_uart = UARTResource(
                    1, rx=connector.mapping["1"], tx=connector.mapping["2"])
                platform.add_resources([pmod_uart])

                uart_mac = platform.request("uart", 0)
                uart_win = platform.request("uart", 1)

                self.rx = uart_win.rx
                self.tx = uart_mac.tx

                sw_clr = platform.request("button", 0)
                sw_clr_b = Button(switch=sw_clr)
                m.submodules.sw_clr_b = sw_clr_b
                with sw_clr_b.Up(m):
                    m.d.sync += ctr.eq(0)

                rep = Signal(100)

                with m.FSM():
                    with m.State('A'):
                        with m.If(rep):
                            m.d.sync += [
                                rep.eq(0),
                                self.uart.tx_in.eq(ctr >> 8),
                                self.uart.tx_stb.eq(1),
                            ]
                            m.next = 'B'
                    with m.State('B'):
                        with m.If(rep == 99):
                            m.d.sync += rep.eq(0)
                            m.next = 'C'
                        with m.Else():
                            m.d.sync += rep.eq(rep+1)
                    with m.State('C'):
                        with m.If(~self.uart.tx_busy):
                            m.d.sync += [
                                self.uart.tx_in.eq(ctr),
                                self.uart.tx_stb.eq(1),
                            ]
                            m.next = 'A'

                sw_rep = platform.request("button", 1)
                sw_rep_b = Button(switch=sw_rep)
                m.submodules.sw_rep_b = sw_rep_b
                with sw_rep_b.Up(m):
                    m.d.sync += rep.eq(1)

                logic_analyzer_out_res = Resource(
                    "logic_analyzer_out",
                    0,
                    Subsignal("tx", Pins(
                        connector.mapping["3"], dir="o", assert_width=1)),
                    Subsignal("rx", Pins(
                        connector.mapping["4"], dir="o", assert_width=1)),
                )
                platform.add_resources([logic_analyzer_out_res])
                logic_analyzer_out = platform.request("logic_analyzer_out")
                m.d.comb += logic_analyzer_out.tx.eq(uart_mac.tx)
                m.d.comb += logic_analyzer_out.rx.eq(uart_win.rx)

            m.d.comb += self.led1.eq(self.rx)
            m.d.comb += self.led2.eq(self.tx)

        m.submodules.uart = self.uart
        m.d.comb += [
            self.uart.rx.eq(self.rx),
            self.tx.eq(self.uart.tx),
            self.ssa.inv.eq(self.uart.rx_inv),
            self.ssb.inv.eq(self.uart.rx_inv),
            self.ssa.digit.eq(self.uart.rx_out[4:]),
            self.ssb.digit.eq(self.uart.rx_out[:4]),
        ]

        m.submodules.ssa = self.ssa
        m.d.comb += self.ssa_sig.eq(self.ssa.segments)

        m.submodules.ssb = self.ssb
        m.d.comb += self.ssb_sig.eq(self.ssb.segments)

        with m.If(self.uart.rx_stb):
            m.d.sync += [
                ctr.eq(ctr + 1),
                self.uart.tx_in.eq(self.uart.rx_out),
                self.uart.tx_stb.eq(1),
            ]

        with m.If(self.uart.tx_ack):
            m.d.sync += [
                self.uart.tx_stb.eq(0),
            ]

        return m

    @classmethod
    @property
    def sim_args(cls):
        return [], {'uart_options': {
            'baud': (1 // SIM_CLOCK) // 2,
            'parity': None,
            'data_bits': 8,
            'stop_bits': 1,
        }}

    def prep_sim(self, sim: Simulator) -> List[Signal]:
        def assert_state(name, index=None):
            assert (yield self.uartrx.fsm.state) == self.uartrx.fsm.encoding[name]
            if index is not None:
                assert (yield self.uartrx.index) == index

        def bench():
            assert (yield self.rx)
            yield self.rx.eq(0)
            yield
            yield from assert_state('START')
            yield
            yield from assert_state('ALIGN')
            yield
            yield from assert_state('ALIGN')

            d = C(0b10101100)

            for i in range(8):
                yield self.rx.eq(d[i])
                for _ in range(3):
                    yield
                    yield from assert_state('DATA', i)

            yield self.rx.eq(1)
            for _ in range(3):
                yield
                yield from assert_state('STOP')

            yield
            yield from assert_state('START')
            assert (yield self.uartrx.data == 0b00110101)
            assert (yield self.uartrx.out == 0b10101100)
            assert (yield self.ssa.digit == 0b1010)
            assert (yield self.ssb.digit == 0b1100)

        sim.add_clock(SIM_CLOCK)
        sim.add_sync_process(bench)

        return [self.rx,
                self.uartrx.fsm.state,
                self.uartrx.index,
                self.uartrx.out,
                self.uartrx.out_inv,
                self.ssa.digit,
                self.ssb.digit]

    @classmethod
    def formal(cls) -> Tuple[Module, List[Signal]]:
        m = Module()
        m.submodules.c = c = cls(uart_options={
            'parity': None,
            'data_bits': 5,
            'stop_bits': 1,
            'count': 1,
        })

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
