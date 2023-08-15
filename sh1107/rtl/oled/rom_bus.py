from typing import Self

from amaranth import Record, Signal
from amaranth.hdl.ast import ShapeCastable, Statement
from amaranth.hdl.mem import ReadPort
from amaranth.hdl.rec import DIR_FANIN, DIR_FANOUT
from amaranth.lib.wiring import In, Out, Signature

__all__ = ["ROMBus"]


class ROMBus(Signature):
    def __init__(
        self,
        addr: ShapeCastable,
        data: ShapeCastable,
    ):
        return super().__init__(
            {
                "addr": In(addr),
                "data": Out(data),
            }
        )

    def connect_read_port(self, rom_rd: ReadPort) -> list[Statement]:
        return [
            rom_rd.addr.eq(self.addr),
            self.data.eq(rom_rd.data),
        ]
