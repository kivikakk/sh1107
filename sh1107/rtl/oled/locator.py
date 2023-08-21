from amaranth import Elaboratable, Module, Mux, Signal
from amaranth.lib.wiring import Component, In, Out

from ...platform import Platform
from ...proto import Cmd, ControlByte
from ..i2c import RW, I2CBus, Transfer

__all__ = ["Locator"]


class Locator(Component):
    _addr: int

    adjust: Out(range(16))
    row: Out(range(17))
    col: Out(range(17))
    stb: Out(1)
    i2c_bus: Out(I2CBus)

    busy: In(1)

    _adjusted_row: Signal

    def __init__(self, *, addr: int):
        super().__init__()
        self._addr = addr

        self._adjusted_row = Signal(range(16))

    def elaborate(self, platform: Platform) -> Elaboratable:
        m = Module()

        m.d.comb += self._adjusted_row.eq(self.row - 1 + self.adjust)

        transfer = Transfer(self.i2c_bus.in_fifo_w_data)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.stb):
                    m.d.sync += [
                        self.busy.eq(1),
                        transfer.kind.eq(Transfer.Kind.START),
                        transfer.payload.start.addr.eq(self._addr),
                        transfer.payload.start.rw.eq(RW.W),
                        self.i2c_bus.in_fifo_w_en.eq(1),
                    ]
                    m.next = "START: ADDR: STROBED W_EN"

            with m.State("START: ADDR: STROBED W_EN"):
                m.d.sync += [
                    self.i2c_bus.in_fifo_w_en.eq(0),
                    self.i2c_bus.stb.eq(1),
                ]
                m.next = "START: ADDR: STROBED STB"

            with m.State("START: ADDR: STROBED STB"):
                m.d.sync += self.i2c_bus.stb.eq(0)
                with m.If(self.i2c_bus.in_fifo_w_rdy):
                    m.d.sync += [
                        transfer.kind.eq(Transfer.Kind.DATA),
                        transfer.payload.data.eq(
                            ControlByte(False, "Command").to_byte()
                        ),
                        self.i2c_bus.in_fifo_w_en.eq(1),
                    ]
                    m.next = "START: CONTROL: STROBED W_EN"

            with m.State("START: CONTROL: STROBED W_EN"):
                m.d.sync += self.i2c_bus.in_fifo_w_en.eq(0)
                m.next = "START: CONTROL: UNSTROBED W_EN"

            with m.State("START: CONTROL: UNSTROBED W_EN"):
                with m.If(
                    self.i2c_bus.busy & self.i2c_bus.ack & self.i2c_bus.in_fifo_w_rdy
                ):
                    with m.If(self.col != 0):
                        byte = Cmd.SetPageAddress(0x00).to_byte() + 16 - self.col
                        m.d.sync += [
                            transfer.payload.data.eq(byte),
                            self.i2c_bus.in_fifo_w_en.eq(1),
                        ]
                        m.next = "START: PAGE: STROBED W_EN"
                    with m.Elif(self.row != 0):
                        self.start_row(m)
                        m.next = "START: COL LOWER: STROBED W_EN"
                    with m.Else():
                        m.d.sync += self.busy.eq(0)
                        m.next = "IDLE"
                with m.Elif(~self.i2c_bus.busy):
                    m.d.sync += self.busy.eq(0)
                    m.next = "IDLE"

            with m.State("START: PAGE: STROBED W_EN"):
                m.d.sync += self.i2c_bus.in_fifo_w_en.eq(0)
                m.next = "START: PAGE: UNSTROBED W_EN"

            with m.State("START: PAGE: UNSTROBED W_EN"):
                with m.If(self.row != 0):
                    with m.If(
                        self.i2c_bus.busy
                        & self.i2c_bus.ack
                        & self.i2c_bus.in_fifo_w_rdy
                    ):
                        self.start_row(m)
                        m.next = "START: COL LOWER: STROBED W_EN"
                    with m.Elif(~self.i2c_bus.busy):
                        m.d.sync += self.busy.eq(0)
                        m.next = "IDLE"
                with m.Elif(~self.i2c_bus.busy):
                    m.d.sync += self.busy.eq(0)
                    m.next = "IDLE"

            with m.State("START: COL LOWER: STROBED W_EN"):
                m.d.sync += self.i2c_bus.in_fifo_w_en.eq(0)
                m.next = "START: COL LOWER: UNSTROBED W_EN"

            with m.State("START: COL LOWER: UNSTROBED W_EN"):
                with m.If(
                    self.i2c_bus.busy & self.i2c_bus.ack & self.i2c_bus.in_fifo_w_rdy
                ):
                    byte = Cmd.SetHigherColumnAddress(0x00).to_byte() + (
                        self._adjusted_row >> 1
                    )
                    m.d.sync += [
                        transfer.payload.data.eq(byte),
                        self.i2c_bus.in_fifo_w_en.eq(1),
                    ]
                    m.next = "START: COL HIGHER: STROBED W_EN"
                with m.Elif(~self.i2c_bus.busy):
                    m.d.sync += self.busy.eq(0)
                    m.next = "IDLE"

            with m.State("START: COL HIGHER: STROBED W_EN"):
                m.d.sync += self.i2c_bus.in_fifo_w_en.eq(0)
                m.next = "START: COL HIGHER: UNSTROBED W_EN"

            with m.State("START: COL HIGHER: UNSTROBED W_EN"):
                with m.If(
                    ~self.i2c_bus.busy & self.i2c_bus.ack & self.i2c_bus.in_fifo_w_rdy
                ):
                    m.d.sync += self.busy.eq(0)
                    m.next = "IDLE"
                with m.Elif(~self.i2c_bus.busy):
                    m.d.sync += self.busy.eq(0)
                    m.next = "IDLE"

        return m

    def start_row(self, m: Module):
        # For (adjusted) rows 0, 2, 4, 6, .., the column addresses are 0x00, 0x10, 0x20, ...
        # For (adjusted) rows 1, 3, 5, 7, .., the column addresses are 0x08, 0x18, 0x28, ...
        byte = Cmd.SetLowerColumnAddress(0x00).to_byte() + Mux(
            self._adjusted_row[0], 8, 0
        )
        transfer = Transfer(self.i2c_bus.in_fifo_w_data)
        m.d.sync += [
            transfer.payload.data.eq(byte),
            self.i2c_bus.in_fifo_w_en.eq(1),
        ]
