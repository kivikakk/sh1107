from typing import Optional, cast

from amaranth import Mux  # pyright: reportUnknownVariableType=false
from amaranth import Elaboratable, Memory, Module, Record, Signal
from amaranth.build import Platform
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

from i2c import I2C, Speed
from minor import ButtonWithHold
from .command import Command

with Command.writer() as w:
    # Adapted from juniper.

    # TODO: Use SH1107Command.
    w.write([0, 0xAE])  # disp off
    w.write([0, 0xD5, 0x80])  # clk div +15%/1
    w.write([0, 0xA8, 0x7F])  # set multiplex 128 (por)
    w.write([0, 0xD3, 0])  # display offset por
    w.write([0, 0xDC, 0])  # start line por
    w.write([0, 0xAD, 0x8B])  # enable charge pump when display on por
    w.write([0, 0xA0])  # seg remap por
    w.write([0, 0xC0])  # com out scan dir por
    # w.write([0, 0xDA, 0x12]) # 12 set compins
    w.write([0, 0x81, 0x80])  # set contrast
    # set precharge: 2 dclks (por), 2 dclks (por)
    w.write([0, 0xD9, 0x22])
    w.write([0, 0xDB, 0x40])  # set vcom deselect: 1//
    w.write([0, 0xA6])  # display non-inverted (por)

    # fill
    # show
    w.write([0, 0xAF])  # disp on

    INIT_SEQUENCE = w.done()

POWEROFF_SEQUENCE = Command.write([0, 0xAE])


class Top(Elaboratable):
    speed: Speed

    def __init__(self, *, speed: Speed):
        self.speed = speed

        self.init_sequence = Memory(
            width=8, depth=len(INIT_SEQUENCE), init=INIT_SEQUENCE
        )

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.i2c = self.i2c = i2c = I2C(speed=self.speed)

        switch: Signal
        program: Optional[Signal] = None

        match platform:
            case ICEBreakerPlatform():
                led_busy = cast(Signal, platform.request("led", 0).o)
                led_ack = cast(Signal, platform.request("led", 1).o)

                m.d.comb += led_busy.eq(i2c.o_busy)
                m.d.comb += led_ack.eq(i2c.o_ack)

                switch = cast(Signal, platform.request("button").i)

            case OrangeCrabR0_2_85FPlatform():
                rgb = platform.request("rgb_led")
                led_busy = cast(Signal, cast(Record, rgb.r).o)
                led_ack = cast(Signal, cast(Record, rgb.g).o)

                m.d.comb += led_busy.eq(i2c.o_busy)
                m.d.comb += led_ack.eq(i2c.o_ack)

                switch = cast(Signal, platform.request("button").i)
                program = cast(Signal, platform.request("program").o)

            case _:
                switch = Signal()

        was_turned_on = Signal()

        m.submodules.button = self.button = button = ButtonWithHold()
        m.d.comb += button.i.eq(switch)

        if program is not None:
            with m.If(button.o_held):
                m.d.sync += program.eq(1)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(button.o_up):
                    m.d.sync += i2c.i_addr.eq(0x3C)
                    m.d.sync += i2c.i_rw.eq(0)
                    with m.If(i2c.fifo.w_rdy):
                        m.d.sync += i2c.fifo.w_data.eq(0x00)
                        m.d.sync += i2c.fifo.w_en.eq(1)
                    m.next = "FIRST_QUEUED"
            with m.State("FIRST_QUEUED"):
                m.d.sync += i2c.i_stb.eq(1)
                m.d.sync += i2c.fifo.w_en.eq(0)
                m.next = "FIRST_READY"
            with m.State("FIRST_READY"):
                m.d.sync += i2c.i_stb.eq(0)
                # Wait until we need the next byte.
                m.next = "WAIT_SECOND"
            with m.State("WAIT_SECOND"):
                with m.If(i2c.o_busy & i2c.o_ack & i2c.fifo.w_rdy):
                    m.d.sync += i2c.fifo.w_data.eq(Mux(was_turned_on, 0xAE, 0xAF))
                    m.d.sync += was_turned_on.eq(~was_turned_on)
                    m.d.sync += i2c.fifo.w_en.eq(1)
                    m.next = "SECOND_DONE"
                with m.Elif(~i2c.o_busy):
                    # Failed.  Nothing to write.
                    m.next = "IDLE"
            with m.State("SECOND_DONE"):
                m.d.sync += i2c.fifo.w_en.eq(0)
                m.next = "IDLE"

        return m
