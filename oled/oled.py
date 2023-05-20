from typing import Final, Optional

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform
from amaranth.lib.enum import IntEnum
from amaranth.lib.fifo import SyncFIFO

from common import Hz
from i2c import I2C
from .clser import Clser
from .locator import Locator
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
    locator: Locator
    clser: Clser

    i_fifo: SyncFIFO
    o_result: Signal

    i2c_fifo_w_data: Signal
    i2c_fifo_w_en: Signal
    i2c_i_stb: Signal

    row: Signal
    col: Signal
    cursor: Signal

    def __init__(self, *, speed: Hz):
        self.i2c = I2C(speed=speed)
        self.rom_writer = ROMWriter(addr=OLED.ADDR)
        self.locator = Locator(addr=OLED.ADDR)
        self.clser = Clser(addr=OLED.ADDR)

        self.i_fifo = SyncFIFO(width=8, depth=1)
        self.o_result = Signal(OLED.Result)

        self.i2c_fifo_w_data = Signal(9)
        self.i2c_fifo_w_en = Signal()
        self.i2c_i_stb = Signal()

        self.row = Signal(range(1, 17), reset=1)
        self.col = Signal(range(1, 17), reset=1)
        self.cursor = Signal()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.i2c = self.i2c
        m.submodules.rom_writer = self.rom_writer
        m.submodules.locator = self.locator
        m.submodules.clser = self.clser
        m.submodules.i_fifo = self.i_fifo

        self.rom_writer.connect_i2c_in(m, self.i2c)
        self.locator.connect_i2c_in(m, self.i2c)
        self.clser.connect_i2c_in(m, self.i2c)

        with m.If(self.rom_writer.o_busy):
            self.rom_writer.connect_i2c_out(m, self.i2c)
        with m.Elif(self.locator.o_busy):
            self.locator.connect_i2c_out(m, self.i2c)
        with m.Elif(self.clser.o_busy):
            self.clser.connect_i2c_out(m, self.i2c)
        with m.Else():
            m.d.comb += self.i2c.fifo.w_data.eq(self.i2c_fifo_w_data)
            m.d.comb += self.i2c.fifo.w_en.eq(self.i2c_fifo_w_en)
            m.d.comb += self.i2c.i_stb.eq(self.i2c_i_stb)

        # TODO: actually flash cursor when on
        # TODO: print catch "\r", "\n", adjust location

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
                        # TODO: we should either restore page/col after CLS, or
                        # define it as resetting the location
                        m.d.sync += self.clser.i_stb.eq(1)
                        m.next = "CLSER: STROBED"

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

            with m.State("CLSER: STROBED"):
                m.d.sync += self.clser.i_stb.eq(0)
                m.next = "CLSER: UNSTROBED"

            with m.State("CLSER: UNSTROBED"):
                with m.If(~self.clser.o_busy):
                    m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                    m.next = "IDLE"

            self.locate_states(m)
            self.print_states(m)

            with m.State("ROM WRITE SINGLE: STROBED ROM WRITER"):
                m.d.sync += self.rom_writer.i_stb.eq(0)
                m.next = "ROM WRITE SINGLE: UNSTROBED ROM WRITER"

            with m.State("ROM WRITE SINGLE: UNSTROBED ROM WRITER"):
                with m.If(~self.rom_writer.o_busy):
                    m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                    m.next = "IDLE"

        return m

    def locate_states(self, m: Module):
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
                m.d.sync += self.locator.i_row.eq(self.i_fifo.r_data)
            with m.Else():
                m.d.sync += self.locator.i_row.eq(0)
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
                m.d.sync += self.locator.i_col.eq(self.i_fifo.r_data)
            with m.Else():
                m.d.sync += self.locator.i_col.eq(0)
            m.d.sync += self.locator.i_stb.eq(1)
            m.next = "LOCATE: STROBED LOCATOR"

        with m.State("LOCATE: STROBED LOCATOR"):
            m.d.sync += self.locator.i_stb.eq(0)
            m.next = "LOCATE: UNSTROBED LOCATOR"

        with m.State("LOCATE: UNSTROBED LOCATOR"):
            with m.If(~self.locator.o_busy):
                m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                m.next = "IDLE"

    def print_states(self, m: Module):
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
            with m.If(self.i_fifo.r_data == 13):
                # CR
                m.d.sync += self.col.eq(1)
                m.d.sync += self.locator.i_col.eq(1)
                m.d.sync += self.locator.i_row.eq(0)
                m.d.sync += self.locator.i_stb.eq(1)
                m.next = "PRINT: DATA: PAGE ADJUST: STROBED LOCATOR"
            with m.Elif(self.i_fifo.r_data == 10):
                # LF
                m.d.sync += self.col.eq(1)
                m.d.sync += self.row.eq(self.row + 1)  # TODO: scroll
                m.d.sync += self.locator.i_row.eq(self.row + 1)
                m.d.sync += self.locator.i_col.eq(1)
                m.d.sync += self.locator.i_stb.eq(1)
                m.next = "PRINT: DATA: PAGE ADJUST: STROBED LOCATOR"
            with m.Else():
                m.d.sync += self.rom_writer.i_index.eq(OFFSET_CHAR + self.i_fifo.r_data)
                m.d.sync += self.rom_writer.i_stb.eq(1)
                m.next = "PRINT: DATA: STROBED ROM WRITER"

        with m.State("PRINT: DATA: STROBED ROM WRITER"):
            m.d.sync += self.rom_writer.i_stb.eq(0)
            # Page addressing mode automatically matches our column adjust;
            # we need to manually change page when we wrap, though.
            with m.If(self.col == 16):
                m.d.sync += self.col.eq(1)
                m.d.sync += self.row.eq(self.row + 1)  # TODO: scroll
                m.next = "PRINT: DATA: UNSTROBED ROM WRITER, NEEDS PAGE ADJUST"
            with m.Else():
                m.d.sync += self.col.eq(self.col + 1)
                m.next = "PRINT: DATA: UNSTROBED ROM WRITER"

        with m.State("PRINT: DATA: UNSTROBED ROM WRITER"):
            with m.If(~self.rom_writer.o_busy):
                with m.If(remaining == 1):
                    m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                    m.next = "IDLE"
                with m.Else():
                    m.d.sync += remaining.eq(remaining - 1)
                    m.next = "PRINT: DATA: WAIT"

        with m.State("PRINT: DATA: UNSTROBED ROM WRITER, NEEDS PAGE ADJUST"):
            with m.If(~self.rom_writer.o_busy):
                m.next = "PRINT: DATA: PAGE ADJUST"

        with m.State("PRINT: DATA: PAGE ADJUST"):
            with m.If(self.i2c.fifo.w_rdy):
                m.d.sync += self.locator.i_row.eq(self.row)
                m.d.sync += self.locator.i_col.eq(0)
                m.d.sync += self.locator.i_stb.eq(1)
                m.next = "PRINT: DATA: PAGE ADJUST: STROBED LOCATOR"

        with m.State("PRINT: DATA: PAGE ADJUST: STROBED LOCATOR"):
            m.d.sync += self.locator.i_stb.eq(0)
            m.next = "PRINT: DATA: PAGE ADJUST: UNSTROBED LOCATOR"

        with m.State("PRINT: DATA: PAGE ADJUST: UNSTROBED LOCATOR"):
            with m.If(~self.locator.o_busy):
                with m.If(remaining == 1):
                    m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                    m.next = "IDLE"
                with m.Else():
                    m.d.sync += remaining.eq(remaining - 1)
                    m.next = "PRINT: DATA: WAIT"
