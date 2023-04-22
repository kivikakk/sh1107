from typing import Optional, cast

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

from common import Button
from vendor.amlib.amlib.io.spi import SPIControllerInterface

__all__ = ["SPITestTop"]


class SPITestTop(Elaboratable):
    spi_flash: SPIControllerInterface

    def __init__(self):
        self.spi_flash = SPIControllerInterface(divisor=12)  # ?

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.spi_flash = self.spi_flash

        match platform:
            case ICEBreakerPlatform() | OrangeCrabR0_2_85FPlatform():
                res = platform.request("spi_flash_1x")
                m.d.comb += self.spi_flash.connect_to_resource(res)

                switch = cast(Signal, platform.request("button").i)

            case _:
                raise NotImplementedError

        m.submodules.button = self.button = button = Button()
        m.d.comb += button.i.eq(switch)

        with m.FSM():
            with m.State("INIT"):
                with m.If(button.o_up):
                    m.next = "START"

            with m.State("START"):
                m.d.sync += self.spi_flash.word_out.eq(0x9F)
                m.d.sync += self.spi_flash.start_transfer.eq(1)
                m.next = "UNSTB"

            with m.State("UNSTB"):
                m.d.sync += self.spi_flash.start_transfer.eq(0)
                m.next = "READ"

        return m
