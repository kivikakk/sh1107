from typing import Optional

from amaranth import C, Cat, Elaboratable, Module, Signal, Value
from amaranth.build import Platform
from amaranth.hdl.ast import ValueCastable
from amaranth.lib.fifo import SyncFIFO
from amaranth.lib.wiring import Component, In, Out

from ... import sim
from ...base import Config
from . import SPIFlashReader, SPIHardwareBus


# TODO(Ch): try using this + initted Memory in vsh instead of the whitebox, just
# to see how hard/easy it is.
class MockSPIFlashPeripheral(Component):
    data: Value
    spi: In(SPIHardwareBus)

    def __init__(self, *, data: Value):
        super().__init__()

        self.data = data
        assert len(self.data) <= 32
        assert len(self.data) % 8 == 0

    def elaborate(self, platform: Optional[Platform]) -> Elaboratable:
        m = Module()

        sr = Signal(32)
        edges = Signal(range(33))
        addr = Signal(24)

        # XXX(Ch): when we all run at the same speed, we can't detect the rising
        # edge.
        clk_rising = self.spi.clk == 1

        srnext = Signal.like(sr)
        m.d.comb += srnext.eq(Cat(self.spi.copi, sr[:-1]))

        with m.If(self.spi.cs & clk_rising):
            m.d.sync += [
                sr.eq(srnext),
                edges.eq(edges + 1),
            ]
        with m.Else():
            m.d.sync += edges.eq(0)

        m.d.comb += self.spi.cipo.eq(0)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.spi.cs):
                    m.next = "SELECTED, POWERED DOWN"

            with m.State("SELECTED, POWERED DOWN"):
                with m.If((edges == 7) & (srnext[:8] == 0xAB)):
                    m.next = "SELECTED, POWERING UP, NEEDS DESELECT"

            with m.State("SELECTED, POWERING UP, NEEDS DESELECT"):
                with m.If(~self.spi.cs):
                    m.next = "DESELECTED, POWERED UP"

            with m.State("DESELECTED, POWERED UP"):
                with m.If(self.spi.cs):
                    m.next = "SELECTED, POWERED UP"

            with m.State("SELECTED, POWERED UP"):
                with m.If((edges == 31) & (srnext[24:] == 0x03)):
                    m.d.sync += [
                        addr.eq(srnext[:24]),
                        sr.eq(Cat(C(0, 32 - len(self.data)), self.data)),
                    ]
                    m.next = "READING"

            with m.State("READING"):
                m.d.comb += self.spi.cipo.eq(sr[-1])
                with m.If(~self.spi.cs):
                    m.next = "IDLE"

        return m


class TestSPIFlashReaderTop(Component):
    data: Value
    len: int

    stb: Out(1)
    out: SyncFIFO
    busy: In(1)

    spifr: SPIFlashReader
    peripheral: MockSPIFlashPeripheral

    def __init__(self, *, data: ValueCastable):
        self.data = Value.cast(data)
        self.len = len(self.data) // 8

        self.stb = Signal()
        self.fifo_out = SyncFIFO(width=8, depth=self.len)
        self.busy = Signal()

        self.spifr = SPIFlashReader(config=Config.test)
        self.peripheral = MockSPIFlashPeripheral(data=self.data)

    def elaborate(self, platform: Optional[Platform]) -> Elaboratable:
        m = Module()

        m.submodules.fifo_out = self.fifo_out
        m.submodules.spifr = self.spifr
        m.submodules.peripheral = self.peripheral

        m.d.comb += [
            self.peripheral.spi.copi.eq(self.spifr.spi.copi),
            self.spifr.spi.cipo.eq(self.peripheral.spi.cipo),
            self.peripheral.spi.cs.eq(self.spifr.spi.cs),
            self.peripheral.spi.clk.eq(self.spifr.spi.clk),
        ]

        m.d.sync += [
            self.spifr.bus.stb.eq(0),
            self.fifo_out.w_en.eq(0),
        ]

        with m.FSM() as fsm:
            m.d.comb += self.busy.eq(~fsm.ongoing("IDLE"))

            with m.State("IDLE"):
                with m.If(self.stb):
                    m.d.sync += [
                        self.spifr.bus.addr.eq(0x00CAFE),
                        self.spifr.bus.len.eq(self.len),
                        self.spifr.bus.stb.eq(1),
                    ]
                    m.next = "STROBED SPIFR"

            with m.State("STROBED SPIFR"):
                m.next = "WAITING SPIFR"

            with m.State("WAITING SPIFR"):
                with m.If(self.spifr.bus.valid):
                    m.d.sync += [
                        self.fifo_out.w_data.eq(self.spifr.bus.data),
                        self.fifo_out.w_en.eq(1),
                    ]
                with m.Elif(~self.spifr.bus.busy):
                    m.next = "IDLE"

        return m


class TestSPIFlashReader(sim.TestCase):
    @sim.args(data=C(0x3C, 8))
    @sim.args(data=C(0x0101, 16))
    @sim.args(data=C(0x7EEF08, 24))
    @sim.args(data=C(0xBEEFFEED, 32))
    def test_sim_spifr(self, dut: TestSPIFlashReaderTop) -> sim.Procedure:
        yield dut.stb.eq(1)
        yield
        yield dut.stb.eq(0)
        yield

        while (yield dut.busy):
            yield

        expected = []
        for i in reversed(range(len(dut.data) // 8)):
            expected.append((yield dut.data[i * 8 : (i + 1) * 8]))
        self.assertEqual((yield from sim.fifo_content(dut.fifo_out)), expected)
