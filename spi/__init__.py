from typing import Optional, cast

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform
from amaranth.lib.io import Pin
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

from common import Hz

__all__ = ["SPIFlash"]


class SPIFlash(Elaboratable):
    # W25Q128JVSIM: max freq 133MHz
    # Guess we can use anything?
    speed: Hz

    sck: Signal
    copi: Signal
    cipo: Signal
    cs: Signal

    def __init__(self, *, speed: Hz):
        self.speed = speed

        self.sck = Signal()
        self.copi = Signal()
        self.cipo = Signal()
        self.cs = Signal()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        match platform:
            case ICEBreakerPlatform() | OrangeCrabR0_2_85FPlatform():
                res = platform.request("spi_flash")

                self.sck = cast(Signal, cast(Pin, res.clk).o)
                self.copi = cast(Signal, cast(Pin, res.copi).o)
                self.cipo = cast(Signal, cast(Pin, res.cipo).i)
                self.cs = cast(Signal, cast(Pin, res.cs).o)

            case _:
                pass

        return m
