from amaranth import Module
from amaranth.hdl.ast import ShapeCastable
from amaranth.hdl.mem import ReadPort
from amaranth.lib.wiring import In, Interface, Out, Signature

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

    @staticmethod
    def connect_read_port(m: Module, rom_rd: ReadPort, rom_bus: Interface):
        m.d.comb += [
            rom_rd.addr.eq(rom_bus.addr),
            rom_bus.data.eq(rom_rd.data),
        ]
