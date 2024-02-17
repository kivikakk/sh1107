from amaranth import Module
from amaranth.hdl import ReadPort, ShapeCastable
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
                "addr": Out(addr),
                "data": In(data),
            }
        )

    @staticmethod
    def connect_read_port(m: Module, rom_rd: ReadPort, rom_bus: object):
        m.d.comb += [
            rom_rd.addr.eq(rom_bus.addr),
            rom_bus.data.eq(rom_rd.data),
        ]
