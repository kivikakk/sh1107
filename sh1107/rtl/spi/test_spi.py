from amaranth import C, Cat, Elaboratable, Module, Signal, Value
from amaranth.hdl import ValueCastable
from amaranth.lib.fifo import SyncFIFO
from amaranth.lib.wiring import Component, In, Out
from amaranth.sim import Tick

from ... import sim
from ...platform import Platform
from . import SPIFlashReader, SPIHardwareBus


# TODO(Ch): try using this + initted Memory in vsh instead of the whitebox, just
# to see how hard/easy it is.
class MockSPIFlashPeripheral(Component):
    _data: Value
    spi: In(SPIHardwareBus)

    def __init__(self, *, data: Value):
        super().__init__()

        self._data = data
        assert len(self._data) <= 32
        assert len(self._data) % 8 == 0

    def elaborate(self, platform: Platform) -> Elaboratable:
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
                        sr.eq(Cat(C(0, 32 - len(self._data)), self._data)),
                    ]
                    m.next = "READING"

            with m.State("READING"):
                m.d.comb += self.spi.cipo.eq(sr[-1])
                with m.If(~self.spi.cs):
                    m.next = "IDLE"

        return m


class TestSPIFlashReaderTop(Component):
    _data: Value
    _len: int

    stb: Out(1)
    _fifo_out: SyncFIFO
    busy: In(1)

    _spifr: SPIFlashReader
    _peripheral: MockSPIFlashPeripheral

    def __init__(self, *, data: ValueCastable):
        super().__init__()

        self._data = Value.cast(data)
        self._len = len(self._data) // 8

        self._fifo_out = SyncFIFO(width=8, depth=self._len)

        self._spifr = SPIFlashReader()
        self._peripheral = MockSPIFlashPeripheral(data=self._data)

    def elaborate(self, platform: Platform) -> Elaboratable:
        m = Module()

        m.submodules.fifo_out = self._fifo_out
        m.submodules.spifr = self._spifr
        m.submodules.peripheral = self._peripheral

        m.d.comb += [
            self._peripheral.spi.copi.eq(self._spifr.spi.copi),
            self._spifr.spi.cipo.eq(self._peripheral.spi.cipo),
            self._peripheral.spi.cs.eq(self._spifr.spi.cs),
            self._peripheral.spi.clk.eq(self._spifr.spi.clk),
        ]

        m.d.sync += [
            self._spifr.bus.stb.eq(0),
            self._fifo_out.w_en.eq(0),
        ]

        with m.FSM() as fsm:
            m.d.comb += self.busy.eq(~fsm.ongoing("IDLE"))

            with m.State("IDLE"):
                with m.If(self.stb):
                    m.d.sync += [
                        self._spifr.bus.addr.eq(0x00CAFE),
                        self._spifr.bus.len.eq(self._len),
                        self._spifr.bus.stb.eq(1),
                    ]
                    m.next = "STROBED SPIFR"

            with m.State("STROBED SPIFR"):
                m.next = "WAITING SPIFR"

            with m.State("WAITING SPIFR"):
                with m.If(self._spifr.bus.valid):
                    m.d.sync += [
                        self._fifo_out.w_data.eq(self._spifr.bus.data),
                        self._fifo_out.w_en.eq(1),
                    ]
                with m.Elif(~self._spifr.bus.busy):
                    m.next = "IDLE"

        return m


class TestSPIFlashReader(sim.TestCase):
    @sim.args(data=C(0x3C, 8))
    @sim.args(data=C(0x0101, 16))
    @sim.args(data=C(0x7EEF08, 24))
    @sim.args(data=C(0xBEEFFEED, 32))
    def test_sim_spifr(self, dut: TestSPIFlashReaderTop, data: Value) -> sim.Procedure:
        yield dut.stb.eq(1)
        yield Tick()
        yield dut.stb.eq(0)
        yield Tick()

        while (yield dut.busy):
            yield Tick()

        expected = []
        for i in reversed(range(len(data) // 8)):
            expected.append((yield data[i * 8 : (i + 1) * 8]))
        self.assertEqual((yield from sim.fifo_content(dut._fifo_out)), expected)
