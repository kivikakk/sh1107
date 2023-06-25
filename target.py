import os
import subprocess
from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, Self, Type

from amaranth.build import Platform
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

__all__ = ["Target"]


class TargetRegistry(ABCMeta):
    _registry: ClassVar[dict[str, Type[Self]]] = {}
    _platform_targets: ClassVar[set[str]] = set()

    def __new__(mcls, name: str, bases: tuple[type, ...], *args: Any, **kwargs: Any):
        cls = super().__new__(mcls, name, bases, *args, **kwargs)
        if bases:
            mcls._registry[cls.__name__] = cls
            if "platform" in cls.__dict__:
                mcls._platform_targets.add(cls.__name__)
        return cls

    def __getitem__(cls, key: str) -> "Target":
        return cls._registry[key]()

    @property
    def platform_targets(cls) -> set[str]:
        return cls._platform_targets


class Target(metaclass=TargetRegistry):
    def platform(self) -> Platform:
        raise NotImplementedError()

    @property
    @abstractmethod
    def flash_rom_base(self) -> int:
        ...

    def flash_rom(self, path: Path) -> None:
        raise NotImplementedError()


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
        return 0xAB_CDEF


class test(Target):
    @property
    def flash_rom_base(self) -> int:
        return 0x00_CAFE
