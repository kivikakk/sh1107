from enum import Enum
from typing import TypeAlias

__all__ = ["Blackbox", "Blackboxes"]


class Blackbox(Enum):
    I2C = 1
    SPIFR = 2
    SPIFR_WHITEBOX = 3


Blackboxes: TypeAlias = set[Blackbox]
