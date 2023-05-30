from typing import Optional

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform
from amaranth.lib.fifo import SyncFIFO

from common import Hz
from i2c import I2C, RW, Transfer

__all__ = ["TestI2CReadTop"]


class TestI2CReadTop(Elaboratable):
    addr: int
    count: int
    speed: Hz

    switch: Signal
    busy: Signal
    remaining: Signal
    result: SyncFIFO

    i2c: I2C

    def __init__(self, addr: int, count: int, *, speed: Hz):
        self.addr = addr
        assert count >= 1  # O permitir cero? (para NACK inmediato)
        self.count = count
        self.speed = speed

        self.switch = Signal()
        self.busy = Signal()
        self.remaining = Signal(range(count + 1))
        self.result = SyncFIFO(width=8, depth=count)

        self.i2c = I2C(speed=speed)

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.i2c = self.i2c
        m.submodules.result = self.result

        bus = self.i2c.bus
        transfer = Transfer(bus.i_in_fifo_w_data)

        m.d.comb += self.result.w_data.eq(bus.o_out_fifo_r_data)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.switch):
                    m.d.sync += [
                        transfer.kind.eq(Transfer.Kind.START),
                        transfer.payload.start.rw.eq(RW.R),
                        transfer.payload.start.addr.eq(self.addr),
                        bus.i_in_fifo_w_en.eq(1),
                        self.busy.eq(1),
                        self.remaining.eq(self.count),
                    ]
                    m.next = "W_EN LATCHED"

            with m.State("W_EN LATCHED"):
                m.d.sync += [
                    bus.i_in_fifo_w_en.eq(0),
                    bus.i_stb.eq(1),
                ]
                m.next = "WAIT WRITE"

            with m.State("WAIT WRITE"):
                m.d.sync += bus.i_stb.eq(0)
                with m.If(bus.o_busy & bus.o_ack & bus.o_in_fifo_w_rdy):
                    m.d.sync += [
                        transfer.kind.eq(Transfer.Kind.DATA),
                        bus.i_in_fifo_w_en.eq(1),
                    ]
                    m.next = "PLACEHOLDER LATCHED"

            with m.State("PLACEHOLDER LATCHED"):
                m.d.sync += bus.i_in_fifo_w_en.eq(0)
                m.next = "PLACEHOLDER UNLATCHED"

            with m.State("PLACEHOLDER UNLATCHED"):
                with m.If(bus.o_busy & bus.o_ack & bus.o_out_fifo_r_rdy):
                    m.d.sync += [
                        bus.i_out_fifo_r_en.eq(1),
                        self.result.w_en.eq(1),
                    ]
                    m.next = "R_EN LATCHED"

                with m.Elif(~bus.o_busy):
                    m.d.sync += self.busy.eq(0)
                    m.next = "IDLE"

            with m.State("R_EN LATCHED"):
                m.d.sync += [
                    bus.i_out_fifo_r_en.eq(0),
                    self.result.w_en.eq(0),
                ]

                with m.If(self.remaining == 1):
                    m.d.sync += self.busy.eq(0)
                    m.next = "IDLE"

                with m.Else():
                    m.d.sync += self.remaining.eq(self.remaining - 1)
                    m.next = "WAIT WRITE"

        return m
