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

    class Result(IntEnum):
        SUCCESS = 0
        BUSY = 1
        FAILURE = 2

    VALID_SPEEDS: Final[list[int]] = [
        100_000,
        400_000,
        1_000_000,
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
            with m.State("WAIT_CMD"):
                with m.If(
                    self.i_stb
                    & (self.i_cmd >= min(OLED.Command))
                    & (self.i_cmd <= max(OLED.Command))
                    & self.i2c.fifo.w_rdy
                ):
                    m.d.sync += self.rom_rd.addr.eq((self.i_cmd - 1) * 4)
                    m.d.sync += cmd.eq(self.i_cmd - 1)
                    m.d.sync += self.o_result.eq(OLED.Result.BUSY)
                    m.next = "READ_OFF0_WAIT"

            with m.State("READ_OFF0_WAIT"):
                m.d.sync += self.rom_rd.addr.eq(self.rom_rd.addr + 1)
                m.next = "READ_OFF0"

            with m.State("READ_OFF0"):
                m.d.sync += self.rom_rd.addr.eq(self.rom_rd.addr + 1)
                m.d.sync += self.offset.eq(self.rom_rd.data)
                m.next = "READ_OFF1"

            with m.State("READ_OFF1"):
                m.d.sync += self.rom_rd.addr.eq(self.rom_rd.addr + 1)
                m.d.sync += self.offset.eq(self.offset | self.rom_rd.data.shift_left(8))
                m.next = "READ_LEN0"

            with m.State("READ_LEN0"):
                m.d.sync += self.remain.eq(self.rom_rd.data)
                # Prepare our first data byte read
                m.d.sync += self.rom_rd.addr.eq(self.offset)
                m.next = "READ_LEN1"

            with m.State("READ_LEN1"):
                m.d.sync += self.remain.eq(self.remain | self.rom_rd.data.shift_left(8))
                m.next = "SEND_PREP"

            # Send loop:
            # * If remain == 0, we're done with this transmission.
            # * Otherwise, when the I2C FIFO is ready, grab the next byte of data from the ROM.
            # * Set the I2C address + write bit, latch the data from the ROM into the FIFO, adjust pointers.
            # * Strobe I2C (and unstrobe the FIFO write).
            # * Unstrobe I2C.
            # * Wait until I2C indicates what's next:
            #   * If it reads ACK, we have until the end of that SCL cycle to enqueue the next byte.
            #   * Otherwise it'll stop and turn off its busy signal, which means it didn't ACK or we missed the boat.
            #
            # When done with a transmission, check to see if there are more to do
            # for this command.  If so, keep going.
            with m.State("SEND_PREP"):
                with m.If(self.remain == 0):
                    m.d.sync += self.rom_rd.addr.eq(self.offset + 1)
                    m.d.sync += self.offset.eq(self.offset + 1)
                    m.next = "SEQUENCE_BREAK"
                with m.Elif(self.i2c.fifo.w_rdy):
                    m.next = "SEND_ENQUEUE"

            with m.State("SEND_ENQUEUE"):
                m.d.sync += self.offset.eq(self.offset + 1)
                m.d.sync += self.remain.eq(self.remain - 1)
                m.d.sync += self.i2c.i_addr.eq(0x3C)
                m.d.sync += self.i2c.i_rw.eq(0)
                m.d.sync += self.i2c.fifo.w_data.eq(self.rom_rd.data)
                m.d.sync += self.i2c.fifo.w_en.eq(1)

                # Prepare next read, whether it's data or nextlen.
                m.d.sync += self.rom_rd.addr.eq(self.offset + 1)
                m.next = "SEND_READY"

            with m.State("SEND_READY"):
                m.d.sync += self.i2c.i_stb.eq(1)
                m.d.sync += self.i2c.fifo.w_en.eq(0)

                m.next = "SEND_UNSTB"

            with m.State("SEND_UNSTB"):
                m.d.sync += self.i2c.i_stb.eq(0)
                m.next = "SEND_WAIT"

            with m.State("SEND_WAIT"):
                with m.If(self.i2c.o_busy & self.i2c.o_ack & self.i2c.fifo.w_rdy):
                    m.next = "SEND_PREP"
                with m.Elif(~self.i2c.o_busy):
                    # Failed.  Nothing to write.
                    m.d.sync += self.o_result.eq(OLED.Result.FAILURE)
                    m.next = "WAIT_CMD"

            with m.State("SEQUENCE_BREAK"):
                m.d.sync += self.remain.eq(self.rom_rd.data)
                m.d.sync += self.rom_rd.addr.eq(self.offset + 1)
                m.d.sync += self.offset.eq(self.offset + 1)
                m.next = "SEQUENCE_BREAK_HIGH"

            with m.State("SEQUENCE_BREAK_HIGH"):
                remain = self.remain | cast(Cat, self.rom_rd.data.shift_left(8))
                with m.If(remain == 0):
                    m.next = "WAIT_I2C"
                with m.Else():
                    m.d.sync += self.remain.eq(remain)
                    m.next = "SEQUENCE_BREAK_WAIT"

            with m.State("SEQUENCE_BREAK_WAIT"):
                with m.If(~self.i2c.o_busy & self.i2c.o_ack & self.i2c.fifo.w_rdy):
                    m.next = "SEND_PREP"
                with m.Elif(~self.i2c.o_busy):
                    m.d.sync += self.o_result.eq(OLED.Result.FAILURE)
                    m.next = "WAIT_CMD"

            with m.State("WAIT_I2C"):
                with m.If(~self.i2c.o_busy & self.i2c.o_ack & self.i2c.fifo.w_rdy):
                    m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                    m.next = "WAIT_CMD"
                with m.Elif(~self.i2c.o_busy):
                    m.d.sync += self.o_result.eq(OLED.Result.FAILURE)
                    m.next = "WAIT_CMD"

        return m
