from typing import Optional

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform
from amaranth.lib.enum import IntEnum
from amaranth.sim import Settle

import sim
from common import Hz
from i2c import I2C, RW, Transfer
from . import sim_i2c


class Status(IntEnum):
    IDLE = 0
    BUSY = 1
    FAILED = 2
    SUCCESS = 3


class TestI2CReadTop(Elaboratable):
    speed: Hz
    switch: Signal
    status: Signal
    result: Signal

    i2c: I2C

    def __init__(self, *, speed: Hz):
        self.speed = speed
        self.switch = Signal()
        self.status = Signal(Status)
        self.result = Signal(8)

        self.i2c = I2C(speed=speed)

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.i2c = self.i2c

        bus = self.i2c.bus
        transfer = Transfer(bus.i_in_fifo_w_data)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.switch):
                    m.d.sync += [
                        transfer.kind.eq(Transfer.Kind.START),
                        transfer.payload.start.rw.eq(RW.R),
                        transfer.payload.start.addr.eq(0x3C),
                        bus.i_in_fifo_w_en.eq(1),
                        self.status.eq(Status.BUSY),
                    ]
                    m.next = "W_EN LATCHED"

            with m.State("W_EN LATCHED"):
                m.d.sync += [
                    bus.i_in_fifo_w_en.eq(0),
                    bus.i_stb.eq(1),
                ]
                m.next = "I2C STROBED"

            with m.State("I2C STROBED"):
                m.d.sync += bus.i_stb.eq(0)
                m.next = "I2C UNSTROBED"

            with m.State("I2C UNSTROBED"):
                with m.If(bus.o_busy & bus.o_ack & bus.o_in_fifo_r_rdy):
                    m.d.sync += [
                        transfer.kind.eq(Transfer.Kind.DATA),
                        bus.i_in_fifo_w_en.eq(1),
                    ]
                    m.next = "DATA LATCHED"

            with m.State("DATA LATCHED"):
                m.d.sync += bus.i_in_fifo_w_en.eq(0)
                m.next = "DATA UNLATCHED"

            with m.State("DATA UNLATCHED"):
                with m.If(bus.o_busy & bus.o_ack & bus.o_out_fifo_r_rdy):
                    m.d.sync += bus.i_out_fifo_r_en.eq(1)
                    m.next = "R_EN LATCHED"
                with m.Elif(~bus.o_busy):
                    m.d.sync += self.status.eq(Status.FAILED)
                    m.next = "IDLE"

            with m.State("R_EN LATCHED"):
                m.d.sync += bus.i_out_fifo_r_en.eq(0)
                m.next = "R_EN UNLATCHED"

            with m.State("R_EN UNLATCHED"):
                m.d.sync += [
                    self.status.eq(Status.SUCCESS),
                    self.result.eq(bus.o_out_fifo_r_data),
                ]
                m.next = "IDLE"

        return m


class TestI2CRead(sim.TestCase):
    @sim.i2c_speeds
    def test_sim_i2c_read(self, dut: TestI2CReadTop) -> sim.Generator:
        yield dut.switch.eq(1)
        yield
        yield Settle()
        yield dut.switch.eq(0)

        yield from sim_i2c.synchronise(dut.i2c, 0x179)
        yield from sim_i2c.start(dut.i2c)
        yield from sim_i2c.send(dut.i2c, 0x79)
        yield from sim_i2c.ack(dut.i2c)
        yield from sim_i2c.receive(dut.i2c, 0xC5)
        yield from sim_i2c.nack(dut.i2c, from_them=True)
        yield from sim_i2c.stop(dut.i2c)
        yield from sim_i2c.steady_stopped(dut.i2c)

        assert (
            yield dut.status
        ) == Status.SUCCESS, f"expected SUCCESS, got {Status((yield dut.status)).name}"
        assert (yield dut.result) == 0xC5, f"expected C5, got {(yield dut.result):02x}"
