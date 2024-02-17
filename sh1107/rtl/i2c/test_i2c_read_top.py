from amaranth import Elaboratable, Module
from amaranth.lib.fifo import SyncFIFO
from amaranth.lib.wiring import Component, In, Out

from ...platform import Platform
from ..common import Hz
from . import I2C, RW, Transfer

__all__ = ["TestI2CReadTop"]


class TestI2CReadTop(Component):
    _addr: int
    _count: int
    _speed: Hz

    _result: SyncFIFO

    _i2c: I2C

    def __init__(self, addr: int, count: int, *, speed: Hz):
        self._addr = addr
        assert count >= 1  # O permitir cero? (para NACK inmediato)
        self._count = count
        self._speed = speed

        super().__init__(
            {
                "switch": In(1),
                "busy": Out(1),
                "remaining": Out(range(self._count + 1)),
            }
        )

        self._result = SyncFIFO(width=8, depth=count)
        self._i2c = I2C(speed=speed)

    def elaborate(self, platform: Platform) -> Elaboratable:
        m = Module()

        m.submodules.i2c = self._i2c
        m.submodules.result = self._result

        bus = self._i2c.bus
        transfer = Transfer(bus.in_fifo_w_data)

        m.d.comb += [
            self._result.w_data.eq(bus.out_fifo_r_data),
            self._result.w_en.eq(bus.out_fifo_r_rdy),
            bus.out_fifo_r_en.eq(bus.out_fifo_r_rdy),
        ]

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.switch):
                    m.d.sync += [
                        transfer.kind.eq(Transfer.Kind.START),
                        transfer.payload.start.rw.eq(RW.R),
                        transfer.payload.start.addr.eq(self._addr),
                        bus.in_fifo_w_en.eq(1),
                        self.busy.eq(1),
                        self.remaining.eq(self._count),
                    ]
                    m.next = "W_EN LATCHED"

            with m.State("W_EN LATCHED"):
                m.d.sync += [
                    bus.in_fifo_w_en.eq(0),
                    bus.stb.eq(1),
                ]
                m.next = "WAIT WRITE"

            with m.State("WAIT WRITE"):
                m.d.sync += bus.stb.eq(0)
                with m.If(bus.busy & bus.ack & bus.in_fifo_w_rdy):
                    m.d.sync += [
                        transfer.kind.eq(Transfer.Kind.DATA),
                        bus.in_fifo_w_en.eq(1),
                    ]
                    m.next = "PLACEHOLDER LATCHED"

            with m.State("PLACEHOLDER LATCHED"):
                m.d.sync += bus.in_fifo_w_en.eq(0)

                with m.If(self.remaining == 1):
                    m.d.sync += self.busy.eq(0)
                    m.next = "IDLE"

                with m.Else():
                    m.d.sync += self.remaining.eq(self.remaining - 1)
                    m.next = "WAIT WRITE"

        return m
