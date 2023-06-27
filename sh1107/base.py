import importlib
import inspect
from argparse import Namespace
from enum import Enum
from pathlib import Path
from typing import Any, Final, Self, TypeAlias

from amaranth import Elaboratable

from .target import Target

__all__ = [
    "Blackbox",
    "Blackboxes",
    "Config",
    "ConfigElaboratable",
    "build_top",
    "path",
]


class Blackbox(Enum):
    I2C = 1
    SPIFR = 2
    SPIFR_WHITEBOX = 3


Blackboxes: TypeAlias = set[Blackbox]


class Config:
    target: Final[Target]
    blackboxes: Final[Blackboxes]

    def __init__(self, *, target: Target, blackboxes: Blackboxes):
        self.target = target
        self.blackboxes = blackboxes

    @classmethod
    @property
    def test(cls) -> Self:
        return Config(target=Target["test"], blackboxes=set())


class ConfigElaboratable(Elaboratable):
    config: Final[Config]

    def __init__(self, config: Config):
        self.config = config


def build_top(args: Namespace, target: Target, **kwargs: Any) -> Elaboratable:
    from .rtl.common import Hz

    mod, klass_name = args.top.rsplit(".", 1)
    klass = getattr(importlib.import_module(mod), klass_name)

    sig = inspect.signature(klass)
    if "speed" in sig.parameters and "speed" in args:
        kwargs["speed"] = Hz(args.speed)

    blackboxes = kwargs.pop("blackboxes", Blackboxes())
    if kwargs.get("blackbox_i2c", getattr(args, "blackbox_i2c", False)):
        blackboxes.add(Blackbox.I2C)
    if kwargs.get("blackbox_spifr", getattr(args, "blackbox_spifr", False)):
        blackboxes.add(Blackbox.SPIFR)
    else:
        blackboxes.add(Blackbox.SPIFR_WHITEBOX)

    kwargs["config"] = Config(target=target, blackboxes=blackboxes)

    return klass(**kwargs)


def path(rest: str) -> Path:
    base = Path(__file__).parent.parent.absolute()
    return base / rest
