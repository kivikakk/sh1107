from typing import Final, Optional

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform
from amaranth.lib.enum import IntEnum
from amaranth.lib.fifo import SyncFIFO

from common import Hz
from i2c import I2C
from .rom import OFFSET_CHAR, OFFSET_DISPLAY_OFF, OFFSET_DISPLAY_ON
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

    row: Signal
    col: Signal
    cursor: Signal

    def __init__(self, *, speed: Hz):
        self.i2c = I2C(speed=speed)
        self.rom_writer = ROMWriter(addr=OLED.ADDR)

        self.i_fifo = SyncFIFO(width=8, depth=1)
        self.o_result = Signal(OLED.Result)

        self.row = Signal(range(16))
        self.col = Signal(range(16))
        self.cursor = Signal()

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

        # TODO: actually flash cursor when on

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.i_fifo.r_rdy & self.i2c.fifo.w_rdy):
                    m.d.sync += self.i_fifo.r_en.eq(1)
                    m.d.sync += self.o_result.eq(OLED.Result.BUSY)
                    m.next = "START: STROBED I_FIFO R_EN"

            with m.State("START: STROBED I_FIFO R_EN"):
                m.d.sync += self.i_fifo.r_en.eq(0)
                m.next = "START: UNSTROBED I_FIFO R_EN"

            with m.State("START: UNSTROBED I_FIFO R_EN"):
                # self.i_fifo.r_data contains the command!

                with m.Switch(self.i_fifo.r_data):
                    with m.Case(OLED.Command.NOP):
                        m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                        m.next = "IDLE"

                    with m.Case(OLED.Command.DISPLAY_ON):
                        m.d.sync += self.rom_writer.i_index.eq(OFFSET_DISPLAY_ON)
                        m.d.sync += self.rom_writer.i_stb.eq(1)
                        m.next = "ROM WRITE SINGLE: STROBED ROM WRITER"

                    with m.Case(OLED.Command.DISPLAY_OFF):
                        m.d.sync += self.rom_writer.i_index.eq(OFFSET_DISPLAY_OFF)
                        m.d.sync += self.rom_writer.i_stb.eq(1)
                        m.next = "ROM WRITE SINGLE: STROBED ROM WRITER"

                    with m.Case(OLED.Command.CLS):
                        # NYI
                        m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                        m.next = "IDLE"

                    with m.Case(OLED.Command.LOCATE):
                        m.next = "LOCATE: ROW: WAIT"

                    with m.Case(OLED.Command.PRINT):
                        m.next = "PRINT: COUNT: WAIT"

                    with m.Case(OLED.Command.CURSOR_ON):
                        m.d.sync += self.cursor.eq(1)
                        m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                        m.next = "IDLE"

                    with m.Case(OLED.Command.CURSOR_OFF):
                        m.d.sync += self.cursor.eq(0)
                        m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                        m.next = "IDLE"

            self.locateStates(m)
            self.printStates(m)

            with m.State("ROM WRITE SINGLE: STROBED ROM WRITER"):
                m.d.sync += self.rom_writer.i_stb.eq(0)
                m.next = "ROM WRITE SINGLE: UNSTROBED ROM WRITER"

            with m.State("ROM WRITE SINGLE: UNSTROBED ROM WRITER"):
                with m.If(~self.rom_writer.o_busy):
                    m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                    m.next = "IDLE"

        return m

    def locateStates(self, m: Module):
        with m.State("LOCATE: ROW: WAIT"):
            with m.If(self.i_fifo.r_rdy):
                m.d.sync += self.i_fifo.r_en.eq(1)
                m.next = "LOCATE: ROW: STROBED R_EN"

        with m.State("LOCATE: ROW: STROBED R_EN"):
            m.d.sync += self.i_fifo.r_en.eq(0)
            m.next = "LOCATE: ROW: UNSTROBED R_EN"

        with m.State("LOCATE: ROW: UNSTROBED R_EN"):
            with m.If(self.i_fifo.r_data != 0):
                m.d.sync += self.row.eq(self.i_fifo.r_data)
            m.next = "LOCATE: COL: WAIT"

        with m.State("LOCATE: COL: WAIT"):
            with m.If(self.i_fifo.r_rdy):
                m.d.sync += self.i_fifo.r_en.eq(1)
                m.next = "LOCATE: COL: STROBED R_EN"

        with m.State("LOCATE: COL: STROBED R_EN"):
            m.d.sync += self.i_fifo.r_en.eq(0)
            m.next = "LOCATE: COL: UNSTROBED R_EN"

        with m.State("LOCATE: COL: UNSTROBED R_EN"):
            with m.If(self.i_fifo.r_data != 0):
                m.d.sync += self.col.eq(self.i_fifo.r_data)
            m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
            m.next = "IDLE"

    def printStates(self, m: Module):
        remaining = Signal(8)

        with m.State("PRINT: COUNT: WAIT"):
            with m.If(self.i_fifo.r_rdy):
                m.d.sync += self.i_fifo.r_en.eq(1)
                m.next = "PRINT: COUNT: STROBED R_EN"

        with m.State("PRINT: COUNT: STROBED R_EN"):
            m.d.sync += self.i_fifo.r_en.eq(0)
            m.next = "PRINT: COUNT: UNSTROBED R_EN"

        with m.State("PRINT: COUNT: UNSTROBED R_EN"):
            with m.If(self.i_fifo.r_data != 0):
                m.d.sync += remaining.eq(self.i_fifo.r_data)
                m.next = "PRINT: DATA: WAIT"
            with m.Else():
                m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                m.next = "IDLE"

        with m.State("PRINT: DATA: WAIT"):
            with m.If(self.i_fifo.r_rdy):
                m.d.sync += self.i_fifo.r_en.eq(1)
                m.next = "PRINT: DATA: STROBED R_EN"

        with m.State("PRINT: DATA: STROBED R_EN"):
            m.d.sync += self.i_fifo.r_en.eq(0)
            m.next = "PRINT: DATA: UNSTROBED R_EN"

        with m.State("PRINT: DATA: UNSTROBED R_EN"):
            m.d.sync += self.rom_writer.i_index.eq(OFFSET_CHAR + self.i_fifo.r_data)
            m.d.sync += self.rom_writer.i_stb.eq(1)
            m.next = "PRINT: DATA: STROBED ROM WRITER"

        with m.State("PRINT: DATA: STROBED ROM WRITER"):
            m.d.sync += self.rom_writer.i_stb.eq(0)
            m.next = "PRINT: DATA: UNSTROBED ROM WRITER"

        with m.State("PRINT: DATA: UNSTROBED ROM WRITER"):
            with m.If(~self.rom_writer.o_busy):
                with m.If(remaining == 1):
                    m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                    m.next = "IDLE"
                with m.Else():
                    m.d.sync += remaining.eq(remaining - 1)
                    m.next = "PRINT: DATA: WAIT"
