from typing import Optional, cast

from amaranth import Cat, Module, Signal
from amaranth.build import Platform
from amaranth.lib.wiring import Component, In, Out

from ... import rom
from ..i2c import RW, I2CBus, Transfer
from .rom_bus import ROMBus

__all__ = ["ROMWriter"]


class ROMWriter(Component):
    addr: int

    index: Out(range(rom.SEQ_COUNT))
    stb: Out(1)
    i2c_bus: Out(I2CBus)
    rom_bus: Out(ROMBus(rom.ROM_ABITS, 8))

    busy: In(1)

    offset: Signal
    remain: Signal

    def __init__(self, *, addr: int):
        super().__init__()
        self.addr = addr

        self.offset = Signal(range(rom.ROM_LENGTH))
        self.remain = Signal(range(rom.ROM_LENGTH))

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        transfer = Transfer(self.i2c_bus.in_fifo_w_data)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.stb):
                    m.d.sync += [
                        self.rom_bus.addr.eq(self.index * 4),
                        self.busy.eq(1),
                    ]
                    m.next = "START: ADDRESSED OFFSET[0]"

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
                    self.i2c_bus.in_fifo_w_en.eq(1),
                ]
                m.next = "ADDRESS PERIPHERAL: LATCHED W_EN"

            with m.State("ADDRESS PERIPHERAL: LATCHED W_EN"):
                m.d.sync += [
                    self.i2c_bus.in_fifo_w_en.eq(0),
                    self.i2c_bus.stb.eq(1),
                ]
                m.next = "LOOP HEAD: SEQ BREAK OR WAIT I2C"

            with m.State("LOOP HEAD: SEQ BREAK OR WAIT I2C"):
                m.d.sync += self.i2c_bus.stb.eq(0)
                with m.If(self.remain == 0):
                    m.d.sync += [
                        self.rom_bus.addr.eq(self.offset + 1),
                        self.offset.eq(self.offset + 1),
                    ]
                    m.next = "SEQ BREAK: ADDRESSED NEXTLEN[1], NEXTLEN[0] AVAILABLE"
                with m.Elif(self.i2c_bus.in_fifo_w_rdy):
                    m.d.sync += [
                        self.offset.eq(self.offset + 1),
                        self.remain.eq(self.remain - 1),
                        transfer.kind.eq(Transfer.Kind.DATA),
                        transfer.payload.data.eq(self.rom_bus.data),
                        self.i2c_bus.in_fifo_w_en.eq(1),
                    ]

                    # Prepare next read, whether it's data or NEXTLEN[0].
                    m.d.sync += self.rom_bus.addr.eq(self.offset + 1)
                    m.next = "SEND: LATCHED W_EN"

            with m.State("SEND: LATCHED W_EN"):
                m.d.sync += self.i2c_bus.in_fifo_w_en.eq(0)
                m.next = "SEND: WAIT FOR I2C"

            with m.State("SEND: WAIT FOR I2C"):
                with m.If(
                    self.i2c_bus.busy & self.i2c_bus.ack & self.i2c_bus.in_fifo_w_rdy
                ):
                    m.next = "LOOP HEAD: SEQ BREAK OR WAIT I2C"
                with m.Elif(~self.i2c_bus.busy):
                    # Failed.  Stop.
                    m.d.sync += self.busy.eq(0)
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
                        self.i2c_bus.in_fifo_w_en.eq(1),
                    ]
                    m.next = "SEQ BREAK: LATCHED W_EN"

            with m.State("SEQ BREAK: LATCHED W_EN"):
                m.d.sync += self.i2c_bus.in_fifo_w_en.eq(0)
                m.next = "LOOP HEAD: SEQ BREAK OR WAIT I2C"

            with m.State("FIN: WAIT I2C DONE"):
                with m.If(
                    ~self.i2c_bus.busy & self.i2c_bus.ack & self.i2c_bus.in_fifo_w_rdy
                ):
                    m.d.sync += self.busy.eq(0)
                    m.next = "IDLE"
                with m.Elif(~self.i2c_bus.busy):
                    m.d.sync += self.busy.eq(0)
                    m.next = "IDLE"

        return m
