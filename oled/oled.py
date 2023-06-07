from typing import Final, Optional

from amaranth import Mux  # pyright: ignore[reportUnknownVariableType]
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

    # 1MHz is a bit unacceptable.  It seems to mostly work, except that
    # switching between command and data before doing a read isn't consistent.
    # There's a clear reason why this might be the case: the SH1107 datasheet
    # specifies 400kHz as the maximum SCL clock frequency, and further specifies
    # a bunch of timings that we don't meet at 1MHz — particularly
    # START/STOP/RESTART hold times, which are all listed as min 0.6μs.  At
    # 1MHz, we're only holding for 0.5μs.
    #
    # I tried adding some delays after switching to command mode (i.e. add some
    # extra commands!) before restarting the transaction in read, but it still
    # ended up giving me display RAM data back.  This doesn't happen at 400kHz.
    VALID_BUILD_SPEEDS: Final[list[int]] = [
        100_000,
        400_000,
    ]
    VALID_SPEEDS: Final[list[int]] = VALID_BUILD_SPEEDS + [
        2_000_000,  # for vsh
    ]
    DEFAULT_SPEED: Final[int] = 400_000
    DEFAULT_SPEED_VSH: Final[int] = 2_000_000

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
    i2c_bus: I2CBus

    rom_writer: ROMWriter
    locator: Locator
    clser: Clser
    scroller: Scroller
    own_i2c_bus: I2CBus

    i_fifo: SyncFIFO
    i_i2c_bb_in_ack: Signal  # For blackbox simulation only
    i_i2c_bb_in_out_fifo_data: Signal  # For blackbox simulation only
    i_i2c_bb_in_out_fifo_stb: Signal  # For blackbox simulation only
    o_result: Signal

    row: Signal
    col: Signal
    cursor: Signal

    chpr_data: Signal
    chpr_run: Signal

    def __init__(self, *, speed: Hz, build_i2c: bool):
        assert speed.value in self.VALID_SPEEDS

        self.build_i2c = build_i2c

        if build_i2c:
            self.i2c = I2C(speed=speed)
        else:
            self.i_i2c_bb_in_ack = Signal()
            self.i_i2c_bb_in_out_fifo_data = Signal(8)
            self.i_i2c_bb_in_out_fifo_stb = Signal()
        self.i2c_bus = I2CBus()

        self.rom_writer = ROMWriter(addr=OLED.ADDR)
        self.locator = Locator(addr=OLED.ADDR)
        self.clser = Clser(addr=OLED.ADDR)
        self.scroller = Scroller(addr=OLED.ADDR)
        self.own_i2c_bus = I2CBus()

        self.i_fifo = SyncFIFO(width=8, depth=1)
        self.o_result = Signal(OLED.Result)

        self.row = Signal(range(1, 17), reset=1)
        self.col = Signal(range(1, 17), reset=1)
        self.cursor = Signal()

        self.chpr_data = Signal(8)
        self.chpr_run = Signal()

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
                i_out_fifo_r_en=self.i2c_bus.i_out_fifo_r_en,
                i_stb=self.i2c_bus.i_stb,
                i_bb_in_ack=self.i_i2c_bb_in_ack,
                i_bb_in_out_fifo_data=self.i_i2c_bb_in_out_fifo_data,
                i_bb_in_out_fifo_stb=self.i_i2c_bb_in_out_fifo_stb,
                o_ack=self.i2c_bus.o_ack,
                o_busy=self.i2c_bus.o_busy,
                o_in_fifo_w_rdy=self.i2c_bus.o_in_fifo_w_rdy,
                o_out_fifo_r_rdy=self.i2c_bus.o_out_fifo_r_rdy,
                o_out_fifo_r_data=self.i2c_bus.o_out_fifo_r_data,
            )

        m.submodules.i2c = self.i2c
        m.submodules.rom_writer = self.rom_writer
        m.submodules.locator = self.locator
        m.submodules.clser = self.clser
        m.submodules.scroller = self.scroller

        m.submodules.i_fifo = self.i_fifo

        with m.If(self.rom_writer.o_busy):
            m.d.comb += self.i2c_bus.connect(self.rom_writer.i2c_bus)
        with m.Elif(self.locator.o_busy):
            m.d.comb += self.i2c_bus.connect(self.locator.i2c_bus)
        with m.Elif(self.clser.o_busy):
            m.d.comb += self.i2c_bus.connect(self.clser.i2c_bus)
        with m.Elif(self.scroller.o_busy):
            m.d.comb += self.i2c_bus.connect(self.scroller.i2c_bus)
        with m.Else():
            m.d.comb += self.i2c_bus.connect(self.own_i2c_bus)

        m.d.comb += self.locator.i_adjust.eq(self.scroller.o_adjusted)

        # TODO: actually flash cursor when on

        command = Signal(8)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.i_fifo.r_rdy & self.own_i2c_bus.o_in_fifo_w_rdy):
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
                            self.scroller.i_rst.eq(1),
                        ]
                        m.next = "DISPLAY ON: STROBED ROM WRITER"

                    with m.Case(OLED.Command.DISPLAY_OFF):
                        m.d.sync += [
                            self.rom_writer.i_index.eq(OFFSET_DISPLAY_OFF),
                            self.rom_writer.i_stb.eq(1),
                        ]
                        m.next = "ROM WRITE SINGLE: STROBED ROM WRITER"

                    with m.Case(OLED.Command.CLS):
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

            self.locate_states(m)
            self.print_states(m)
            self.id_states(m)

            with m.State("CLSER: STROBED"):
                m.d.sync += self.clser.i_stb.eq(0)
                m.next = "CLSER: UNSTROBED"

            with m.State("CLSER: UNSTROBED"):
                with m.If(~self.clser.o_busy):
                    m.d.sync += [
                        self.locator.i_row.eq(self.row),
                        self.locator.i_col.eq(self.col),
                        self.locator.i_stb.eq(1),
                    ]
                    m.next = "CLSER: STROBED LOCATOR"

            with m.State("CLSER: STROBED LOCATOR"):
                m.d.sync += self.locator.i_stb.eq(0)
                m.next = "CLSER: UNSTROBED LOCATOR"

            with m.State("CLSER: UNSTROBED LOCATOR"):
                with m.If(~self.locator.o_busy):
                    m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                    m.next = "IDLE"

            with m.State("DISPLAY ON: STROBED ROM WRITER"):
                m.d.sync += [
                    self.rom_writer.i_stb.eq(0),
                    self.scroller.i_rst.eq(0),
                ]
                m.next = "ROM WRITE SINGLE: UNSTROBED ROM WRITER"

            with m.State("ROM WRITE SINGLE: STROBED ROM WRITER"):
                m.d.sync += self.rom_writer.i_stb.eq(0)
                m.next = "ROM WRITE SINGLE: UNSTROBED ROM WRITER"

            with m.State("ROM WRITE SINGLE: UNSTROBED ROM WRITER"):
                with m.If(~self.rom_writer.o_busy):
                    m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                    m.next = "IDLE"

        self.chpr_fsm(m)

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
                m.d.sync += [
                    self.i_fifo.r_en.eq(1),
                    self.chpr_data.eq(self.i_fifo.r_data),
                    self.chpr_run.eq(1),
                ]
                m.next = "PRINT: DATA: CHPR RUNNING"

        with m.State("PRINT: DATA: CHPR RUNNING"):
            m.d.sync += self.i_fifo.r_en.eq(0)
            with m.If(~self.chpr_run):
                with m.If(remaining == 1):
                    m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                    m.next = "IDLE"
                with m.Else():
                    m.d.sync += remaining.eq(remaining - 1)
                    m.next = "PRINT: DATA: WAIT"

    def chpr_fsm(self, m: Module):
        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.chpr_run):
                    with m.If(self.chpr_data == 13):
                        # CR
                        m.d.sync += [
                            self.col.eq(1),
                            self.locator.i_col.eq(1),
                            self.locator.i_row.eq(0),
                            self.locator.i_stb.eq(1),
                        ]
                        m.next = "CHPR: STROBED LOCATOR"
                    with m.Elif(self.chpr_data == 10):
                        # LF
                        with m.If(self.row == 16):
                            m.d.sync += [
                                self.col.eq(1),
                                self.scroller.i_stb.eq(1),
                            ]
                            m.next = "CHPR: STROBED SCROLLER"
                        with m.Else():
                            m.d.sync += [
                                self.col.eq(1),
                                self.row.eq(self.row + 1),
                                self.locator.i_row.eq(self.row + 1),
                                self.locator.i_col.eq(1),
                                self.locator.i_stb.eq(1),
                            ]
                            m.next = "CHPR: STROBED LOCATOR"
                    with m.Else():
                        m.d.sync += [
                            self.rom_writer.i_index.eq(OFFSET_CHAR + self.chpr_data),
                            self.rom_writer.i_stb.eq(1),
                        ]
                        m.next = "CHPR: STROBED ROM WRITER"

            with m.State("CHPR: STROBED ROM WRITER"):
                m.d.sync += self.rom_writer.i_stb.eq(0)
                with m.If(self.col == 16):
                    with m.If(self.row == 16):
                        m.d.sync += self.col.eq(1)
                        m.next = "CHPR: UNSTROBED ROM WRITER, NEEDS SCROLL"
                    with m.Else():
                        m.d.sync += [
                            self.col.eq(1),
                            self.row.eq(self.row + 1),
                        ]
                        m.next = "CHPR: UNSTROBED ROM WRITER"
                with m.Else():
                    m.d.sync += self.col.eq(self.col + 1)
                    m.next = "CHPR: UNSTROBED ROM WRITER"

            with m.State("CHPR: UNSTROBED ROM WRITER"):
                with m.If(~self.rom_writer.o_busy):
                    m.d.sync += [
                        self.locator.i_row.eq(self.row),
                        self.locator.i_col.eq(self.col),
                        self.locator.i_stb.eq(1),
                    ]
                    m.next = "CHPR: STROBED LOCATOR"

            with m.State("CHPR: UNSTROBED ROM WRITER, NEEDS SCROLL"):
                with m.If(~self.rom_writer.o_busy):
                    m.d.sync += self.scroller.i_stb.eq(1)
                    m.next = "CHPR: STROBED SCROLLER"

            with m.State("CHPR: STROBED SCROLLER"):
                m.d.sync += self.scroller.i_stb.eq(0)
                m.next = "CHPR: UNSTROBED SCROLLER"

            with m.State("CHPR: UNSTROBED SCROLLER"):
                with m.If(~self.scroller.o_busy):
                    m.d.sync += [
                        self.locator.i_row.eq(self.row),
                        self.locator.i_col.eq(self.col),
                        self.locator.i_stb.eq(1),
                    ]
                    m.next = "CHPR: STROBED LOCATOR"

            with m.State("CHPR: STROBED LOCATOR"):
                m.d.sync += self.locator.i_stb.eq(0)
                m.next = "CHPR: UNSTROBED LOCATOR"

            with m.State("CHPR: UNSTROBED LOCATOR"):
                with m.If(~self.locator.o_busy):
                    m.d.sync += self.chpr_run.eq(0)
                    m.next = "IDLE"

    def id_states(self, m: Module):
        # XXX(Ch): hack just to test read capability

        id_recvd = Signal(8)

        with m.State("ID: START"):
            m.d.sync += [
                self.own_i2c_bus.i_in_fifo_w_data.eq(0x178),
                self.own_i2c_bus.i_in_fifo_w_en.eq(1),
            ]
            m.next = "ID: START WRITE: STROBED W_EN"

        with m.State("ID: START WRITE: STROBED W_EN"):
            m.d.sync += [
                self.own_i2c_bus.i_in_fifo_w_en.eq(0),
                self.own_i2c_bus.i_stb.eq(1),
            ]
            m.next = "ID: START WRITE: STROBED I_STB"

        with m.State("ID: START WRITE: STROBED I_STB"):
            m.d.sync += self.own_i2c_bus.i_stb.eq(0)
            m.next = "ID: START WRITE: UNSTROBED I_STB"

        with m.State("ID: START WRITE: UNSTROBED I_STB"):
            with m.If(
                self.own_i2c_bus.o_busy
                & self.own_i2c_bus.o_ack
                & self.own_i2c_bus.o_in_fifo_w_rdy
            ):
                m.d.sync += [
                    self.own_i2c_bus.i_in_fifo_w_data.eq(0x00),  # Command/NC
                    self.own_i2c_bus.i_in_fifo_w_en.eq(1),
                ]
                m.next = "ID: WRITE CMD: STROBED W_EN"
            with m.Elif(~self.own_i2c_bus.o_busy):
                m.d.sync += self.o_result.eq(OLED.Result.FAILURE)
                m.next = "IDLE"

        with m.State("ID: WRITE CMD: STROBED W_EN"):
            m.d.sync += self.own_i2c_bus.i_in_fifo_w_en.eq(0)
            m.next = "ID: WRITE CMD: UNSTROBED W_EN"

        with m.State("ID: WRITE CMD: UNSTROBED W_EN"):
            with m.If(
                self.own_i2c_bus.o_busy
                & self.own_i2c_bus.o_ack
                & self.own_i2c_bus.o_in_fifo_w_rdy
            ):
                m.d.sync += [
                    self.own_i2c_bus.i_in_fifo_w_data.eq(0x179),
                    self.own_i2c_bus.i_in_fifo_w_en.eq(1),
                ]
                m.next = "ID: START READ: STROBED W_EN"
            with m.Elif(~self.own_i2c_bus.o_busy):
                m.d.sync += self.o_result.eq(OLED.Result.FAILURE)
                m.next = "IDLE"

        with m.State("ID: START READ: STROBED W_EN"):
            m.d.sync += self.own_i2c_bus.i_in_fifo_w_en.eq(0)
            m.next = "ID: START READ: UNSTROBED W_EN"

        with m.State("ID: START READ: UNSTROBED W_EN"):
            with m.If(
                self.own_i2c_bus.o_busy
                & self.own_i2c_bus.o_ack
                & self.own_i2c_bus.o_in_fifo_w_rdy
            ):
                m.d.sync += [
                    self.own_i2c_bus.i_in_fifo_w_data.eq(0x00),
                    self.own_i2c_bus.i_in_fifo_w_en.eq(1),
                ]
                m.next = "ID: RECV: WAIT"
            with m.Elif(~self.own_i2c_bus.o_busy):
                m.d.sync += self.o_result.eq(OLED.Result.FAILURE)
                m.next = "IDLE"

        with m.State("ID: RECV: WAIT"):
            m.d.sync += self.own_i2c_bus.i_in_fifo_w_en.eq(0)
            with m.If(self.own_i2c_bus.o_out_fifo_r_rdy):
                m.d.sync += [
                    id_recvd.eq(self.own_i2c_bus.o_out_fifo_r_data),
                    self.own_i2c_bus.i_out_fifo_r_en.eq(1),
                ]
                m.next = "ID: RECV: STROBED R_EN"
            with m.Elif(~self.own_i2c_bus.o_busy):
                m.d.sync += self.o_result.eq(OLED.Result.FAILURE)
                m.next = "IDLE"

        with m.State("ID: RECV: STROBED R_EN"):
            m.d.sync += self.own_i2c_bus.i_out_fifo_r_en.eq(0)
            with m.If(~self.own_i2c_bus.o_busy):
                first_half = id_recvd[4:8]
                m.d.sync += [
                    self.chpr_data.eq(
                        Mux(
                            first_half > 9,
                            ord("A") + first_half - 10,
                            ord("0") + first_half,
                        )
                    ),
                    self.chpr_run.eq(1),
                ]
                m.next = "ID: FIRST HALF: CHPR RUNNING"

        with m.State("ID: FIRST HALF: CHPR RUNNING"):
            with m.If(~self.chpr_run):
                second_half = id_recvd[:4]
                m.d.sync += [
                    self.chpr_data.eq(
                        Mux(
                            second_half > 9,
                            ord("A") + second_half - 10,
                            ord("0") + second_half,
                        )
                    ),
                    self.chpr_run.eq(1),
                ]
                m.next = "ID: SECOND HALF: CHPR RUNNING"

        with m.State("ID: SECOND HALF: CHPR RUNNING"):
            with m.If(~self.chpr_run):
                m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                m.next = "IDLE"
