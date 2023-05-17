from typing import Optional

from amaranth import Mux  # pyright: ignore[reportUnknownVariableType]
from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform

from i2c import I2C, RW
from .sh1107 import Cmd, ControlByte

__all__ = ["Locator"]


class Locator(Elaboratable):
    addr: int

    i_row: Signal
    i_col: Signal
    i_stb: Signal

    i_i2c_fifo_w_rdy: Signal
    i_i2c_o_busy: Signal
    i_i2c_o_ack: Signal

    o_busy: Signal

    o_i2c_fifo_w_data: Signal
    o_i2c_fifo_w_en: Signal
    o_i2c_i_stb: Signal

    def __init__(self, *, addr: int):
        self.addr = addr

        self.i_row = Signal(range(17))
        self.i_col = Signal(range(17))
        self.i_stb = Signal()

        self.i_i2c_fifo_w_rdy = Signal()
        self.i_i2c_o_busy = Signal()
        self.i_i2c_o_ack = Signal()

        self.o_busy = Signal()

        self.o_i2c_fifo_w_data = Signal(9)
        self.o_i2c_fifo_w_en = Signal()
        self.o_i2c_i_stb = Signal()

    def connect_i2c_in(self, m: Module, i2c: I2C):
        m.d.comb += [
            self.i_i2c_fifo_w_rdy.eq(i2c.fifo.w_rdy),
            self.i_i2c_o_busy.eq(i2c.o_busy),
            self.i_i2c_o_ack.eq(i2c.o_ack),
        ]

    def connect_i2c_out(self, m: Module, i2c: I2C):
        m.d.comb += [
            i2c.fifo.w_data.eq(self.o_i2c_fifo_w_data),
            i2c.fifo.w_en.eq(self.o_i2c_fifo_w_en),
            i2c.i_stb.eq(self.o_i2c_i_stb),
        ]

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.i_stb):
                    m.d.sync += self.o_busy.eq(1)
                    m.d.sync += self.o_i2c_fifo_w_data.eq((self.addr << 1) | RW.W)
                    m.d.sync += self.o_i2c_fifo_w_en.eq(1)
                    m.next = "START: ADDR: STROBED W_EN"

            with m.State("START: ADDR: STROBED W_EN"):
                m.d.sync += self.o_i2c_fifo_w_en.eq(0)
                m.d.sync += self.o_i2c_i_stb.eq(1)
                m.next = "START: ADDR: STROBED I_STB"

            with m.State("START: ADDR: STROBED I_STB"):
                m.d.sync += self.o_i2c_i_stb.eq(0)
                with m.If(self.i_i2c_fifo_w_rdy):
                    m.d.sync += self.o_i2c_fifo_w_data.eq(
                        ControlByte(False, "Command").to_byte()
                    )
                    m.d.sync += self.o_i2c_fifo_w_en.eq(1)
                    m.next = "START: CONTROL: STROBED W_EN"

            with m.State("START: CONTROL: STROBED W_EN"):
                m.d.sync += self.o_i2c_fifo_w_en.eq(0)
                m.next = "START: CONTROL: UNSTROBED W_EN"

            with m.State("START: CONTROL: UNSTROBED W_EN"):
                with m.If(self.i_i2c_o_busy & self.i_i2c_o_ack & self.i_i2c_fifo_w_rdy):
                    with m.If(self.i_row != 0):
                        byte = Cmd.SetPageAddress(0x00).to_byte() + self.i_row - 1
                        m.d.sync += self.o_i2c_fifo_w_data.eq(byte)
                        m.d.sync += self.o_i2c_fifo_w_en.eq(1)
                        m.next = "START: ROW: STROBED W_EN"
                    with m.Elif(self.i_col != 0):
                        self.start_col(m)
                        m.next = "START: COL LOWER: STROBED W_EN"
                    with m.Else():
                        m.d.sync += self.o_busy.eq(0)
                        m.next = "IDLE"
                with m.Elif(~self.i_i2c_o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

            with m.State("START: ROW: STROBED W_EN"):
                m.d.sync += self.o_i2c_fifo_w_en.eq(0)
                m.next = "START: ROW: UNSTROBED W_EN"

            with m.State("START: ROW: UNSTROBED W_EN"):
                with m.If(self.i_col != 0):
                    with m.If(
                        self.i_i2c_o_busy & self.i_i2c_o_ack & self.i_i2c_fifo_w_rdy
                    ):
                        self.start_col(m)
                        m.next = "START: COL LOWER: STROBED W_EN"
                    with m.Elif(~self.i_i2c_o_busy):
                        m.d.sync += self.o_busy.eq(0)
                        m.next = "IDLE"
                with m.Elif(~self.i_i2c_o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

            with m.State("START: COL LOWER: STROBED W_EN"):
                m.d.sync += self.o_i2c_fifo_w_en.eq(0)
                m.next = "START: COL LOWER: UNSTROBED W_EN"

            with m.State("START: COL LOWER: UNSTROBED W_EN"):
                with m.If(self.i_i2c_o_busy & self.i_i2c_o_ack & self.i_i2c_fifo_w_rdy):
                    byte = Cmd.SetHigherColumnAddress(0x00).to_byte() + (
                        (self.i_col - 1) >> 1
                    )
                    m.d.sync += self.o_i2c_fifo_w_data.eq(byte)
                    m.d.sync += self.o_i2c_fifo_w_en.eq(1)
                    m.next = "START: COL HIGHER: STROBED W_EN"
                with m.Elif(~self.i_i2c_o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

            with m.State("START: COL HIGHER: STROBED W_EN"):
                m.d.sync += self.o_i2c_fifo_w_en.eq(0)
                m.next = "START: COL HIGHER: UNSTROBED W_EN"

            with m.State("START: COL HIGHER: UNSTROBED W_EN"):
                with m.If(
                    ~self.i_i2c_o_busy & self.i_i2c_o_ack & self.i_i2c_fifo_w_rdy
                ):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"
                with m.Elif(~self.i_i2c_o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

        return m

    def start_col(self, m: Module):
        # For columns 1, 3, 5, 7, .., the column addresses are 0x00, 0x10, 0x20, ...
        # For columns 2, 4, 6, 8, .., the column addresses are 0x08, 0x18, 0x28, ...
        byte = Cmd.SetLowerColumnAddress(0x00).to_byte() + Mux(self.i_col[0], 0, 8)
        m.d.sync += self.o_i2c_fifo_w_data.eq(byte)
        m.d.sync += self.o_i2c_fifo_w_en.eq(1)
