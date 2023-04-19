from typing import Optional, cast

from amaranth import Elaboratable, Module, Record, Signal
from amaranth.build import Platform
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

from i2c import Speed
from minor import Button, ButtonWithHold
from .oled import OLED

__all__ = ["Top"]


class Top(Elaboratable):
    oled: OLED

    o_last_cmd: Signal

    sim_switch: Signal

    def __init__(self):
        self.oled = OLED(speed=Speed(100_000))

        self.o_last_cmd = Signal(OLED.Command)

        self.sim_switch = Signal()

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

                m.submodules.button = self.button = button = Button()
                m.d.comb += button.i.eq(switch)
                button_up = button.o_up

            case OrangeCrabR0_2_85FPlatform():
                rgb = platform.request("rgb_led")
                led_busy = cast(Signal, cast(Record, rgb.r).o)
                led_ack = cast(Signal, cast(Record, rgb.g).o)

                m.d.comb += led_busy.eq(self.oled.i2c.o_busy)
                m.d.comb += led_ack.eq(self.oled.i2c.o_ack)

                switch = cast(Signal, platform.request("button").i)
                program = cast(Signal, platform.request("program").o)

                m.submodules.button = self.button = button = ButtonWithHold()
                m.d.comb += button.i.eq(switch)
                button_up = button.o_up

                with m.If(button.o_held):
                    m.d.sync += program.eq(1)

            case None:
                switch = self.sim_switch
                buffer = Signal()
                button_up = Signal()

                m.d.sync += buffer.eq(switch)
                m.d.comb += button_up.eq(buffer & ~switch)

            case _:
                raise NotImplementedError

        with m.FSM():
            with m.State("POWEROFF"):
                m.d.sync += self.oled.i_stb.eq(0)
                with m.If(button_up):
                    m.d.sync += self.o_last_cmd.eq(OLED.Command.INIT)
                    m.d.sync += self.oled.i_cmd.eq(OLED.Command.INIT)
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "INIT"
            with m.State("INIT"):
                m.d.sync += self.oled.i_stb.eq(0)
                with m.If(button_up):
                    m.d.sync += self.o_last_cmd.eq(OLED.Command.DISPLAY)
                    m.d.sync += self.oled.i_cmd.eq(OLED.Command.DISPLAY)
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "DISPLAY1"
            with m.State("DISPLAY1"):
                m.d.sync += self.oled.i_stb.eq(0)
                with m.If(button_up):
                    m.d.sync += self.o_last_cmd.eq(OLED.Command.DISPLAY2)
                    m.d.sync += self.oled.i_cmd.eq(OLED.Command.DISPLAY2)
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "DISPLAY2"
            with m.State("DISPLAY2"):
                m.d.sync += self.oled.i_stb.eq(0)
                with m.If(button_up):
                    m.d.sync += self.o_last_cmd.eq(OLED.Command.POWEROFF)
                    m.d.sync += self.oled.i_cmd.eq(OLED.Command.POWEROFF)
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "POWEROFF"

        return m
