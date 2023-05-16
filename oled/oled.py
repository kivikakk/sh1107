from typing import Final, Optional

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform
from amaranth.lib.enum import IntEnum
from amaranth.lib.fifo import SyncFIFO

from common import Hz
from i2c import I2C
from .rom_writer import ROMWriter

__all__ = ["OLED"]


class OLED(Elaboratable):
    ADDR: Final[int] = 0x3C

    class Command(IntEnum, shape=8):
        NOP = 0x00
        DISPLAY_ON = 0x01
        DISPLAY_OFF = 0x02
        CLS = 0x03
        LOCATE = 0x04
        PRINT = 0x05
        CURSOR_ON = 0x06
        CURSOR_OFF = 0x07

    class Result(IntEnum):
        SUCCESS = 0
        BUSY = 1
        FAILURE = 2

    i2c: I2C
    rom_writer: ROMWriter

    i_fifo: SyncFIFO
    o_result: Signal

    def __init__(self, *, speed: Hz):
        self.i2c = I2C(speed=speed)
        self.rom_writer = ROMWriter(addr=OLED.ADDR)

        self.i_fifo = SyncFIFO(width=8, depth=1)
        self.o_result = Signal(OLED.Result)

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.i2c = self.i2c
        m.submodules.rom_writer = self.rom_writer
        m.submodules.i_fifo = self.i_fifo

        with m.If(self.rom_writer.o_busy):
            # TODO(AEC): compile this all into one coherent interface that we can
            # connect/Mux/whatever.
            m.d.comb += self.rom_writer.i_i2c_fifo_w_rdy.eq(self.i2c.fifo.w_rdy)
            m.d.comb += self.rom_writer.i_i2c_o_busy.eq(self.i2c.o_busy)
            m.d.comb += self.rom_writer.i_i2c_o_ack.eq(self.i2c.o_ack)

            m.d.comb += self.i2c.fifo.w_data.eq(self.rom_writer.o_i2c_fifo_w_data)
            m.d.comb += self.i2c.fifo.w_en.eq(self.rom_writer.o_i2c_fifo_w_en)
            m.d.comb += self.i2c.i_stb.eq(self.rom_writer.o_i2c_i_stb)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.i_fifo.r_rdy & self.i2c.fifo.w_rdy):
                    m.d.sync += self.i_fifo.r_en.eq(1)
                    m.next = "START: STROBED I_FIFO R_EN"

            with m.State("START: STROBED I_FIFO R_EN"):
                m.d.sync += self.i_fifo.r_en.eq(0)
                m.next = "START: UNSTROBED I_FIFO R_EN"

            with m.State("START: UNSTROBED I_FIFO R_EN"):
                m.d.sync += self.rom_writer.i_index.eq(self.i_fifo.r_data - 1)
                m.d.sync += self.rom_writer.i_stb.eq(1)
                m.d.sync += self.o_result.eq(OLED.Result.BUSY)
                m.next = "START: STROBED ROM WRITER"

            with m.State("START: STROBED ROM WRITER"):
                m.d.sync += self.rom_writer.i_stb.eq(0)
                m.next = "START: UNSTROBED ROM WRITER"

            with m.State("START: UNSTROBED ROM WRITER"):
                with m.If(~self.rom_writer.o_busy):
                    m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                    m.next = "IDLE"

        return m
