from typing import Optional, cast

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

from common import Button, Hz
from oled import OLED
from vendor.amlib.amlib.io.spi import SPIControllerInterface

__all__ = ["SPITestTop"]


class SPITestTop(Elaboratable):
    spi_flash: SPIControllerInterface
    oled: OLED
    switch: Signal

    def __init__(self):
        self.spi_flash = SPIControllerInterface(divisor=12)  # ?
        self.oled = OLED(speed=Hz(1_000_000))
        self.switch = Signal()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.spi_flash = self.spi_flash
        m.submodules.oled = self.oled

        match platform:
            case ICEBreakerPlatform() | OrangeCrabR0_2_85FPlatform():
                res = platform.request("spi_flash_1x")
                m.d.comb += self.spi_flash.connect_to_resource(res)

                switch = cast(Signal, platform.request("button").i)
                led = cast(Signal, platform.request("led", 0).o)
                led_top = cast(Signal, platform.request("led", 1).o)

            case _:
                switch = self.switch
                led = Signal()
                led_top = Signal()

        m.submodules.button = self.button = button = Button()
        m.d.comb += button.i.eq(switch)

        word = Signal(self.spi_flash.word_size)
        disp1_pls = Signal()
        disp1_yes = Signal()
        disp2_pls = Signal()
        disp2_yes = Signal()

        with m.FSM() as fsm:
            m.d.comb += led_top.eq(fsm.ongoing("LOOP"))

            with m.State("LOOP"):
                with m.If(button.o_up):
                    m.next = "START"

            with m.State("START"):
                m.d.sync += self.spi_flash.word_out.eq(0x9F)
                m.d.sync += self.spi_flash.start_transfer.eq(1)
                m.d.sync += disp1_pls.eq(1)
                m.next = "UNSTB"

            with m.State("UNSTB"):
                m.d.sync += self.spi_flash.start_transfer.eq(0)
                m.next = "READ"

            with m.State("READ"):
                with m.If(self.spi_flash.word_complete):
                    m.d.sync += disp2_pls.eq(1)
                    m.d.sync += word.eq(self.spi_flash.word_in)
                    m.next = "LOOP"

        with m.FSM() as fsm:
            m.d.comb += led.eq(fsm.ongoing("QUIET"))

            with m.State("INIT"):
                m.d.sync += self.oled.i_cmd.eq(OLED.Command.INIT)
                m.d.sync += self.oled.i_stb.eq(1)
                m.next = "DESTB"

            with m.State("DESTB"):
                m.d.sync += self.oled.i_stb.eq(0)
                with m.If(self.oled.o_result == OLED.Result.SUCCESS):
                    m.next = "QUIET"

            with m.State("QUIET"):
                with m.If(disp1_pls & ~disp1_yes):
                    m.d.sync += disp1_yes.eq(1)
                    m.d.sync += self.oled.i_cmd.eq(OLED.Command.DISPLAY)
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "DESTB"
                with m.Elif(disp2_pls & ~disp2_yes):
                    m.d.sync += disp2_yes.eq(1)
                    m.d.sync += self.oled.i_cmd.eq(OLED.Command.DISPLAY2)
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "DESTB"

        return m
