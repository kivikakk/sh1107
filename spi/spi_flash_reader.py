import math
from typing import Optional, cast

from amaranth import C, Cat, ClockSignal, Elaboratable, Module, Record, Signal
from amaranth.build import Platform
from amaranth.hdl.rec import DIR_FANIN, DIR_FANOUT
from amaranth_boards.icebreaker import ICEBreakerPlatform

import sim

__all__ = ["SPIFlashReaderBus", "SPIFlashReader"]


class SPIFlashReaderBus(Record):
    addr: Signal
    len: Signal
    stb: Signal
    busy: Signal
    data: Signal
    valid: Signal

    def __init__(self):
        super().__init__(
            [
                ("addr", 24, DIR_FANIN),
                ("len", 16, DIR_FANIN),
                ("stb", 1, DIR_FANIN),
                ("busy", 1, DIR_FANOUT),
                ("data", 8, DIR_FANOUT),
                ("valid", 1, DIR_FANOUT),
            ]
        )


class SPIFlashReader(Elaboratable):
    spi_copi: Signal
    spi_cipo: Signal
    spi_cs: Signal
    spi_clk: Signal

    bus: SPIFlashReaderBus

    def __init__(self):
        self.spi_copi = Signal()
        self.spi_cipo = Signal()
        self.spi_cs = Signal()
        self.spi_clk = Signal()

        self.bus = SPIFlashReaderBus()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        clk = ClockSignal()

        match platform:
            case ICEBreakerPlatform():
                spi = platform.request("spi_flash_1x")
                self.spi_copi = spi.copi.o
                self.spi_cipo = spi.cipo.i
                self.spi_cs = spi.cs.o
                self.spi_clk = spi.clk.o
            case _:
                pass

        freq = (
            cast(int, platform.default_clk_frequency)
            if platform
            else int(1 / sim.clock())
        )
        # tRES1 (/CS High to Standby Mode without ID Read) and tDP (/CS High to
        # Power-down Mode) are both max 3us.
        TRES1_TDP_CYCLES = math.floor(freq / 1_000_000 * 3) + 1

        sr = Signal(32)
        snd_bitcount = Signal(range(max(32, TRES1_TDP_CYCLES)))

        rcv_bitcount = Signal(range(8))
        rcv_bytecount = Signal.like(self.bus.len)

        m.d.comb += [
            self.spi_copi.eq(sr[-1]),
            self.spi_clk.eq(self.spi_cs & ~clk),
            self.bus.data.eq(sr[:8]),
        ]

        m.d.sync += self.bus.valid.eq(0)

        with m.FSM() as fsm:
            m.d.comb += self.bus.busy.eq(~fsm.ongoing("IDLE"))

            with m.State("IDLE"):
                with m.If(self.bus.stb):
                    m.d.sync += [
                        self.spi_cs.eq(1),
                        sr.eq(0xAB000000),
                        snd_bitcount.eq(31),
                    ]
                    m.next = "POWER-DOWN RELEASE"

            with m.State("POWER-DOWN RELEASE"):
                m.d.sync += [
                    snd_bitcount.eq(snd_bitcount - 1),
                    sr.eq(Cat(C(0b1, 1), sr[:-1])),
                ]
                with m.If(snd_bitcount == 0):
                    m.d.sync += [
                        self.spi_cs.eq(0),
                        snd_bitcount.eq(TRES1_TDP_CYCLES - 1),
                    ]
                    m.next = "WAIT TRES1"

            with m.State("WAIT TRES1"):
                with m.If(snd_bitcount != 0):
                    m.d.sync += snd_bitcount.eq(snd_bitcount - 1)
                with m.Else():
                    m.d.sync += [
                        self.spi_cs.eq(1),
                        sr.eq(Cat(self.bus.addr, C(0x03, 8))),
                        snd_bitcount.eq(31),
                        rcv_bitcount.eq(7),
                        rcv_bytecount.eq(self.bus.len),
                    ]
                    m.next = "SEND CMD"

            with m.State("SEND CMD"):
                m.d.sync += [
                    snd_bitcount.eq(snd_bitcount - 1),
                    sr.eq(Cat(C(0b1, 1), sr[:-1])),
                ]
                with m.If(snd_bitcount == 0):
                    m.next = "RECEIVING"

            with m.State("RECEIVING"):
                m.d.sync += [
                    rcv_bitcount.eq(rcv_bitcount - 1),
                    sr.eq(Cat(self.spi_cipo, sr[:-1])),
                ]
                with m.If(rcv_bitcount == 0):
                    m.d.sync += [
                        rcv_bytecount.eq(rcv_bytecount - 1),
                        rcv_bitcount.eq(7),
                        self.bus.valid.eq(1),
                    ]
                    with m.If(rcv_bytecount == 0):
                        m.d.sync += [
                            self.spi_cs.eq(0),
                            snd_bitcount.eq(TRES1_TDP_CYCLES - 1),
                        ]
                        m.next = "POWER DOWN"
                    with m.Else():
                        m.next = "RECEIVING"

            with m.State("POWER DOWN"):
                with m.If(snd_bitcount != 0):
                    m.d.sync += snd_bitcount.eq(snd_bitcount - 1)
                with m.Else():
                    m.next = "IDLE"

        return m
