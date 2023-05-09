from typing import Final, Optional, cast

from amaranth import Cat, Elaboratable, Memory, Module, Signal
from amaranth.build import Platform
from amaranth.hdl.mem import ReadPort
from amaranth.lib.enum import IntEnum

from common import Hz
from i2c import I2C
from .rom import ROM

__all__ = ["OLED"]


class OLED(Elaboratable):
    class Command(IntEnum):
        # these correspond to offsets in ROM.
        # TODO(ari): less hacky
        INIT = 1
        DISPLAY = 2
        DISPLAY2 = 3
        POWEROFF = 4
        POS1 = 5
        POS2 = 6
        CHAR0 = 7
        CHARF = 22

    class Result(IntEnum):
        SUCCESS = 0
        BUSY = 1
        FAILURE = 2

    VALID_SPEEDS: Final[list[int]] = [
        100_000,
        400_000,
        1_000_000,
        2_000_000,  # XXX vsh
    ]
    DEFAULT_SPEED: Final[int] = 1_000_000

    speed: Hz

    i2c: I2C
    rom_rd: ReadPort

    i_cmd: Signal
    i_stb: Signal
    o_result: Signal

    offset: Signal
    remain: Signal

    def __init__(self, *, speed: Hz):
        assert speed.value in self.VALID_SPEEDS
        self.speed = speed

        self.i2c = I2C(speed=speed)

        self.i_cmd = Signal(OLED.Command)
        self.i_stb = Signal()
        self.o_result = Signal(OLED.Result)

        self.offset = Signal(range(len(ROM)))
        self.remain = Signal(range(len(ROM)))

        self.rom_rd = Memory(
            width=8,
            depth=len(ROM),
            init=ROM,
        ).read_port(transparent=False)

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.i2c = self.i2c
        m.submodules.rom_rd = self.rom_rd

        cmd = Signal.like(self.i_cmd)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(
                    self.i_stb
                    & (self.i_cmd >= min(OLED.Command))
                    & (self.i_cmd <= max(OLED.Command))
                    & self.i2c.fifo.w_rdy
                ):
                    m.d.sync += self.rom_rd.addr.eq((self.i_cmd - 1) * 4)
                    m.d.sync += cmd.eq(self.i_cmd - 1)
                    m.d.sync += self.o_result.eq(OLED.Result.BUSY)
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
                # Prepare our first data byte read
                m.d.sync += self.rom_rd.addr.eq(self.offset)
                m.next = "START: ADDRESSED *OFFSET, LEN[1] AVAILABLE"

            with m.State("START: ADDRESSED *OFFSET, LEN[1] AVAILABLE"):
                m.d.sync += self.remain.eq(self.remain | self.rom_rd.data.shift_left(8))
                m.d.sync += self.i2c.fifo.w_data.eq((0x3C << 1) | I2C.RW.W)
                m.d.sync += self.i2c.fifo.w_en.eq(1)
                m.next = "ADDRESS PERIPHERAL: LATCHED W_EN"

            with m.State("ADDRESS PERIPHERAL: LATCHED W_EN"):
                m.d.sync += self.i2c.fifo.w_en.eq(0)
                m.d.sync += self.i2c.i_stb.eq(1)
                m.next = "LOOP HEAD: SEQ BREAK OR WAIT I2C"

            # Send loop:
            # * If remain == 0, we're done with this transmission.
            # * Otherwise, when the I2C FIFO is ready, grab the next byte of
            #   data from the ROM.
            # * Set the I2C address + write bit, latch the data from the ROM
            #   into the FIFO, adjust pointers.
            # * Strobe I2C (and unstrobe the FIFO write).
            # * Unstrobe I2C.
            # * Wait until I2C indicates what's next:
            #   * If it reads ACK, we have until the end of that SCL cycle to
            #     enqueue the next byte.
            #   * Otherwise it'll stop and turn off its busy signal, which means
            #     it didn't ACK or we missed the boat.
            #
            # When done with a transmission, check to see if there are more to
            # do for this command.  If so, keep going.
            with m.State("LOOP HEAD: SEQ BREAK OR WAIT I2C"):
                # XXX(Ch): Compare desactivando aquí con en su propio estado
                # (wrt. celdas utilizadas)
                m.d.sync += self.i2c.i_stb.eq(0)
                with m.If(self.remain == 0):
                    m.d.sync += self.rom_rd.addr.eq(self.offset + 1)
                    m.d.sync += self.offset.eq(self.offset + 1)
                    m.next = "SEQ BREAK: ADDRESSED NEXTLEN[1], NEXTLEN[0] AVAILABLE"
                with m.Elif(self.i2c.fifo.w_rdy):
                    m.d.sync += self.offset.eq(self.offset + 1)
                    m.d.sync += self.remain.eq(self.remain - 1)
                    m.d.sync += self.i2c.fifo.w_data.eq(self.rom_rd.data)
                    m.d.sync += self.i2c.fifo.w_en.eq(1)

                    # Prepare next read, whether it's data or NEXTLEN[0].
                    m.d.sync += self.rom_rd.addr.eq(self.offset + 1)
                    m.next = "SEND: LATCHED W_EN"

            with m.State("SEND: LATCHED W_EN"):
                m.d.sync += self.i2c.fifo.w_en.eq(0)
                m.next = "SEND: WAIT FOR I2C"  # XXX(Ch): como anteriormente

            with m.State("SEND: WAIT FOR I2C"):
                with m.If(self.i2c.o_busy & self.i2c.o_ack & self.i2c.fifo.w_rdy):
                    m.next = "LOOP HEAD: SEQ BREAK OR WAIT I2C"
                with m.Elif(~self.i2c.o_busy):
                    # Failed.  Nothing to write.
                    m.d.sync += self.o_result.eq(OLED.Result.FAILURE)
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
                    m.d.sync += self.i2c.fifo.w_data.eq(
                        (1 << 8) | (0x3C << 1) | I2C.RW.W
                    )
                    m.d.sync += self.i2c.fifo.w_en.eq(1)
                    m.next = "SEQ BREAK: LATCHED W_EN"

            with m.State("SEQ BREAK: LATCHED W_EN"):
                m.d.sync += self.i2c.fifo.w_en.eq(0)
                m.next = "LOOP HEAD: SEQ BREAK OR WAIT I2C"

            with m.State("FIN: WAIT I2C DONE"):
                with m.If(~self.i2c.o_busy & self.i2c.o_ack & self.i2c.fifo.w_rdy):
                    m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                    m.next = "IDLE"
                with m.Elif(~self.i2c.o_busy):
                    m.d.sync += self.o_result.eq(OLED.Result.FAILURE)
                    m.next = "IDLE"

        return m
