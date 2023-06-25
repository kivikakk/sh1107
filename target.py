import os
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, Self, Type

from amaranth.build import Platform
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

__all__ = ["Target"]


class Target(ABC):
    registry: ClassVar[dict[str, Type[Self]]] = {}

    def platform(self) -> Platform:
        ...

    @property
    @abstractmethod
    def flash_rom_base(self) -> int:
        ...

    def flash_rom(self, path: Path):
        ...

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        Target.registry[cls.__name__] = cls


class icebreaker(Target):
    def platform(self):
        return ICEBreakerPlatform()

    @property
    def flash_rom_base(self) -> int:
        return 0x80_0000

    def flash_rom(self, path: Path):
        iceprog = os.environ.get("ICEPROG", "iceprog")
        subprocess.run(
            [iceprog, "-o", hex(self.flash_rom_base), path],
            check=True,
        )


class orangecrab(Target):
    def platform(self):
        return OrangeCrabR0_2_85FPlatform()

    @property
    def flash_rom_base(self) -> int:
        return 0x10_0000

    def flash_rom(self, path: Path):
        dfu_util = os.environ.get("DFU_UTIL", "dfu-util")
        subprocess.run([dfu_util, "-a 1", "-D", path], check=True)


class vsh(Target):
    @property
    def flash_rom_base(self) -> int:
        return 0xABCDEF
