from typing import Optional

from amaranth import Mux  # pyright: ignore[reportUnknownVariableType]
from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform

from i2c import RW, Transfer
from .sh1107 import Cmd, ControlByte

__all__ = ["Clser"]


class Clser(Elaboratable):
    addr: int

    i_stb: Signal

    i_i2c_fifo_w_rdy: Signal
    i_i2c_o_busy: Signal
    i_i2c_o_ack: Signal

    o_busy: Signal

    o_i2c_fifo_w_data: Transfer
    o_i2c_fifo_w_en: Signal
    o_i2c_i_stb: Signal

    current_page: Signal
    current_column: Signal

    def __init__(self, *, addr: int):
        self.addr = addr

        self.i_stb = Signal()

        self.i_i2c_fifo_w_rdy = Signal()
        self.i_i2c_o_busy = Signal()
        self.i_i2c_o_ack = Signal()

        self.o_busy = Signal()

        self.o_i2c_fifo_w_data = Transfer()
        self.o_i2c_fifo_w_en = Signal()
        self.o_i2c_i_stb = Signal()

        self.current_page = Signal(range(0x10))
        self.current_column = Signal(range(0x81))

    def connect_i2c_in(
        self, m: Module, *, o_fifo_w_rdy: Signal, o_busy: Signal, o_ack: Signal
    ):
        m.d.comb += [
            self.i_i2c_fifo_w_rdy.eq(o_fifo_w_rdy),
            self.i_i2c_o_busy.eq(o_busy),
            self.i_i2c_o_ack.eq(o_ack),
        ]

    def connect_i2c_out(
        self, m: Module, *, i_fifo_w_data: Signal, i_fifo_w_en: Signal, i_stb: Signal
    ):
        m.d.comb += [
            i_fifo_w_data.eq(self.o_i2c_fifo_w_data),
            i_fifo_w_en.eq(self.o_i2c_fifo_w_en),
            i_stb.eq(self.o_i2c_i_stb),
        ]

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.i_stb):
                    m.d.sync += self.o_busy.eq(1)
                    m.d.sync += self.current_page.eq(0)
                    m.d.sync += self.current_column.eq(0)
                    m.d.sync += self.o_i2c_fifo_w_data.kind.eq(Transfer.Kind.START)
                    m.d.sync += self.o_i2c_fifo_w_data.payload.start.addr.eq(self.addr)
                    m.d.sync += self.o_i2c_fifo_w_data.payload.start.rw.eq(RW.W)
                    m.d.sync += self.o_i2c_fifo_w_en.eq(1)
                    m.next = "START: ADDR: STROBED W_EN"

            with m.State("START: ADDR: STROBED W_EN"):
                m.d.sync += self.o_i2c_fifo_w_en.eq(0)
                m.d.sync += self.o_i2c_i_stb.eq(1)
                m.next = "START: ADDR: STROBED I_STB"

            with m.State("START: ADDR: STROBED I_STB"):
                m.d.sync += self.o_i2c_i_stb.eq(0)
                with m.If(self.i_i2c_fifo_w_rdy):
                    m.d.sync += self.o_i2c_fifo_w_data.kind.eq(Transfer.Kind.DATA)
                    m.d.sync += self.o_i2c_fifo_w_data.payload.data.eq(
                        ControlByte(False, "Command").to_byte()
                    )
                    m.d.sync += self.o_i2c_fifo_w_en.eq(1)
                    m.next = "START: CONTROL: STROBED W_EN"

            with m.State("START: CONTROL: STROBED W_EN"):
                m.d.sync += self.o_i2c_fifo_w_en.eq(0)
                with m.If(self.current_page == 0):
                    m.next = "START: CONTROL: UNSTROBED W_EN"
                with m.Else():
                    m.next = "START: COL HIGHER: UNSTROBED W_EN"

            with m.State("START: CONTROL: UNSTROBED W_EN"):
                with m.If(self.i_i2c_o_busy & self.i_i2c_o_ack & self.i_i2c_fifo_w_rdy):
                    byte = Cmd.SetLowerColumnAddress(0x0).to_byte()
                    m.d.sync += self.o_i2c_fifo_w_data.payload.data.eq(byte)
                    m.d.sync += self.o_i2c_fifo_w_en.eq(1)
                    m.next = "START: COL LOWER: STROBED W_EN"
                with m.Elif(~self.i_i2c_o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

            with m.State("START: COL LOWER: STROBED W_EN"):
                m.d.sync += self.o_i2c_fifo_w_en.eq(0)
                m.next = "START: COL LOWER: UNSTROBED W_EN"

            with m.State("START: COL LOWER: UNSTROBED W_EN"):
                with m.If(self.i_i2c_o_busy & self.i_i2c_o_ack & self.i_i2c_fifo_w_rdy):
                    byte = Cmd.SetHigherColumnAddress(0x00).to_byte()
                    m.d.sync += self.o_i2c_fifo_w_data.payload.data.eq(byte)
                    m.d.sync += self.o_i2c_fifo_w_en.eq(1)
                    m.next = "START: COL HIGHER: STROBED W_EN"
                with m.Elif(~self.i_i2c_o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

            with m.State("START: COL HIGHER: STROBED W_EN"):
                m.d.sync += self.o_i2c_fifo_w_en.eq(0)
                m.next = "START: COL HIGHER: UNSTROBED W_EN"

            with m.State("START: COL HIGHER: UNSTROBED W_EN"):
                with m.If(self.i_i2c_o_busy & self.i_i2c_o_ack & self.i_i2c_fifo_w_rdy):
                    byte = Cmd.SetPageAddress(0x00).to_byte() + self.current_page
                    m.d.sync += self.o_i2c_fifo_w_data.payload.data.eq(byte)
                    m.d.sync += self.o_i2c_fifo_w_en.eq(1)
                    m.next = "LOOP: PAGE: STROBED W_EN"
                with m.Elif(~self.i_i2c_o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

            with m.State("LOOP: PAGE: STROBED W_EN"):
                m.d.sync += self.o_i2c_fifo_w_en.eq(0)
                m.next = "LOOP: PAGE: UNSTROBED W_EN"

            with m.State("LOOP: PAGE: UNSTROBED W_EN"):
                with m.If(self.i_i2c_o_busy & self.i_i2c_o_ack & self.i_i2c_fifo_w_rdy):
                    m.d.sync += self.o_i2c_fifo_w_data.kind.eq(Transfer.Kind.START)
                    m.d.sync += self.o_i2c_fifo_w_data.payload.start.addr.eq(self.addr)
                    m.d.sync += self.o_i2c_fifo_w_data.payload.start.rw.eq(RW.W)
                    m.d.sync += self.o_i2c_fifo_w_en.eq(1)
                    m.next = "LOOP: ADDR: STROBED W_EN"
                with m.Elif(~self.i_i2c_o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

            with m.State("LOOP: ADDR: STROBED W_EN"):
                m.d.sync += self.o_i2c_fifo_w_en.eq(0)
                m.next = "LOOP: ADDR: UNSTROBED W_EN"

            with m.State("LOOP: ADDR: UNSTROBED W_EN"):
                with m.If(self.i_i2c_fifo_w_rdy):
                    m.d.sync += self.o_i2c_fifo_w_data.kind.eq(Transfer.Kind.DATA)
                    m.d.sync += self.o_i2c_fifo_w_data.payload.data.eq(
                        ControlByte(False, "Data").to_byte()
                    )
                    m.d.sync += self.o_i2c_fifo_w_en.eq(1)
                    m.next = "LOOP: CONTROL: STROBED W_EN"

            with m.State("LOOP: CONTROL: STROBED W_EN"):
                m.d.sync += self.o_i2c_fifo_w_en.eq(0)
                m.next = "LOOP: CONTROL: UNSTROBED W_EN"

            with m.State("LOOP: CONTROL: UNSTROBED W_EN"):
                with m.If(self.i_i2c_o_busy & self.i_i2c_o_ack & self.i_i2c_fifo_w_rdy):
                    with m.If(self.current_column != 0x80):
                        m.d.sync += self.o_i2c_fifo_w_data.payload.data.eq(0x00)
                        m.d.sync += self.o_i2c_fifo_w_en.eq(1)
                        m.d.sync += self.current_column.eq(self.current_column + 1)
                        m.next = "LOOP: CONTROL: STROBED W_EN"
                    with m.Elif(self.current_page != 0x0F):
                        m.d.sync += self.current_column.eq(0)
                        m.d.sync += self.current_page.eq(self.current_page + 1)

                        m.d.sync += self.o_i2c_fifo_w_data.kind.eq(Transfer.Kind.START)
                        m.d.sync += self.o_i2c_fifo_w_data.payload.start.addr.eq(
                            self.addr
                        )
                        m.d.sync += self.o_i2c_fifo_w_data.payload.start.rw.eq(RW.W)
                        m.d.sync += self.o_i2c_fifo_w_en.eq(1)
                        m.next = "LOOP: NEXT PAGE: ADDR: STROBED W_EN"
                    with m.Else():
                        m.d.sync += self.o_busy.eq(0)
                        m.next = "IDLE"
                with m.Elif(~self.i_i2c_o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

            with m.State("LOOP: NEXT PAGE: ADDR: STROBED W_EN"):
                m.d.sync += self.o_i2c_fifo_w_en.eq(0)
                m.next = "START: ADDR: STROBED I_STB"

        return m

    def start_col(self, m: Module):
        # For columns 1, 3, 5, 7, .., the column addresses are 0x00, 0x10, 0x20, ...
        # For columns 2, 4, 6, 8, .., the column addresses are 0x08, 0x18, 0x28, ...
        byte = Cmd.SetLowerColumnAddress(0x00).to_byte() + Mux(self.i_col[0], 0, 8)
        m.d.sync += self.o_i2c_fifo_w_data.eq(byte)
        m.d.sync += self.o_i2c_fifo_w_en.eq(1)
