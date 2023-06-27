from typing import Self

from amaranth import Record, Signal
from amaranth.hdl.ast import ShapeCastable, Statement
from amaranth.hdl.mem import ReadPort
from amaranth.hdl.rec import DIR_FANIN, DIR_FANOUT

__all__ = ["ROMBus"]


# XXX(Ch): All of this is ugly and The Worst, but it'll be replaced once the
# interfaces stuff is done.
class ROMBus(Record):
    addr: Signal
    data: Signal

    def __init__(self, addr: ShapeCastable, width: ShapeCastable):
        super().__init__(
            [
                ("addr", addr, DIR_FANIN),
                ("data", width, DIR_FANOUT),
            ],
            name="ROMBus",
        )

    @classmethod
    def for_read_port(cls, rom_rd: ReadPort):
        return cls(rom_rd.addr.shape(), rom_rd.data.shape())

    def clone(self) -> Self:
        # "like" gives back a Record, not an instance.
        return ROMBus(self.addr.shape(), self.data.shape())

    def connect_read_port(self, rom_rd: ReadPort) -> list[Statement]:
        return [
            rom_rd.addr.eq(self.addr),
            self.data.eq(rom_rd.data),
        ]
