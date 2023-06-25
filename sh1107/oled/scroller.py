from typing import Optional, cast

from amaranth import Cat, Elaboratable, Module, Mux, Signal
from amaranth.build import Platform

from ..i2c import RW, I2CBus, Transfer
from ..oled import rom

__all__ = ["Scroller"]


class Scroller(Elaboratable):
    addr: int

    i_stb: Signal
    i_rst: Signal
    o_busy: Signal
    o_adjusted: Signal

    i2c_bus: I2CBus
    rom_bus: rom.ROMBus

    offset: Signal
    remain: Signal
    written: Signal

    def __init__(self, *, rom_bus: rom.ROMBus, addr: int):
        self.addr = addr

        self.i_stb = Signal()
        self.i_rst = Signal()
        self.o_busy = Signal()
        self.o_adjusted = Signal(range(16))

        self.i2c_bus = I2CBus()
        self.rom_bus = rom_bus.clone()

        self.offset = Signal(range(rom.ROM_LENGTH))
        self.remain = Signal(range(rom.ROM_LENGTH))
        self.written = Signal(range(rom.ROM_LENGTH))

    def elaborate(self, platform: Optional[Platform]) -> Module:
        # XXX: This is an exact copy of ROMWriter with some bits added.
        m = Module()

        transfer = Transfer(self.i2c_bus.i_in_fifo_w_data)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.i_stb):
                    m.d.sync += [
                        self.rom_bus.addr.eq(rom.OFFSET_SCROLL * 4),
                        self.o_busy.eq(1),
                        self.written.eq(0),
                    ]
                    m.next = "START: ADDRESSED OFFSET[0]"
                with m.If(self.i_rst):
                    m.d.sync += self.o_adjusted.eq(0)

            with m.State("START: ADDRESSED OFFSET[0]"):
                m.d.sync += self.rom_bus.addr.eq(self.rom_bus.addr + 1)
                m.next = "START: ADDRESSED OFFSET[1], OFFSET[0] AVAILABLE"

            with m.State("START: ADDRESSED OFFSET[1], OFFSET[0] AVAILABLE"):
                m.d.sync += [
                    self.rom_bus.addr.eq(self.rom_bus.addr + 1),
                    self.offset.eq(self.rom_bus.data),
                ]
                m.next = "START: ADDRESSED LEN[0], OFFSET[1] AVAILABLE"

            with m.State("START: ADDRESSED LEN[0], OFFSET[1] AVAILABLE"):
                m.d.sync += [
                    self.rom_bus.addr.eq(self.rom_bus.addr + 1),
                    self.offset.eq(self.offset | self.rom_bus.data.shift_left(8)),
                ]
                m.next = "START: ADDRESSED LEN[1], LEN[0] AVAILABLE"

            with m.State("START: ADDRESSED LEN[1], LEN[0] AVAILABLE"):
                m.d.sync += [
                    self.remain.eq(self.rom_bus.data),
                    self.rom_bus.addr.eq(self.offset),
                ]
                m.next = "START: ADDRESSED *OFFSET, LEN[1] AVAILABLE"

            with m.State("START: ADDRESSED *OFFSET, LEN[1] AVAILABLE"):
                m.d.sync += [
                    self.remain.eq(self.remain | self.rom_bus.data.shift_left(8)),
                    transfer.kind.eq(Transfer.Kind.START),
                    transfer.payload.start.addr.eq(self.addr),
                    transfer.payload.start.rw.eq(RW.W),
                    self.i2c_bus.i_in_fifo_w_en.eq(1),
                ]
                m.next = "ADDRESS PERIPHERAL: LATCHED W_EN"

            with m.State("ADDRESS PERIPHERAL: LATCHED W_EN"):
                m.d.sync += [
                    self.i2c_bus.i_in_fifo_w_en.eq(0),
                    self.i2c_bus.i_stb.eq(1),
                ]
                m.next = "LOOP HEAD: SEQ BREAK OR WAIT I2C"

            with m.State("LOOP HEAD: SEQ BREAK OR WAIT I2C"):
                m.d.sync += self.i2c_bus.i_stb.eq(0)
                with m.If(self.remain == 0):
                    m.d.sync += [
                        self.rom_bus.addr.eq(self.offset + 1),
                        self.offset.eq(self.offset + 1),
                    ]
                    m.next = "SEQ BREAK: ADDRESSED NEXTLEN[1], NEXTLEN[0] AVAILABLE"
                with m.Elif(self.i2c_bus.o_in_fifo_w_rdy):
                    m.d.sync += [
                        self.offset.eq(self.offset + 1),
                        self.remain.eq(self.remain - 1),
                        transfer.kind.eq(Transfer.Kind.DATA),
                        self.i2c_bus.i_in_fifo_w_en.eq(1),
                        self.written.eq(self.written + 1),
                    ]

                    with m.If(
                        self.written == rom.SCROLL_OFFSETS["InitialHigherColumnAddress"]
                    ):
                        m.d.sync += transfer.payload.data.eq(
                            self.rom_bus.data + (self.o_adjusted >> 1)
                        )
                    for i in range(8):
                        with m.Elif(
                            self.written == rom.SCROLL_OFFSETS[f"LowerColumnAddress{i}"]
                        ):
                            m.d.sync += transfer.payload.data.eq(
                                self.rom_bus.data + (self.o_adjusted[0] << 3)
                            )
                    with m.Elif(
                        self.written == rom.SCROLL_OFFSETS["DisplayStartLine"] + 1
                    ):
                        m.d.sync += transfer.payload.data.eq(
                            Mux(self.o_adjusted == 15, 0, 8 + self.o_adjusted * 8)
                        )
                    with m.Else():
                        m.d.sync += transfer.payload.data.eq(self.rom_bus.data)

                    # Prepare next read, whether it's data or NEXTLEN[0].
                    m.d.sync += self.rom_bus.addr.eq(self.offset + 1)
                    m.next = "SEND: LATCHED W_EN"

            with m.State("SEND: LATCHED W_EN"):
                m.d.sync += self.i2c_bus.i_in_fifo_w_en.eq(0)
                m.next = "SEND: WAIT FOR I2C"

            with m.State("SEND: WAIT FOR I2C"):
                with m.If(
                    self.i2c_bus.o_busy
                    & self.i2c_bus.o_ack
                    & self.i2c_bus.o_in_fifo_w_rdy
                ):
                    m.next = "LOOP HEAD: SEQ BREAK OR WAIT I2C"
                with m.Elif(~self.i2c_bus.o_busy):
                    # Failed.  Stop.
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

            with m.State("SEQ BREAK: ADDRESSED NEXTLEN[1], NEXTLEN[0] AVAILABLE"):
                m.d.sync += [
                    self.remain.eq(self.rom_bus.data),
                    self.rom_bus.addr.eq(self.offset + 1),
                    self.offset.eq(self.offset + 1),
                ]
                m.next = "SEQ BREAK: ADDRESSED FOLLOWING, NEXTLEN[1] AVAILABLE"

            with m.State("SEQ BREAK: ADDRESSED FOLLOWING, NEXTLEN[1] AVAILABLE"):
                remain = self.remain | cast(Cat, self.rom_bus.data.shift_left(8))
                with m.If(remain == 0):
                    m.next = "FIN: WAIT I2C DONE"
                with m.Else():
                    m.d.sync += [
                        self.remain.eq(remain),
                        transfer.kind.eq(Transfer.Kind.START),
                        transfer.payload.start.addr.eq(self.addr),
                        transfer.payload.start.rw.eq(RW.W),
                        self.i2c_bus.i_in_fifo_w_en.eq(1),
                    ]
                    m.next = "SEQ BREAK: LATCHED W_EN"

            with m.State("SEQ BREAK: LATCHED W_EN"):
                m.d.sync += self.i2c_bus.i_in_fifo_w_en.eq(0)
                m.next = "LOOP HEAD: SEQ BREAK OR WAIT I2C"

            with m.State("FIN: WAIT I2C DONE"):
                with m.If(
                    ~self.i2c_bus.o_busy
                    & self.i2c_bus.o_ack
                    & self.i2c_bus.o_in_fifo_w_rdy
                ):
                    m.d.sync += [
                        self.o_adjusted.eq(self.o_adjusted + 1),
                        self.o_busy.eq(0),
                    ]
                    m.next = "IDLE"
                with m.Elif(~self.i2c_bus.o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

        return m
