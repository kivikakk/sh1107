from enum import Enum
from pathlib import Path
from typing import TypeAlias

__all__ = [
    "Blackbox",
    "Blackboxes",
    "path",
]


class Blackbox(Enum):
    I2C = 1
    SPIFR = 2
    SPIFR_WHITEBOX = 3


Blackboxes: TypeAlias = set[Blackbox]


def path(rest: str) -> Path:
    base = Path(__file__).parent.parent.absolute()
    return base / rest
