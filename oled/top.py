from typing import Optional, cast

from amaranth import Cat, Elaboratable, Module, Record, Signal
from amaranth.build import Platform
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

from common import Button, ButtonWithHold, Hz
from .oled import OLED

__all__ = ["Top"]


class Top(Elaboratable):
    oled: OLED
    speed: Hz

    o_last_cmd: Signal

    switch: Signal

    def __init__(self, *, speed: Hz = Hz(400_000)):
        self.oled = OLED(speed=speed)
        self.speed = speed

        self.o_last_cmd = Signal(OLED.Command)

        self.switch = Signal()

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

                platform.add_resources(platform.break_off_pmod)
                led_l = platform.request("led_g", 1)
                led_m = platform.request("led_r", 1)
                led_r = platform.request("led_g", 2)
                m.d.comb += Cat(led_l, led_m, led_r).eq(self.o_last_cmd)

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

        push_and_ready = button_up & (self.oled.o_result != OLED.Result.BUSY)

        with m.FSM():
            with m.State("POWEROFF"):
                m.d.sync += self.oled.i_stb.eq(0)
                with m.If(push_and_ready):
                    m.d.sync += self.o_last_cmd.eq(OLED.Command.INIT)
                    m.d.sync += self.oled.i_cmd.eq(OLED.Command.INIT)
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "INIT"
            with m.State("INIT"):
                m.d.sync += self.oled.i_stb.eq(0)
                with m.If(push_and_ready):
                    m.d.sync += self.o_last_cmd.eq(OLED.Command.DISPLAY)
                    m.d.sync += self.oled.i_cmd.eq(OLED.Command.DISPLAY)
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "DISPLAY1"
            with m.State("DISPLAY1"):
                m.d.sync += self.oled.i_stb.eq(0)
                with m.If(push_and_ready):
                    m.d.sync += self.o_last_cmd.eq(OLED.Command.DISPLAY2)
                    m.d.sync += self.oled.i_cmd.eq(OLED.Command.DISPLAY2)
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "DISPLAY2"
            with m.State("DISPLAY2"):
                m.d.sync += self.oled.i_stb.eq(0)
                with m.If(push_and_ready):
                    m.d.sync += self.o_last_cmd.eq(OLED.Command.POWEROFF)
                    m.d.sync += self.oled.i_cmd.eq(OLED.Command.POWEROFF)
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "POWEROFF"

        return m
