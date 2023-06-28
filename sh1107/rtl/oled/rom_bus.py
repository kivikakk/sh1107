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

    def __init__(
        self,
        addr: ShapeCastable,
        data: ShapeCastable,
        *,
        name: str,
    ):
        super().__init__(
            [
                ("addr", addr, DIR_FANIN),
                ("data", data, DIR_FANOUT),
            ],
            name=f"ROMBus_{name}",
        )

    @classmethod
    def for_read_port(cls, rom_rd: ReadPort, *, name: str):
        return cls(rom_rd.addr.shape(), rom_rd.data.shape(), name=name)

    def clone(self, *, name: str) -> Self:
        # "like" gives back a Record, not an instance.
        return ROMBus(
            self.addr.shape(),
            self.data.shape(),
            name=name,
        )

    def connect_read_port(self, rom_rd: ReadPort) -> list[Statement]:
        return [
            rom_rd.addr.eq(self.addr),
            self.data.eq(rom_rd.data),
        ]
