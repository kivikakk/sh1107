import math
from typing import Optional, cast

from amaranth import C, Cat, ClockSignal, Elaboratable, Module, Signal
from amaranth.build import Platform
from amaranth_boards.icebreaker import ICEBreakerPlatform

import sim

__all__ = ["SPIFlashReader"]


class SPIFlashReader(Elaboratable):
    spi_copi: Signal
    spi_cipo: Signal
    spi_cs: Signal
    spi_clk: Signal

    i_addr: Signal
    i_len: Signal
    i_stb: Signal
    o_busy: Signal

    o_data: Signal
    o_valid: Signal

    def __init__(self):
        self.spi_copi = Signal()
        self.spi_cipo = Signal()
        self.spi_cs = Signal()
        self.spi_clk = Signal()

        self.i_addr = Signal(24)
        self.i_len = Signal(16)
        self.i_stb = Signal()
        self.o_busy = Signal()

        self.o_data = Signal(8)
        self.o_valid = Signal()

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
        # TODO: fix up the +1s by using 0, letting it wrap
        snd_bitcount = Signal(range(max(32, TRES1_TDP_CYCLES) + 1))

        rcv_bitcount = Signal(range(9))
        rcv_bytecount = Signal.like(self.i_len)

        m.d.comb += [
            self.spi_copi.eq(sr[31]),
            self.spi_clk.eq(self.spi_cs & ~clk),
            self.o_data.eq(sr[:8]),
        ]

        m.d.sync += self.o_valid.eq(0)

        with m.FSM() as fsm:
            m.d.comb += self.o_busy.eq(~fsm.ongoing("IDLE"))

            with m.State("IDLE"):
                with m.If(self.i_stb):
                    m.d.sync += [
                        self.spi_cs.eq(1),
                        sr.eq(0xAB000000),
                        snd_bitcount.eq(32),
                    ]
                    m.next = "POWER-DOWN RELEASE"

            with m.State("POWER-DOWN RELEASE"):
                m.d.sync += [
                    snd_bitcount.eq(snd_bitcount - 1),
                    sr.eq(Cat(C(0b1, 1), sr[:-1])),
                ]
                with m.If(snd_bitcount == 1):
                    m.d.sync += [
                        self.spi_cs.eq(0),
                        snd_bitcount.eq(TRES1_TDP_CYCLES),
                    ]
                    m.next = "WAIT TRES1"

            with m.State("WAIT TRES1"):
                with m.If(snd_bitcount != 0):
                    m.d.sync += snd_bitcount.eq(snd_bitcount - 1)
                with m.Else():
                    m.d.sync += [
                        self.spi_cs.eq(1),
                        sr.eq(Cat(self.i_addr, C(0x03, 8))),
                        snd_bitcount.eq(32),
                        rcv_bitcount.eq(8),
                        rcv_bytecount.eq(self.i_len),
                    ]
                    m.next = "SEND CMD"

            with m.State("SEND CMD"):
                m.d.sync += [
                    snd_bitcount.eq(snd_bitcount - 1),
                    sr.eq(Cat(C(0b1, 1), sr[:-1])),
                ]
                with m.If(snd_bitcount == 1):
                    m.next = "RECEIVING"

            with m.State("RECEIVING"):
                m.d.sync += [
                    rcv_bitcount.eq(rcv_bitcount - 1),
                    sr.eq(Cat(self.spi_cipo, sr[:-1])),
                ]
                with m.If(rcv_bitcount == 1):
                    m.d.sync += [
                        rcv_bytecount.eq(rcv_bytecount - 1),
                        rcv_bitcount.eq(8),
                        self.o_valid.eq(1),
                    ]
                    with m.If(rcv_bytecount == 1):
                        m.d.sync += [
                            self.spi_cs.eq(0),
                            snd_bitcount.eq(TRES1_TDP_CYCLES),
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
