from typing import Optional, cast

from amaranth import Elaboratable, Module, Record, Signal
from amaranth.build import Platform
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

from i2c import Speed
from minor import ButtonWithHold
from .oled import OLED


class Top(Elaboratable):
    oled: OLED

    def __init__(self):
        self.oled = OLED(speed=Speed(100_000))

    def elaborate(self, platform: Optional[Platform]):
        m = Module()

        m.submodules.oled = self.oled

        switch: Signal
        program: Optional[Signal] = None

        match platform:
            case ICEBreakerPlatform():
                led_busy = cast(Signal, platform.request("led", 0).o)
                led_ack = cast(Signal, platform.request("led", 1).o)

                m.d.comb += led_busy.eq(self.oled.i2c.o_busy)
                m.d.comb += led_ack.eq(self.oled.i2c.o_ack)

                switch = cast(Signal, platform.request("button").i)

            case OrangeCrabR0_2_85FPlatform():
                rgb = platform.request("rgb_led")
                led_busy = cast(Signal, cast(Record, rgb.r).o)
                led_ack = cast(Signal, cast(Record, rgb.g).o)

                m.d.comb += led_busy.eq(self.oled.i2c.o_busy)
                m.d.comb += led_ack.eq(self.oled.i2c.o_ack)

                switch = cast(Signal, platform.request("button").i)
                program = cast(Signal, platform.request("program").o)

            case _:
                switch = Signal()

        m.submodules.button = self.button = button = ButtonWithHold()
        m.d.comb += button.i.eq(switch)

        if program is not None:
            with m.If(button.o_held):
                m.d.sync += program.eq(1)

        with m.FSM():
            with m.State("POWEROFF"):
                m.d.sync += self.oled.i_stb.eq(0)
                with m.If(button.o_up):
                    m.d.sync += self.oled.i_cmd.eq(OLED.Command.INIT)
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "INIT"
            with m.State("INIT"):
                m.d.sync += self.oled.i_stb.eq(0)
                with m.If(button.o_up):
                    m.d.sync += self.oled.i_cmd.eq(OLED.Command.DISPLAY)
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "DISPLAY1"
            with m.State("DISPLAY1"):
                m.d.sync += self.oled.i_stb.eq(0)
                with m.If(button.o_up):
                    m.d.sync += self.oled.i_cmd.eq(OLED.Command.DISPLAY2)
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "DISPLAY2"
            with m.State("DISPLAY2"):
                m.d.sync += self.oled.i_stb.eq(0)
                with m.If(button.o_up):
                    m.d.sync += self.oled.i_cmd.eq(OLED.Command.POWEROFF)
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "POWEROFF"
