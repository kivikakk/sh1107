import os
import subprocess
from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, Self, Type

from amaranth.build import Platform as AmaranthPlatform
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

from .base import Blackboxes

__all__ = ["Platform"]


class PlatformRegistry(ABCMeta):
    _registry: ClassVar[dict[str, Type[Self]]] = {}
    _build_targets: ClassVar[set[str]] = set()

    def __new__(mcls, name: str, bases: tuple[type, ...], *args: Any, **kwargs: Any):
        cls = super().__new__(mcls, name, bases, *args, **kwargs)
        if bases:
            mcls._registry[cls.__name__] = cls
            if issubclass(cls, AmaranthPlatform) and cls is not AmaranthPlatform:
                mcls._build_targets.add(cls.__name__)
        return cls

    def __getitem__(cls, key: str) -> "Platform":
        return cls._registry[key]()

    @property
    def build_targets(cls) -> set[str]:
        return cls._build_targets


class Platform(metaclass=PlatformRegistry):
    blackboxes: Blackboxes = set()

    @property
    @abstractmethod
    def flash_rom_base(self) -> int:
        ...

    def flash_rom(self, path: Path) -> None:
        raise NotImplementedError()

    simulation = False


class icebreaker(ICEBreakerPlatform, Platform):
    @property
    def flash_rom_base(self) -> int:
        return 0x80_0000

    def flash_rom(self, path: Path):
        iceprog = os.environ.get("ICEPROG", "iceprog")
        subprocess.run(
            [iceprog, "-o", hex(self.flash_rom_base), path],
            check=True,
        )


class orangecrab(OrangeCrabR0_2_85FPlatform, Platform):
    @property
    def flash_rom_base(self) -> int:
        return 0x10_0000

    def flash_rom(self, path: Path):
        dfu_util = os.environ.get("DFU_UTIL", "dfu-util")
        subprocess.run([dfu_util, "-a 1", "-D", path], check=True)


class vsh(Platform):
    @property
    def flash_rom_base(self) -> int:
        return 0xAB_CDEF

    @property
    def default_clk_frequency(self):
        return 3_000_000


class test(Platform):
    @property
    def flash_rom_base(self) -> int:
        return 0x00_CAFE

    simulation = True

    @property
    def default_clk_frequency(self):
        from .sim import clock

        return int(1 / clock())
