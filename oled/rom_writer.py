from typing import Optional, cast

from amaranth import Cat, Elaboratable, Memory, Module, Signal
from amaranth.build import Platform
from amaranth.hdl.mem import ReadPort

from i2c import RW, I2CBus, Transfer
from oled import rom

__all__ = ["ROMWriter"]


class ROMWriter(Elaboratable):
    addr: int

    i_index: Signal
    i_stb: Signal

    o_busy: Signal

    i2c_bus: I2CBus

    rom_rd: ReadPort
    offset: Signal
    remain: Signal

    def __init__(self, *, addr: int):
        self.addr = addr

        self.i_index = Signal(range(rom.SEQ_COUNT))
        self.i_stb = Signal()

        self.o_busy = Signal()

        self.i2c_bus = I2CBus()

        self.rom_rd = Memory(
            width=8,
            depth=len(rom.ROM),
            init=rom.ROM,
        ).read_port(transparent=False)
        self.offset = Signal(range(len(rom.ROM)))
        self.remain = Signal(range(len(rom.ROM)))

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.rom_rd = self.rom_rd

        transfer = Transfer(self.i2c_bus.i_in_fifo_w_data)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.i_stb):
                    m.d.sync += self.rom_rd.addr.eq(self.i_index * 4)
                    m.d.sync += self.o_busy.eq(1)
                    m.next = "START: ADDRESSED OFFSET[0]"

            with m.State("START: ADDRESSED OFFSET[0]"):
                m.d.sync += self.rom_rd.addr.eq(self.rom_rd.addr + 1)
                m.next = "START: ADDRESSED OFFSET[1], OFFSET[0] AVAILABLE"

            with m.State("START: ADDRESSED OFFSET[1], OFFSET[0] AVAILABLE"):
                m.d.sync += self.rom_rd.addr.eq(self.rom_rd.addr + 1)
                m.d.sync += self.offset.eq(self.rom_rd.data)
                m.next = "START: ADDRESSED LEN[0], OFFSET[1] AVAILABLE"

            with m.State("START: ADDRESSED LEN[0], OFFSET[1] AVAILABLE"):
                m.d.sync += self.rom_rd.addr.eq(self.rom_rd.addr + 1)
                m.d.sync += self.offset.eq(self.offset | self.rom_rd.data.shift_left(8))
                m.next = "START: ADDRESSED LEN[1], LEN[0] AVAILABLE"

            with m.State("START: ADDRESSED LEN[1], LEN[0] AVAILABLE"):
                m.d.sync += self.remain.eq(self.rom_rd.data)
                m.d.sync += self.rom_rd.addr.eq(self.offset)
                m.next = "START: ADDRESSED *OFFSET, LEN[1] AVAILABLE"

            with m.State("START: ADDRESSED *OFFSET, LEN[1] AVAILABLE"):
                m.d.sync += self.remain.eq(self.remain | self.rom_rd.data.shift_left(8))
                m.d.sync += transfer.kind.eq(Transfer.Kind.START)
                m.d.sync += transfer.payload.start.addr.eq(self.addr)
                m.d.sync += transfer.payload.start.rw.eq(RW.W)
                m.d.sync += self.i2c_bus.i_in_fifo_w_en.eq(1)
                m.next = "ADDRESS PERIPHERAL: LATCHED W_EN"

            with m.State("ADDRESS PERIPHERAL: LATCHED W_EN"):
                m.d.sync += self.i2c_bus.i_in_fifo_w_en.eq(0)
                m.d.sync += self.i2c_bus.i_stb.eq(1)
                m.next = "LOOP HEAD: SEQ BREAK OR WAIT I2C"

            with m.State("LOOP HEAD: SEQ BREAK OR WAIT I2C"):
                m.d.sync += self.i2c_bus.i_stb.eq(0)
                with m.If(self.remain == 0):
                    m.d.sync += self.rom_rd.addr.eq(self.offset + 1)
                    m.d.sync += self.offset.eq(self.offset + 1)
                    m.next = "SEQ BREAK: ADDRESSED NEXTLEN[1], NEXTLEN[0] AVAILABLE"
                with m.Elif(self.i2c_bus.o_in_fifo_w_rdy):
                    m.d.sync += self.offset.eq(self.offset + 1)
                    m.d.sync += self.remain.eq(self.remain - 1)
                    m.d.sync += transfer.kind.eq(Transfer.Kind.DATA)
                    m.d.sync += transfer.payload.data.eq(self.rom_rd.data)
                    m.d.sync += self.i2c_bus.i_in_fifo_w_en.eq(1)

                    # Prepare next read, whether it's data or NEXTLEN[0].
                    m.d.sync += self.rom_rd.addr.eq(self.offset + 1)
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
                m.d.sync += self.remain.eq(self.rom_rd.data)
                m.d.sync += self.rom_rd.addr.eq(self.offset + 1)
                m.d.sync += self.offset.eq(self.offset + 1)
                m.next = "SEQ BREAK: ADDRESSED FOLLOWING, NEXTLEN[1] AVAILABLE"

            with m.State("SEQ BREAK: ADDRESSED FOLLOWING, NEXTLEN[1] AVAILABLE"):
                remain = self.remain | cast(Cat, self.rom_rd.data.shift_left(8))
                with m.If(remain == 0):
                    m.next = "FIN: WAIT I2C DONE"
                with m.Else():
                    m.d.sync += self.remain.eq(remain)
                    m.d.sync += transfer.kind.eq(Transfer.Kind.START)
                    m.d.sync += transfer.payload.start.addr.eq(self.addr)
                    m.d.sync += transfer.payload.start.rw.eq(RW.W)
                    m.d.sync += self.i2c_bus.i_in_fifo_w_en.eq(1)
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
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"
                with m.Elif(~self.i2c_bus.o_busy):
                    m.d.sync += self.o_busy.eq(0)
                    m.next = "IDLE"

        return m
