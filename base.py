from enum import Enum
from typing import Final, TypeAlias

from amaranth import Elaboratable

from target import Target

__all__ = ["Blackbox", "Blackboxes", "Config", "ConfigElaboratable"]


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


class ConfigElaboratable(Elaboratable):
    config: Final[Config]

    def __init__(self, config: Config):
        self.config = config
