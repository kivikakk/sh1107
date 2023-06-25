from typing import Optional

from amaranth import Elaboratable, Module, Mux, Signal
from amaranth.build import Platform

from ..i2c import RW, I2CBus, Transfer
from .sh1107 import Cmd, ControlByte

__all__ = ["Locator"]


class Locator(Elaboratable):
    addr: int

    i_adjust: Signal
    i_row: Signal
    i_col: Signal
    i_stb: Signal

    o_busy: Signal

    i2c_bus: I2CBus
    adjusted_row: Signal

    def __init__(self, *, addr: int):
        self.addr = addr

        self.i_adjust = Signal(range(16))
        self.i_row = Signal(range(17))
        self.i_col = Signal(range(17))
        self.i_stb = Signal()

        self.o_busy = Signal()

        self.i2c_bus = I2CBus()
        self.adjusted_row = Signal(range(16))

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.d.comb += self.adjusted_row.eq(self.i_row - 1 + self.i_adjust)

        transfer = Transfer(self.i2c_bus.i_in_fifo_w_data)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.i_stb):
                    m.d.sync += [
                        self.o_busy.eq(1),
                        transfer.kind.eq(Transfer.Kind.START),
                        transfer.payload.start.addr.eq(self.addr),
                        transfer.payload.start.rw.eq(RW.W),
                        self.i2c_bus.i_in_fifo_w_en.eq(1),
                    ]
                    m.next = "START: ADDR: STROBED W_EN"

            with m.State("START: ADDR: STROBED W_EN"):
                m.d.sync += [
                    self.i2c_bus.i_in_fifo_w_en.eq(0),
                    self.i2c_bus.i_stb.eq(1),
                ]
                m.next = "START: ADDR: STROBED I_STB"

            with m.State("START: ADDR: STROBED I_STB"):
                m.d.sync += self.i2c_bus.i_stb.eq(0)
                with m.If(self.i2c_bus.o_in_fifo_w_rdy):
                    m.d.sync += [
                        transfer.kind.eq(Transfer.Kind.DATA),
                        transfer.payload.data.eq(
                            ControlByte(False, "Command").to_byte()
                        ),
                        self.i2c_bus.i_in_fifo_w_en.eq(1),
                    ]
                    m.next = "START: CONTROL: STROBED W_EN"

            with m.State("START: CONTROL: STROBED W_EN"):
                m.d.sync += self.i2c_bus.i_in_fifo_w_en.eq(0)
                m.next = "START: CONTROL: UNSTROBED W_EN"

            with m.State("START: CONTROL: UNSTROBED W_EN"):
                with m.If(
                    self.i2c_bus.o_busy
                    & self.i2c_bus.o_ack
                    & self.i2c_bus.o_in_fifo_w_rdy
                ):
                    with m.If(self.i_col != 0):
                        byte = Cmd.SetPageAddress(0x00).to_byte() + 16 - self.i_col
                        m.d.sync += [
                            transfer.payload.data.eq(byte),
                            self.i2c_bus.i_in_fifo_w_en.eq(1),
                        ]
                        m.next = "START: PAGE: STROBED W_EN"
                    with m.Elif(self.i_row != 0):
                        self.startRow(m)
                        m.next = "START: COL LOWER: STROBED W_EN"
                    with m.Else():
                        m.d.sync += self.o_busy.eq(0)
                        m.next = "IDLE"
                with m.Elif(~self.i2c_bus.o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

            with m.State("START: PAGE: STROBED W_EN"):
                m.d.sync += self.i2c_bus.i_in_fifo_w_en.eq(0)
                m.next = "START: PAGE: UNSTROBED W_EN"

            with m.State("START: PAGE: UNSTROBED W_EN"):
                with m.If(self.i_row != 0):
                    with m.If(
                        self.i2c_bus.o_busy
                        & self.i2c_bus.o_ack
                        & self.i2c_bus.o_in_fifo_w_rdy
                    ):
                        self.startRow(m)
                        m.next = "START: COL LOWER: STROBED W_EN"
                    with m.Elif(~self.i2c_bus.o_busy):
                        m.d.sync += self.o_busy.eq(0)
                        m.next = "IDLE"
                with m.Elif(~self.i2c_bus.o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

            with m.State("START: COL LOWER: STROBED W_EN"):
                m.d.sync += self.i2c_bus.i_in_fifo_w_en.eq(0)
                m.next = "START: COL LOWER: UNSTROBED W_EN"

            with m.State("START: COL LOWER: UNSTROBED W_EN"):
                with m.If(
                    self.i2c_bus.o_busy
                    & self.i2c_bus.o_ack
                    & self.i2c_bus.o_in_fifo_w_rdy
                ):
                    byte = Cmd.SetHigherColumnAddress(0x00).to_byte() + (
                        self.adjusted_row >> 1
                    )
                    m.d.sync += [
                        transfer.payload.data.eq(byte),
                        self.i2c_bus.i_in_fifo_w_en.eq(1),
                    ]
                    m.next = "START: COL HIGHER: STROBED W_EN"
                with m.Elif(~self.i2c_bus.o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

            with m.State("START: COL HIGHER: STROBED W_EN"):
                m.d.sync += self.i2c_bus.i_in_fifo_w_en.eq(0)
                m.next = "START: COL HIGHER: UNSTROBED W_EN"

            with m.State("START: COL HIGHER: UNSTROBED W_EN"):
                with m.If(
                    ~self.i2c_bus.o_busy
                    & self.i2c_bus.o_ack
                    & self.i2c_bus.o_in_fifo_w_rdy
                ):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"
                with m.Elif(~self.i2c_bus.o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

        return m

    def startRow(self, m: Module):
        # For (adjusted) rows 0, 2, 4, 6, .., the column addresses are 0x00, 0x10, 0x20, ...
        # For (adjusted) rows 1, 3, 5, 7, .., the column addresses are 0x08, 0x18, 0x28, ...
        byte = Cmd.SetLowerColumnAddress(0x00).to_byte() + Mux(
            self.adjusted_row[0], 8, 0
        )
        transfer = Transfer(self.i2c_bus.i_in_fifo_w_data)
        m.d.sync += [
            transfer.payload.data.eq(byte),
            self.i2c_bus.i_in_fifo_w_en.eq(1),
        ]
