from typing import Optional

from amaranth import Cat, Elaboratable, Module, Signal
from amaranth.build import Platform
from amaranth.lib.fifo import SyncFIFO

import sim
from .spi_flash_reader import SPIFlashReader


class TestSPIFlashPeripheral(Elaboratable):
    spi_copi: Signal
    spi_cipo: Signal
    spi_cs: Signal
    spi_clk: Signal

    def __init__(self):
        self.spi_copi = Signal()
        self.spi_cipo = Signal()
        self.spi_cs = Signal()
        self.spi_clk = Signal()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        sr = Signal(32)
        edges = Signal(range(33))
        addr = Signal(24)

        # XXX(Ch): when we all run at the same speed, we can't detect the rising
        # edge.
        clk_rising = self.spi_clk == 1

        srnext = Signal.like(sr)
        m.d.comb += srnext.eq(Cat(self.spi_copi, sr[:-1]))

        with m.If(self.spi_cs & clk_rising):
            m.d.sync += [
                sr.eq(srnext),
                edges.eq(edges + 1),
            ]
        with m.Else():
            m.d.sync += edges.eq(0)

        m.d.comb += self.spi_cipo.eq(0)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.spi_cs):
                    m.next = "SELECTED, POWERED DOWN"

            with m.State("SELECTED, POWERED DOWN"):
                with m.If((edges == 8) & (sr[:8] == 0xAB)):
                    m.next = "SELECTED, POWERING UP, NEEDS DESELECT"

            with m.State("SELECTED, POWERING UP, NEEDS DESELECT"):
                with m.If(~self.spi_cs):
                    m.next = "DESELECTED, POWERED UP"

            with m.State("DESELECTED, POWERED UP"):
                with m.If(self.spi_cs):
                    m.next = "SELECTED, POWERED UP"

            with m.State("SELECTED, POWERED UP"):
                with m.If((edges == 31) & (srnext[24:] == 0x03)):
                    m.d.sync += [
                        addr.eq(srnext[:24]),
                        sr.eq(0xBEEFFEED),
                    ]
                    m.next = "READING"

            with m.State("READING"):
                m.d.comb += self.spi_cipo.eq(sr[-1])
                with m.If(~self.spi_cs):
                    m.next = "IDLE"

        return m


class TestSPIFlashReaderTop(Elaboratable):
    i_stb: Signal
    o_fifo: SyncFIFO
    o_busy: Signal

    spifr: SPIFlashReader
    peripheral: TestSPIFlashPeripheral

    def __init__(self):
        self.i_stb = Signal()
        self.o_fifo = SyncFIFO(width=8, depth=4)
        self.o_busy = Signal()

        self.spifr = SPIFlashReader()
        self.peripheral = TestSPIFlashPeripheral()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.o_fifo = self.o_fifo
        m.submodules.spifr = self.spifr
        m.submodules.peripheral = self.peripheral

        m.d.comb += [
            self.peripheral.spi_copi.eq(self.spifr.spi_copi),
            self.spifr.spi_cipo.eq(self.peripheral.spi_cipo),
            self.peripheral.spi_cs.eq(self.spifr.spi_cs),
            self.peripheral.spi_clk.eq(self.spifr.spi_clk),
        ]

        m.d.sync += [
            self.spifr.i_stb.eq(0),
            self.o_fifo.w_en.eq(0),
        ]

        with m.FSM() as fsm:
            m.d.comb += self.o_busy.eq(~fsm.ongoing("IDLE"))

            with m.State("IDLE"):
                with m.If(self.i_stb):
                    m.d.sync += [
                        self.spifr.i_addr.eq(0x00CAFE),
                        self.spifr.i_len.eq(0x4),
                        self.spifr.i_stb.eq(1),
                    ]
                    m.next = "STROBED SPIFR"

            with m.State("STROBED SPIFR"):
                m.next = "WAITING SPIFR"

            with m.State("WAITING SPIFR"):
                with m.If(self.spifr.o_valid):
                    m.d.sync += [
                        self.o_fifo.w_data.eq(self.spifr.o_data),
                        self.o_fifo.w_en.eq(1),
                    ]
                with m.Elif(~self.spifr.o_busy):
                    m.next = "IDLE"

        return m


class TestSPIFlashReader(sim.TestCase):
    def test_sim_spifr(self, dut: TestSPIFlashReaderTop) -> sim.Procedure:
        yield dut.i_stb.eq(1)
        yield
        yield dut.i_stb.eq(0)
        yield

        while (yield dut.o_busy):
            yield

        self.assertEqual(
            (yield from sim.fifo_content(dut.o_fifo)), [0xBE, 0xEF, 0xFE, 0xED]
        )
