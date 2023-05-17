from typing import Optional, cast

from amaranth import Elaboratable, Memory, Module, Record, Signal
from amaranth.build import Platform
from amaranth.hdl.mem import ReadPort
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

from common import Button, ButtonWithHold, Hz
from .oled import OLED

__all__ = ["Top"]

# TEST_SEQUENCE = [
#     0x01,  # DISPLAY_ON
#     0x03,  # CLS
#     0x04,
#     0x01,
#     0x01,  # LOCATE 1, 1
#     0x05,
#     0x0E,
#     *[ord(c) for c in "Hello, world!\n"],  # PRINT "Hello, world!"
#     0x05,
#     0x06,
#     *[ord(c) for c in "Nyonk!"],  # PRINT "Nyonk!"
#     0x06,  # CURSOR_ON
# ]

msg = "Hello, world! This should wrap correctly."
TEST_SEQUENCE = [
    0x01,  # DISPLAY_ON
    0x03,  # CLS
    0x04,
    0x01,
    0x01,  # LOCATE 1, 1
    0x05,
    len(msg),
    *[ord(c) for c in msg],  # PRINT msg
    0x06,  # CURSOR_ON
]


class Top(Elaboratable):
    oled: OLED
    speed: Hz

    switch: Signal

    rom_rd: ReadPort

    def __init__(self, *, speed: Hz = Hz(1_000_000)):
        self.oled = OLED(speed=speed)
        self.speed = speed

        self.switch = Signal()

        self.rom_rd = Memory(
            width=8, depth=len(TEST_SEQUENCE), init=TEST_SEQUENCE
        ).read_port(transparent=False)

    @property
    def ports(self) -> list[Signal]:
        return [
            self.switch,
            self.oled.i2c.scl_o,
            self.oled.i2c.scl_oe,
            self.oled.i2c.sda_o,
            self.oled.i2c.sda_oe,
            self.oled.i2c.sda_i,
        ]

    def elaborate(self, platform: Optional[Platform]):
        m = Module()

        m.submodules.oled = self.oled
        m.submodules.rom_rd = self.rom_rd

        button_up: Signal

        match platform:
            case ICEBreakerPlatform():
                led_busy = cast(Signal, platform.request("led", 0).o)
                led_ack = cast(Signal, platform.request("led", 1).o)

                m.d.comb += led_busy.eq(self.oled.i2c.o_busy)
                m.d.comb += led_ack.eq(self.oled.i2c.o_ack)

                switch = cast(Signal, platform.request("button").i)
                m.submodules.button = button = Button()
                m.d.comb += button.i.eq(switch)
                button_up = button.o_up

                # platform.add_resources(platform.break_off_pmod)
                # led_l = platform.request("led_g", 1)
                # led_m = platform.request("led_r", 1)
                # led_r = platform.request("led_g", 2)

            case OrangeCrabR0_2_85FPlatform():
                rgb = platform.request("rgb_led")
                led_busy = cast(Signal, cast(Record, rgb.r).o)
                led_ack = cast(Signal, cast(Record, rgb.g).o)

                m.d.comb += led_busy.eq(self.oled.i2c.o_busy)
                m.d.comb += led_ack.eq(self.oled.i2c.o_ack)

                switch = cast(Signal, platform.request("button").i)
                m.submodules.button = button = ButtonWithHold()
                m.d.comb += button.i.eq(switch)
                button_up = button.o_up

                program = cast(Signal, platform.request("program").o)
                with m.If(button.o_held):
                    m.d.sync += program.eq(1)

            case None:
                switch = self.switch
                buffer = Signal()
                button_up = Signal()

                m.d.sync += buffer.eq(switch)
                m.d.comb += button_up.eq(buffer & ~switch)

            case _:
                raise NotImplementedError

        next_idx = Signal(range(len(TEST_SEQUENCE)))

        with m.FSM():
            with m.State("IDLE"):
                m.d.sync += self.oled.i_fifo.w_en.eq(0)
                with m.If(button_up & self.oled.i_fifo.w_rdy):
                    m.d.sync += next_idx.eq(0)
                    m.next = "LOOP: REQUEST"

            with m.State("LOOP: REQUEST"):
                m.d.sync += self.rom_rd.addr.eq(next_idx)
                m.next = "LOOP: ADDRESSED"

            with m.State("LOOP: ADDRESSED"):
                m.next = "LOOP: AVAILABLE"

            with m.State("LOOP: AVAILABLE"):
                with m.If(self.oled.i_fifo.w_rdy):
                    m.d.sync += self.oled.i_fifo.w_data.eq(self.rom_rd.data)
                    m.d.sync += self.oled.i_fifo.w_en.eq(1)
                    m.next = "LOOP: STROBED W_EN"

            with m.State("LOOP: STROBED W_EN"):
                m.d.sync += self.oled.i_fifo.w_en.eq(0)
                with m.If(next_idx == len(TEST_SEQUENCE) - 1):
                    m.next = "IDLE"
                with m.Else():
                    m.d.sync += next_idx.eq(next_idx + 1)
                    m.next = "LOOP: REQUEST"

        return m
