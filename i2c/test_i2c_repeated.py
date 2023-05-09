import unittest
from typing import Optional

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform
from amaranth.sim import Delay, Settle

import sim
from common import Hz
from .i2c import I2C
from .virtual_i2c import VirtualI2C


class Top(Elaboratable):
    speed: Hz
    switch: Signal

    def __init__(self, *, speed: Hz):
        self.speed = speed
        self.switch = Signal()

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.i2c = self.i2c = i2c = I2C(speed=self.speed)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.switch):
                    m.d.sync += i2c.fifo.w_data.eq((0x3C << 1) | I2C.RW.W)
                    m.d.sync += i2c.fifo.w_en.eq(1)
                    m.next = "ADDR_WOFF_STB"
            with m.State("ADDR_WOFF_STB"):
                m.d.sync += i2c.fifo.w_en.eq(0)
                m.d.sync += i2c.i_stb.eq(1)
                m.next = "UNSTB"
            with m.State("UNSTB"):
                m.d.sync += i2c.i_stb.eq(0)
                with m.If(i2c.fifo.w_rdy):
                    m.d.sync += i2c.fifo.w_data.eq(0xAF)
                    m.d.sync += i2c.fifo.w_en.eq(1)
                    m.next = "DATA_FIRST_WOFF"
            with m.State("DATA_FIRST_WOFF"):
                m.d.sync += i2c.fifo.w_en.eq(0)
                m.next = "DATA_SECOND_WAIT"
            with m.State("DATA_SECOND_WAIT"):
                with m.If(i2c.o_busy & i2c.o_ack & i2c.fifo.w_rdy):
                    m.d.sync += i2c.fifo.w_data.eq((1 << 8) | (0x3D << 1) | I2C.RW.W)
                    m.d.sync += i2c.fifo.w_en.eq(1)
                    m.next = "DATA_SECOND_WOFF"
                with m.Elif(~i2c.o_busy):
                    # Failed.  Nothing to write.
                    m.next = "IDLE"
            with m.State("DATA_SECOND_WOFF"):
                m.d.sync += i2c.fifo.w_en.eq(0)
                m.next = "DATA_THIRD_WAIT"
            with m.State("DATA_THIRD_WAIT"):
                with m.If(i2c.o_busy & i2c.o_ack & i2c.fifo.w_rdy):
                    m.d.sync += i2c.fifo.w_data.eq(0x8C)
                    m.d.sync += i2c.fifo.w_en.eq(1)
                    m.next = "DATA_THIRD_DONE"
                with m.Elif(~i2c.o_busy):
                    # Failed.  Nothing to write.
                    m.next = "IDLE"
            with m.State("DATA_THIRD_DONE"):
                m.d.sync += i2c.fifo.w_en.eq(0)
                m.next = "IDLE"

        return m


class TestI2CRepeatedStart(sim.TestCase):
    switch: Signal
    iv: VirtualI2C
    i2c: I2C

    @sim.args(speed=Hz(100_000))
    @sim.args(speed=Hz(400_000))
    @sim.args(speed=Hz(1_000_000))
    @sim.args(
        speed=Hz(2_000_000), expected_failure=True
    )  # currently i2c.py can't do 2MHz on a 12MHz clock
    def test_sim_i2c_repeated_start(self, dut: Top) -> sim.Generator:
        self.switch = dut.switch
        self.iv = VirtualI2C(dut.i2c)
        self.i2c = dut.i2c

        yield from self._bench_complete()
        yield from self._bench_nacks()

    def _bench_complete(self, *, nack_after: Optional[int] = None) -> sim.Generator:
        # Force the button push, we don't need to test it here.
        yield self.switch.eq(1)
        yield Delay(sim.clock())
        yield Settle()
        yield self.switch.eq(0)

        # Enqueue the data.
        assert not (yield self.i2c.i_stb)
        assert (yield self.i2c.fifo.w_en)
        assert (yield self.i2c.fifo.w_data) == 0x78
        assert not (yield self.i2c.fifo.r_rdy)
        assert (yield self.i2c.fifo.r_level) == 0
        yield Delay(sim.clock())
        yield Settle()

        # Data is enqueued, we're strobing I2C.  I2C still high.
        assert (yield self.i2c.i_stb)
        assert not (yield self.i2c.fifo.w_en)
        assert (yield self.i2c.fifo.r_rdy)
        assert (yield self.i2c.fifo.r_level) == 1

        assert (yield self.i2c.scl_o)
        assert (yield self.i2c.sda_o)
        yield Delay(sim.clock())
        yield Settle()

        yield from self.iv.start()

        yield from self.iv.send((0x3C << 1) | 0)
        if nack_after == 1:
            yield from self.iv.nack()
        else:
            yield from self.iv.ack()
            yield from self.iv.send(0xAF, next=0x17A)
            if nack_after == 2:
                yield from self.iv.nack()
            else:
                yield from self.iv.ack()
                yield from self.iv.repeated_start()
                yield from self.iv.send((0x3D << 1) | 0)
                if nack_after == 3:
                    yield from self.iv.nack()
                else:
                    yield from self.iv.ack()
                    yield from self.iv.send(0x8C, next="STOP")
                    if nack_after == 4:
                        yield from self.iv.nack()
                    else:
                        yield from self.iv.ack()

        yield from self.iv.stop()

        for _ in range(3):
            yield Delay(sim.clock())
            yield Settle()
            assert (yield self.i2c.scl_o)
            assert (yield self.i2c.sda_o)

    def _bench_nacks(self) -> sim.Generator:
        yield from self._bench_complete(nack_after=1)
        yield from self._bench_complete(nack_after=2)
        yield from self._bench_complete(nack_after=3)
        yield from self._bench_complete(nack_after=4)


if __name__ == "__main__":
    unittest.main()
