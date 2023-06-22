from enum import Enum
from typing import TypeAlias

__all__ = ["Blackbox", "Blackboxes"]


class Blackbox(Enum):
    I2C = 1
    SPI_FLASH = 2


Blackboxes: TypeAlias = set[Blackbox]
