from typing import Optional
from amaranth import Elaboratable, Module
from amaranth.build import Platform


__all__ = ["SPI"]


class SPI(Elaboratable):
    def __init__(self):
        pass

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        return m
