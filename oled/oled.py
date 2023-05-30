from typing import Final, Optional

from amaranth import ClockSignal, Elaboratable, Instance, Module, Signal
from amaranth.build import Platform
from amaranth.lib.enum import IntEnum
from amaranth.lib.fifo import SyncFIFO

from common import Hz
from i2c import I2C, I2CBus
from .clser import Clser
from .locator import Locator
from .rom import OFFSET_CHAR, OFFSET_DISPLAY_OFF, OFFSET_DISPLAY_ON
from .rom_writer import ROMWriter
from .scroller import Scroller

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
        ID = 0x08

    class Result(IntEnum, shape=2):
        SUCCESS = 0
        BUSY = 1
        FAILURE = 2

    build_i2c: bool

    i2c: I2C | Instance
    rom_writer: ROMWriter
    locator: Locator
    clser: Clser
    scroller: Scroller

    i_fifo: SyncFIFO
    i_i2c_ack_in: Signal  # For blackbox simulation only
    o_result: Signal

    i2c_bus: I2CBus

    row: Signal
    col: Signal
    cursor: Signal

    def __init__(self, *, speed: Hz, build_i2c: bool):
        self.build_i2c = build_i2c

        if build_i2c:
            self.i2c = I2C(speed=speed)
        self.rom_writer = ROMWriter(addr=OLED.ADDR)
        self.locator = Locator(addr=OLED.ADDR)
        self.clser = Clser(addr=OLED.ADDR)
        self.scroller = Scroller(addr=OLED.ADDR)

        self.i_fifo = SyncFIFO(width=8, depth=1)
        self.i_i2c_ack_in = Signal()
        self.o_result = Signal(OLED.Result)

        self.i2c_bus = I2CBus()

        self.row = Signal(range(1, 17), reset=1)
        self.col = Signal(range(1, 17), reset=1)
        self.cursor = Signal()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        if self.build_i2c:
            m.d.comb += self.i2c.bus.connect(self.i2c_bus)
        else:
            self.i2c = Instance(
                "i2c",
                i_clk=ClockSignal(),
                i_in_fifo_w_data=self.i2c_bus.i_in_fifo_w_data,
                i_in_fifo_w_en=self.i2c_bus.i_in_fifo_w_en,
                i_stb=self.i2c_bus.i_stb,
                i_ack_in=self.i_i2c_ack_in,
                o_ack=self.i2c_bus.o_ack,
                o_busy=self.i2c_bus.o_busy,
                o_in_fifo_w_rdy=self.i2c_bus.o_in_fifo_w_rdy,
            )

        m.submodules.i2c = self.i2c
        m.submodules.rom_writer = self.rom_writer
        m.submodules.locator = self.locator
        m.submodules.clser = self.clser
        m.submodules.scroller = self.scroller

        m.submodules.i_fifo = self.i_fifo

        i_in_fifo_w_data = Signal(9)
        i_in_fifo_w_en = Signal()
        i_out_fifo_r_en = Signal()
        i_stb = Signal()

        with m.If(self.rom_writer.o_busy):
            m.d.comb += self.i2c_bus.connect(self.rom_writer.i2c_bus)
        with m.Elif(self.locator.o_busy):
            m.d.comb += self.i2c_bus.connect(self.locator.i2c_bus)
        with m.Elif(self.clser.o_busy):
            m.d.comb += self.i2c_bus.connect(self.clser.i2c_bus)
        with m.Elif(self.scroller.o_busy):
            m.d.comb += self.i2c_bus.connect(self.scroller.i2c_bus)
        with m.Else():
            m.d.comb += [
                self.i2c_bus.i_in_fifo_w_data.eq(i_in_fifo_w_data),
                self.i2c_bus.i_in_fifo_w_en.eq(i_in_fifo_w_en),
                self.i2c_bus.i_out_fifo_r_en.eq(i_out_fifo_r_en),
                self.i2c_bus.i_stb.eq(i_stb),
            ]

        # TODO: actually flash cursor when on

        command = Signal(8)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.i_fifo.r_rdy & self.i2c_bus.o_in_fifo_w_rdy):
                    m.d.sync += [
                        command.eq(self.i_fifo.r_data),
                        self.i_fifo.r_en.eq(1),
                        self.o_result.eq(OLED.Result.BUSY),
                    ]
                    m.next = "START: STROBED I_FIFO R_EN"

            with m.State("START: STROBED I_FIFO R_EN"):
                m.d.sync += self.i_fifo.r_en.eq(0)
                with m.Switch(command):
                    with m.Case(OLED.Command.NOP):
                        m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                        m.next = "IDLE"

                    with m.Case(OLED.Command.DISPLAY_ON):
                        m.d.sync += [
                            self.rom_writer.i_index.eq(OFFSET_DISPLAY_ON),
                            self.rom_writer.i_stb.eq(1),
                        ]
                        m.next = "ROM WRITE SINGLE: STROBED ROM WRITER"

                    with m.Case(OLED.Command.DISPLAY_OFF):
                        m.d.sync += [
                            self.rom_writer.i_index.eq(OFFSET_DISPLAY_OFF),
                            self.rom_writer.i_stb.eq(1),
                        ]
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
                        m.d.sync += [
                            self.cursor.eq(1),
                            self.o_result.eq(OLED.Result.SUCCESS),
                        ]
                        m.next = "IDLE"

                    with m.Case(OLED.Command.CURSOR_OFF):
                        m.d.sync += [
                            self.cursor.eq(0),
                            self.o_result.eq(OLED.Result.SUCCESS),
                        ]
                        m.next = "IDLE"

                    with m.Case(OLED.Command.ID):
                        m.next = "ID: START"

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

            with m.State("ID: START"):
                m.d.sync += [
                    i_in_fifo_w_data.eq(0x179),
                    i_in_fifo_w_en.eq(0x179),
                ]
                m.next = "ID: START: STROBED W_EN"
            with m.State("ID: START: STROBED W_EN"):
                m.d.sync += [
                    i_in_fifo_w_en.eq(0),
                    i_stb.eq(1),
                ]
                m.next = "ID: START: STROBED I_STB"
            with m.State("ID: START: STROBED I_STB"):
                m.d.sync += i_stb.eq(0)
                m.next = "ID: START: UNSTROBED I_STB"
            with m.State("ID: START: UNSTROBED I_STB"):
                with m.If(
                    self.i2c_bus.o_busy
                    & self.i2c_bus.o_ack
                    & self.i2c_bus.o_in_fifo_w_rdy
                ):
                    m.d.sync += [
                        i_in_fifo_w_data.eq(0x00),
                        i_in_fifo_w_en.eq(0x00),
                    ]
                    m.next = "ID: RECV: WAIT"
                with m.Elif(~self.i2c_bus.o_busy):
                    m.d.sync += self.o_result.eq(OLED.Result.FAILURE)
                    m.next = "IDLE"
            id_recvd = Signal(8)
            with m.State("ID: RECV: WAIT"):
                m.d.sync += i_in_fifo_w_en.eq(0)
                with m.If(self.i2c_bus.o_out_fifo_r_rdy):
                    m.d.sync += [
                        id_recvd.eq(self.i2c_bus.o_out_fifo_r_data),
                        i_out_fifo_r_en.eq(1),
                    ]
                    m.next = "ID: RECV: STROBED R_EN"
                with m.Elif(~self.i2c_bus.o_busy):
                    m.d.sync += self.o_result.eq(OLED.Result.FAILURE)
                    m.next = "IDLE"
            with m.State("ID: RECV: STROBED R_EN"):
                m.d.sync += i_out_fifo_r_en.eq(0)
                # TODO Actually do something with it
                m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                m.next = "IDLE"

        return m

    def locate_states(self, m: Module):
        with m.State("LOCATE: ROW: WAIT"):
            with m.If(self.i_fifo.r_rdy):
                with m.If(self.i_fifo.r_data != 0):
                    m.d.sync += [
                        self.row.eq(self.i_fifo.r_data),
                        self.locator.i_row.eq(self.i_fifo.r_data),
                    ]
                with m.Else():
                    m.d.sync += self.locator.i_row.eq(0)
                m.d.sync += self.i_fifo.r_en.eq(1)
                m.next = "LOCATE: ROW: STROBED R_EN"

        with m.State("LOCATE: ROW: STROBED R_EN"):
            m.d.sync += self.i_fifo.r_en.eq(0)
            m.next = "LOCATE: COL: WAIT"

        with m.State("LOCATE: COL: WAIT"):
            with m.If(self.i_fifo.r_rdy):
                with m.If(self.i_fifo.r_data != 0):
                    m.d.sync += [
                        self.col.eq(self.i_fifo.r_data),
                        self.locator.i_col.eq(self.i_fifo.r_data),
                    ]
                with m.Else():
                    m.d.sync += self.locator.i_col.eq(0)
                m.d.sync += [
                    self.i_fifo.r_en.eq(1),
                    self.locator.i_stb.eq(1),
                ]
                m.next = "LOCATE: COL: STROBED R_EN"

        with m.State("LOCATE: COL: STROBED R_EN"):
            m.d.sync += [
                self.i_fifo.r_en.eq(0),
                self.locator.i_stb.eq(0),
            ]
            m.next = "LOCATE: UNSTROBED LOCATOR"

        with m.State("LOCATE: UNSTROBED LOCATOR"):
            with m.If(~self.locator.o_busy):
                m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                m.next = "IDLE"

    def print_states(self, m: Module):
        remaining = Signal(8)

        with m.State("PRINT: COUNT: WAIT"):
            with m.If(self.i_fifo.r_rdy):
                m.d.sync += [
                    self.i_fifo.r_en.eq(1),
                    remaining.eq(self.i_fifo.r_data),
                ]
                m.next = "PRINT: COUNT: STROBED R_EN"

        with m.State("PRINT: COUNT: STROBED R_EN"):
            m.d.sync += self.i_fifo.r_en.eq(0)
            with m.If(remaining == 0):
                m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                m.next = "IDLE"
            with m.Else():
                m.next = "PRINT: DATA: WAIT"

        with m.State("PRINT: DATA: WAIT"):
            with m.If(self.i_fifo.r_rdy):
                m.d.sync += self.i_fifo.r_en.eq(1)
                with m.If(self.i_fifo.r_data == 13):
                    # CR
                    m.d.sync += [
                        self.col.eq(1),
                        self.locator.i_col.eq(1),
                        self.locator.i_row.eq(0),
                        self.locator.i_stb.eq(1),
                    ]
                    m.next = "PRINT: DATA: LOC ADJUST: STROBED LOCATOR"
                with m.Elif(self.i_fifo.r_data == 10):
                    # LF
                    with m.If(self.row == 16):
                        m.d.sync += [
                            self.col.eq(1),
                            self.locator.i_row.eq(0),
                            self.locator.i_col.eq(1),
                            self.locator.i_stb.eq(1),
                        ]
                        m.next = (
                            "PRINT: DATA: LOC ADJUST: STROBED LOCATOR, NEEDS SCROLL"
                        )
                    with m.Else():
                        m.d.sync += [
                            self.col.eq(1),
                            self.row.eq(self.row + 1),
                            self.locator.i_row.eq(self.row + 1),
                            self.locator.i_col.eq(1),
                            self.locator.i_stb.eq(1),
                        ]
                        m.next = "PRINT: DATA: LOC ADJUST: STROBED LOCATOR"
                with m.Else():
                    m.d.sync += [
                        self.rom_writer.i_index.eq(OFFSET_CHAR + self.i_fifo.r_data),
                        self.rom_writer.i_stb.eq(1),
                    ]
                    m.next = "PRINT: DATA: STROBED ROM WRITER"

        with m.State("PRINT: DATA: STROBED ROM WRITER"):
            m.d.sync += [
                self.rom_writer.i_stb.eq(0),
                self.i_fifo.r_en.eq(0),
            ]
            # Page addressing mode automatically matches our column adjust;
            # we need to manually change page when we wrap, though.
            with m.If(self.col == 16):
                with m.If(self.row == 16):
                    m.d.sync += self.col.eq(1)
                    m.next = "PRINT: DATA: UNSTROBED ROM WRITER, NEEDS SCROLL"
                with m.Else():
                    m.d.sync += [
                        self.col.eq(1),
                        self.row.eq(self.row + 1),
                    ]
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

        with m.State("PRINT: DATA: UNSTROBED ROM WRITER, NEEDS SCROLL"):
            with m.If(~self.rom_writer.o_busy):
                m.next = "PRINT: DATA: SCROLL"

        with m.State("PRINT: DATA: PAGE ADJUST"):
            with m.If(self.i2c_bus.o_in_fifo_w_rdy):
                m.d.sync += [
                    self.locator.i_row.eq(self.row),
                    self.locator.i_col.eq(0),
                    self.locator.i_stb.eq(1),
                ]
                m.next = "PRINT: DATA: LOC ADJUST: STROBED LOCATOR"

        with m.State("PRINT: DATA: LOC ADJUST: STROBED LOCATOR"):
            m.d.sync += [
                self.i_fifo.r_en.eq(0),
                self.locator.i_stb.eq(0),
            ]
            m.next = "PRINT: DATA: LOC ADJUST: UNSTROBED LOCATOR"

        with m.State("PRINT: DATA: LOC ADJUST: UNSTROBED LOCATOR"):
            with m.If(~self.locator.o_busy):
                with m.If(remaining == 1):
                    m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                    m.next = "IDLE"
                with m.Else():
                    m.d.sync += remaining.eq(remaining - 1)
                    m.next = "PRINT: DATA: WAIT"

        with m.State("PRINT: DATA: LOC ADJUST: STROBED LOCATOR, NEEDS SCROLL"):
            m.d.sync += [
                self.locator.i_stb.eq(0),
                self.i_fifo.r_en.eq(0),
            ]
            m.next = "PRINT: DATA: LOC ADJUST: UNSTROBED LOCATOR, NEEDS SCROLL"

        with m.State("PRINT: DATA: LOC ADJUST: UNSTROBED LOCATOR, NEEDS SCROLL"):
            with m.If(~self.locator.o_busy):
                m.next = "PRINT: DATA: SCROLL"

        with m.State("PRINT: DATA: SCROLL"):
            m.d.sync += self.scroller.i_stb.eq(1)
            m.next = "PRINT: DATA: SCROLL: STROBED SCROLLER"

        with m.State("PRINT: DATA: SCROLL: STROBED SCROLLER"):
            m.d.sync += self.scroller.i_stb.eq(0)
            m.next = "PRINT: DATA: SCROLL: UNSTROBED SCROLLER"

        with m.State("PRINT: DATA: SCROLL: UNSTROBED SCROLLER"):
            with m.If(~self.scroller.o_busy):
                with m.If(remaining == 1):
                    m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                    m.next = "IDLE"
                with m.Else():
                    m.d.sync += remaining.eq(remaining - 1)
                    m.next = "PRINT: DATA: WAIT"
