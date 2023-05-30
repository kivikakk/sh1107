from typing import Optional

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform

from i2c import RW, I2CBus, Transfer
from .sh1107 import Cmd, ControlByte

__all__ = ["Clser"]


class Clser(Elaboratable):
    addr: int

    i_stb: Signal

    o_busy: Signal

    i2c_bus: I2CBus

    current_page: Signal
    current_column: Signal

    def __init__(self, *, addr: int):
        self.addr = addr

        self.i_stb = Signal()

        self.o_busy = Signal()

        self.i2c_bus = I2CBus()

        self.current_page = Signal(range(0x10))
        self.current_column = Signal(range(0x81))

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        transfer = Transfer(self.i2c_bus.i_in_fifo_w_data)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.i_stb):
                    m.d.sync += [
                        self.o_busy.eq(1),
                        self.current_page.eq(0),
                        self.current_column.eq(0),
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
                with m.If(self.current_page == 0):
                    m.next = "START: CONTROL: UNSTROBED W_EN"
                with m.Else():
                    m.next = "START: COL HIGHER: UNSTROBED W_EN"

            with m.State("START: CONTROL: UNSTROBED W_EN"):
                with m.If(
                    self.i2c_bus.o_busy
                    & self.i2c_bus.o_ack
                    & self.i2c_bus.o_in_fifo_w_rdy
                ):
                    byte = Cmd.SetLowerColumnAddress(0x0).to_byte()
                    m.d.sync += [
                        transfer.payload.data.eq(byte),
                        self.i2c_bus.i_in_fifo_w_en.eq(1),
                    ]
                    m.next = "START: COL LOWER: STROBED W_EN"
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
                    byte = Cmd.SetHigherColumnAddress(0x00).to_byte()
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
                    self.i2c_bus.o_busy
                    & self.i2c_bus.o_ack
                    & self.i2c_bus.o_in_fifo_w_rdy
                ):
                    byte = Cmd.SetPageAddress(0x00).to_byte() + self.current_page
                    m.d.sync += [
                        transfer.payload.data.eq(byte),
                        self.i2c_bus.i_in_fifo_w_en.eq(1),
                    ]
                    m.next = "LOOP: PAGE: STROBED W_EN"
                with m.Elif(~self.i2c_bus.o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

            with m.State("LOOP: PAGE: STROBED W_EN"):
                m.d.sync += self.i2c_bus.i_in_fifo_w_en.eq(0)
                m.next = "LOOP: PAGE: UNSTROBED W_EN"

            with m.State("LOOP: PAGE: UNSTROBED W_EN"):
                with m.If(
                    self.i2c_bus.o_busy
                    & self.i2c_bus.o_ack
                    & self.i2c_bus.o_in_fifo_w_rdy
                ):
                    m.d.sync += [
                        transfer.kind.eq(Transfer.Kind.START),
                        transfer.payload.start.addr.eq(self.addr),
                        transfer.payload.start.rw.eq(RW.W),
                        self.i2c_bus.i_in_fifo_w_en.eq(1),
                    ]
                    m.next = "LOOP: ADDR: STROBED W_EN"
                with m.Elif(~self.i2c_bus.o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

            with m.State("LOOP: ADDR: STROBED W_EN"):
                m.d.sync += self.i2c_bus.i_in_fifo_w_en.eq(0)
                m.next = "LOOP: ADDR: UNSTROBED W_EN"

            with m.State("LOOP: ADDR: UNSTROBED W_EN"):
                with m.If(self.i2c_bus.o_in_fifo_w_rdy):
                    m.d.sync += [
                        transfer.kind.eq(Transfer.Kind.DATA),
                        transfer.payload.data.eq(ControlByte(False, "Data").to_byte()),
                    ]
                    m.d.sync += self.i2c_bus.i_in_fifo_w_en.eq(1)
                    m.next = "LOOP: CONTROL: STROBED W_EN"

            with m.State("LOOP: CONTROL: STROBED W_EN"):
                m.d.sync += self.i2c_bus.i_in_fifo_w_en.eq(0)
                m.next = "LOOP: CONTROL: UNSTROBED W_EN"

            with m.State("LOOP: CONTROL: UNSTROBED W_EN"):
                with m.If(
                    self.i2c_bus.o_busy
                    & self.i2c_bus.o_ack
                    & self.i2c_bus.o_in_fifo_w_rdy
                ):
                    with m.If(self.current_column != 0x80):
                        m.d.sync += [
                            transfer.payload.data.eq(0x00),
                            self.i2c_bus.i_in_fifo_w_en.eq(1),
                            self.current_column.eq(self.current_column + 1),
                        ]
                        m.next = "LOOP: CONTROL: STROBED W_EN"
                    with m.Elif(self.current_page != 0x0F):
                        m.d.sync += [
                            self.current_column.eq(0),
                            self.current_page.eq(self.current_page + 1),
                            transfer.kind.eq(Transfer.Kind.START),
                            transfer.payload.start.addr.eq(self.addr),
                            transfer.payload.start.rw.eq(RW.W),
                            self.i2c_bus.i_in_fifo_w_en.eq(1),
                        ]
                        m.next = "LOOP: NEXT PAGE: ADDR: STROBED W_EN"
                    with m.Else():
                        m.d.sync += self.o_busy.eq(0)
                        m.next = "IDLE"
                with m.Elif(~self.i2c_bus.o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

            with m.State("LOOP: NEXT PAGE: ADDR: STROBED W_EN"):
                m.d.sync += self.i2c_bus.i_in_fifo_w_en.eq(0)
                m.next = "START: ADDR: STROBED I_STB"

        return m
