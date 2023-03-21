from typing import Generator

from amaranth import Record, Signal
from amaranth.sim import Delay, Settle
from amaranth.hdl.ast import Statement

__all__ = ["SIM_CLOCK", "SimGenerator"]

SIM_CLOCK = 1 / 12e6
SimGenerator = Generator[Signal | Record | Delay | Settle | Statement, bool | int, None]
