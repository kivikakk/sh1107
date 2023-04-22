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

    led_top: Signal
    led_oled: Signal

    vsh_tracks: list[Signal]

    def __init__(self):
        self.spi_flash = SPIControllerInterface(divisor=12)  # ?
        self.oled = OLED(speed=Hz(1_000_000))
        self.switch = Signal()

        self.led_top = Signal()
        self.led_oled = Signal()

        self.vsh_tracks = [self.led_top, self.led_oled]

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.spi_flash = self.spi_flash
        m.submodules.oled = self.oled

        button_up: Signal

        match platform:
            case ICEBreakerPlatform() | OrangeCrabR0_2_85FPlatform():
                res = platform.request("spi_flash_1x")
                m.d.comb += self.spi_flash.connect_to_resource(res)

                switch = cast(Signal, platform.request("button").i)
                m.submodules.button = button = Button()
                m.d.comb += button.i.eq(switch)
                button_up = button.o_up

                led_top = cast(Signal, platform.request("led", 0).o)
                led_oled = cast(Signal, platform.request("led", 1).o)

            case _:
                switch = self.switch
                buffer = Signal()
                button_up = Signal()

                m.d.sync += buffer.eq(switch)
                m.d.comb += button_up.eq(buffer & ~switch)

                led_top = self.led_top
                led_oled = self.led_oled

        word = Signal(self.spi_flash.word_size)
        disp1_pls = Signal()
        disp1_yes = Signal()
        disp2_pls = Signal()
        disp2_yes = Signal()
        dispword_pls = Signal()

        reset_wait = Signal(range(0x100000 + 1))

        with m.FSM() as fsm:
            m.d.comb += led_top.eq(fsm.ongoing("LOOP"))

            with m.State("LOOP"):
                with m.If(button_up):
                    m.next = "START_RESET0"

            with m.State("START_RESET0"):
                m.d.sync += self.spi_flash.word_out.eq(0x66)
                m.d.sync += self.spi_flash.start_transfer.eq(1)
                m.next = "START_RESET0_UNSTB"

            with m.State("START_RESET0_UNSTB"):
                m.d.sync += self.spi_flash.start_transfer.eq(0)
                m.next = "START_RESET0_WAIT"

            with m.State("START_RESET0_WAIT"):
                with m.If(self.spi_flash.word_complete):
                    m.d.sync += self.spi_flash.word_out.eq(0x99)
                    m.d.sync += self.spi_flash.start_transfer.eq(1)
                    m.next = "START_RESET1_UNSTB"

            with m.State("START_RESET1_UNSTB"):
                m.d.sync += self.spi_flash.start_transfer.eq(0)
                m.next = "START_RESET1_WAIT"

            with m.State("START_RESET1_WAIT"):
                with m.If(self.spi_flash.word_complete):
                    m.d.sync += reset_wait.eq(0)
                    m.next = "START_RESET_FLASHWAIT"

            with m.State("START_RESET_FLASHWAIT"):
                m.d.sync += reset_wait.eq(reset_wait + 1)
                with m.If(reset_wait == 0x100000):
                    m.d.sync += self.spi_flash.word_out.eq(0x9F)
                    m.d.sync += self.spi_flash.start_transfer.eq(1)
                    m.next = "UNSTB"

            with m.State("UNSTB"):
                m.d.sync += self.spi_flash.start_transfer.eq(0)
                m.next = "WAITFISH"

            with m.State("WAITFISH"):
                with m.If(self.spi_flash.word_complete):
                    m.d.sync += disp1_pls.eq(1)
                    m.d.sync += self.spi_flash.word_out.eq(0x00)
                    m.d.sync += self.spi_flash.start_transfer.eq(1)
                    m.next = "UNSTB2"

            with m.State("UNSTB2"):
                m.d.sync += self.spi_flash.start_transfer.eq(0)
                m.next = "WAITFISH2"

            with m.State("WAITFISH2"):
                with m.If(self.spi_flash.word_complete):
                    m.d.sync += disp2_pls.eq(1)
                    m.d.sync += dispword_pls.eq(1)
                    m.d.sync += word.eq(self.spi_flash.word_in)
                    m.next = "LOOP"

        with m.FSM() as fsm:
            m.d.comb += led_oled.eq(fsm.ongoing("QUIET"))

            with m.State("INIT"):
                m.d.sync += self.oled.i_cmd.eq(OLED.Command.INIT)
                m.d.sync += self.oled.i_stb.eq(1)
                m.next = "DESTB"

            with m.State("DESTB"):
                m.d.sync += self.oled.i_stb.eq(0)
                m.next = "WAIT"

            with m.State("WAIT"):
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
                with m.Elif(dispword_pls):
                    m.d.sync += dispword_pls.eq(0)
                    m.d.sync += self.oled.i_cmd.eq(OLED.Command.POS1)
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "POS1_DESTB"

            with m.State("POS1_DESTB"):
                m.d.sync += self.oled.i_stb.eq(0)
                m.next = "POS1_WAIT"

            with m.State("POS1_WAIT"):
                with m.If(self.oled.o_result == OLED.Result.SUCCESS):
                    m.d.sync += self.oled.i_cmd.eq(
                        OLED.Command.CHAR0 + (word.shift_right(4) & 0xF)
                    )
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "CHAR1_DESTB"

            with m.State("CHAR1_DESTB"):
                m.d.sync += self.oled.i_stb.eq(0)
                m.next = "CHAR1_WAIT"

            with m.State("CHAR1_WAIT"):
                with m.If(self.oled.o_result == OLED.Result.SUCCESS):
                    m.d.sync += self.oled.i_cmd.eq(OLED.Command.POS2)
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "POS2_DESTB"

            with m.State("POS2_DESTB"):
                m.d.sync += self.oled.i_stb.eq(0)
                m.next = "POS2_WAIT"

            with m.State("POS2_WAIT"):
                with m.If(self.oled.o_result == OLED.Result.SUCCESS):
                    m.d.sync += self.oled.i_cmd.eq(OLED.Command.CHAR0 + (word & 0xF))
                    m.d.sync += self.oled.i_stb.eq(1)
                    m.next = "DESTB"

        return m
