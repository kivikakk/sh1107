from typing import Optional, cast

from amaranth import Elaboratable, Module, Record, Signal
from amaranth.build import Platform
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

from common import Button, ButtonWithHold, Hz
from .oled import OLED

__all__ = ["Top"]


class Top(Elaboratable):
    oled: OLED
    speed: Hz

    switch: Signal

    def __init__(self, *, speed: Hz = Hz(1_000_000)):
        self.oled = OLED(speed=speed)
        self.speed = speed

        self.switch = Signal()

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

        push_and_ready = button_up & self.oled.i_fifo.w_rdy

        with m.FSM():
            with m.State("POWEROFF"):
                m.d.sync += self.oled.i_fifo.w_en.eq(0)
                with m.If(push_and_ready):
                    m.d.sync += self.oled.i_fifo.w_data.eq(OLED.Command.DISPLAY_ON)
                    m.d.sync += self.oled.i_fifo.w_en.eq(1)
                    m.next = "INIT"
            with m.State("INIT"):
                m.d.sync += self.oled.i_fifo.w_en.eq(0)
                with m.If(push_and_ready):
                    m.d.sync += self.oled.i_fifo.w_data.eq(OLED.Command.DISPLAY_OFF)
                    m.d.sync += self.oled.i_fifo.w_en.eq(1)
                    m.next = "DISPLAY1"
            with m.State("DISPLAY1"):
                m.d.sync += self.oled.i_fifo.w_en.eq(0)
                with m.If(push_and_ready):
                    m.d.sync += self.oled.i_fifo.w_data.eq(OLED.Command.CLS)
                    m.d.sync += self.oled.i_fifo.w_en.eq(1)
                    m.next = "DISPLAY2"
            with m.State("DISPLAY2"):
                m.d.sync += self.oled.i_fifo.w_en.eq(0)
                with m.If(push_and_ready):
                    m.d.sync += self.oled.i_fifo.w_data.eq(OLED.Command.LOCATE)
                    m.d.sync += self.oled.i_fifo.w_en.eq(1)
                    m.next = "POWEROFF"

        return m
