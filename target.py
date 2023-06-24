from typing import Callable, Final

from amaranth.build import Platform
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

__all__ = ["TARGETS"]


class Target:
    amaranth_platform: Final[Callable[[], Platform]]
    flash_rom_base: Final[int]

    def __init__(self, amaranth_platform: Callable[[], Platform], flash_rom_base: int):
        self.amaranth_platform = amaranth_platform
        self.flash_rom_base = flash_rom_base


TARGETS = {
    "icebreaker": Target(
        amaranth_platform=ICEBreakerPlatform,
        flash_rom_base=0x800000,
    ),
    "orangecrab": Target(
        amaranth_platform=OrangeCrabR0_2_85FPlatform,
        flash_rom_base=0x100000,
    ),
}
