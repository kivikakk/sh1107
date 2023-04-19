from typing import Optional

from amaranth import Elaboratable, Memory, Module, Signal
from amaranth.build import Platform
from amaranth.hdl.mem import ReadPort
from amaranth.lib.enum import IntEnum

from i2c import I2C, Speed
from .sh1107 import Cmd, DataBytes

__all__ = ["OLED"]

INIT_SEQUENCE = Cmd.compose(
    [
        Cmd.DisplayOn(False),
        Cmd.SetDisplayClockFrequency(1, "Pos15"),
        Cmd.SetDisplayOffset(0),
        Cmd.SetDisplayStartColumn(0),
        Cmd.SetDCDC(True),
        Cmd.SetSegmentRemap("Normal"),
        Cmd.SetContrastControlRegister(0x80),
        Cmd.SetPreDischargePeriod(2, 2),
        Cmd.SetVCOMDeselectLevel(0x40),
        Cmd.SetDisplayReverse(False),
        Cmd.DisplayOn(True),
    ]
)

DISPLAY_SEQUENCE = Cmd.compose(
    [
        Cmd.SetPageAddress(0),
        Cmd.SetLowerColumnAddress(0),
        Cmd.SetHigherColumnAddress(0),
        DataBytes([0xFF, 0x77, 0xFF, 0x77]),
    ]
)

DISPLAY2_SEQUENCE = Cmd.compose(
    [
        Cmd.SetPageAddress(0),
        Cmd.SetLowerColumnAddress(0),
        Cmd.SetHigherColumnAddress(0),
        DataBytes([0x77, 0xFF, 0x77, 0xFF]),
    ]
)

POWEROFF_SEQUENCE = Cmd.compose(
    [
        Cmd.DisplayOn(False),
    ]
)

ROM = []
OFFLENS = [0, 0]

for s in (INIT_SEQUENCE, DISPLAY_SEQUENCE, DISPLAY2_SEQUENCE, POWEROFF_SEQUENCE):
    OFFLENS.extend([len(ROM), len(s)])
    ROM.extend(s)


class OLED(Elaboratable):
    speed: Speed

    i2c: I2C

    i_cmd: Signal
    i_stb: Signal
    o_result: Signal

    offset: Signal
    remain: Signal
    offlens_rd: ReadPort
    rom_rd: ReadPort

    class Command(IntEnum):
        # these correspond to offsets in OFFLENS.
        # TODO(ari): less hacky
        INIT = 1
        DISPLAY = 2
        DISPLAY2 = 3
        POWEROFF = 4

    class Result(IntEnum):
        SUCCESS = 0
        BUSY = 1
        FAILURE = 2

    def __init__(self, *, speed: Speed):
        self.speed = speed

        self.i2c = I2C(speed=speed)

        self.i_cmd = Signal(OLED.Command)
        self.i_stb = Signal()
        self.o_result = Signal(OLED.Result)

        self.offset = Signal(range(len(ROM)))
        self.remain = Signal(range(len(ROM)))

        # TODO(ari): auto determine width for offlens? does it just truncate if too small?
        self.rom = Memory(width=8, depth=len(ROM), init=ROM)
        self.offlens = Memory(width=16, depth=len(OFFLENS), init=OFFLENS)

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.i2c = self.i2c

        m.submodules.rom_rd = self.rom_rd = rom_rd = self.rom.read_port(
            transparent=False
        )
        m.submodules.offlens_rd = self.offlens_rd = offlens_rd = self.offlens.read_port(
            transparent=False
        )

        cmd = Signal.like(self.i_cmd)

        with m.FSM():
            with m.State("WAIT_CMD"):
                with m.If(
                    self.i_stb
                    & (self.i_cmd >= min(OLED.Command))
                    & (self.i_cmd <= max(OLED.Command))
                    & self.i2c.fifo.w_rdy
                ):
                    m.d.sync += offlens_rd.addr.eq(self.i_cmd * 2)
                    m.d.sync += cmd.eq(self.i_cmd)
                    m.d.sync += self.o_result.eq(OLED.Result.BUSY)
                    m.next = "READ_OFF_WAIT"

            with m.State("READ_OFF_WAIT"):
                m.d.sync += offlens_rd.addr.eq(
                    cmd * 2 + 1
                )  # XXX(ari): can probably just add 1 to self
                m.next = "READ_OFF"

            with m.State("READ_OFF"):
                m.d.sync += self.offset.eq(offlens_rd.data)
                m.next = "READ_LEN"

            with m.State("READ_LEN"):
                m.d.sync += self.remain.eq(offlens_rd.data)
                m.next = "SEND_PREP"

            # Send loop:
            # * If remain == 0, we're done.
            # * Otherwise, when the I2C FIFO is ready, grab the next byte of data from the ROM.
            # * Set the I2C address + write bit, latch the data from the ROM into the FIFO, adjust pointers.
            # * Strobe I2C (and unstrobe the FIFO write).
            # * Unstrobe I2C.
            # * Wait until I2C indicates what's next:
            #   * If it reads ACK, we have until the end of that SCL cycle to enqueue the next byte.
            #   * Otherwise it'll stop and turn off its busy signal, which means it didn't ACK or we missed the boat.
            with m.State("SEND_PREP"):
                with m.If(self.remain == 0):
                    m.d.sync += self.o_result.eq(OLED.Result.SUCCESS)
                    m.next = "WAIT_CMD"
                with m.Elif(self.i2c.fifo.w_rdy):
                    m.d.sync += rom_rd.addr.eq(self.offset)
                    m.next = "SEND_ENQUEUE_WAIT"

            with m.State("SEND_ENQUEUE_WAIT"):
                m.next = "SEND_ENQUEUE"

            with m.State("SEND_ENQUEUE"):
                m.d.sync += self.i2c.i_addr.eq(0x3C)
                m.d.sync += self.i2c.i_rw.eq(0)
                m.d.sync += self.i2c.fifo.w_data.eq(rom_rd.data)
                m.d.sync += self.i2c.fifo.w_en.eq(1)

                m.d.sync += self.offset.eq(self.offset + 1)
                m.d.sync += self.remain.eq(self.remain - 1)

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

        return m
