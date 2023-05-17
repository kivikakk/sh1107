import unittest
from typing import Optional

from amaranth import Signal
from amaranth.sim import Delay

import sim
from common import Hz
from i2c import I2C, RW, Transfer
from . import sim_i2c
from .test_i2c_top import TestI2CTop


# TODO: further unify with TestI2CRepeatedStart
class TestI2C(sim.TestCase):
    switch: Signal
    i2c: I2C

    @sim.always_args(
        [
            Transfer.const(
                {
                    "kind": Transfer.Kind.START,
                    "payload": {"start": {"addr": 0x3C, "rw": RW.W}},
                }
            ),
            Transfer.const({"kind": Transfer.Kind.DATA, "payload": {"data": 0xAF}}),
            Transfer.const({"kind": Transfer.Kind.DATA, "payload": {"data": 0x8C}}),
        ]
    )
    @sim.args(speed=Hz(100_000))
    @sim.args(speed=Hz(400_000))
    @sim.args(speed=Hz(1_000_000))
    @sim.args(speed=Hz(2_000_000))
    def test_sim_i2c(self, dut: TestI2CTop) -> sim.Generator:
        self.switch = dut.switch
        self.i2c = dut.i2c

        yield from self._bench_complete()
        yield from self._bench_nacks()

    def _bench_complete(self, *, nack_after: Optional[int] = None) -> sim.Generator:
        # Force the button push, we don't need to test it here.
        yield self.switch.eq(1)
        yield Delay(sim.clock())
        yield self.switch.eq(0)

        yield from sim_i2c.synchronise(self.i2c, 0x178)
        yield from sim_i2c.start(self.i2c)

        yield from sim_i2c.send(self.i2c, 0x78)
        if nack_after == 1:
            yield from sim_i2c.nack(self.i2c)
        else:
            yield from sim_i2c.ack(self.i2c)
            yield from sim_i2c.send(self.i2c, 0xAF, next=0x8C)
            if nack_after == 2:
                yield from sim_i2c.nack(self.i2c)
            else:
                yield from sim_i2c.ack(self.i2c)
                yield from sim_i2c.send(self.i2c, 0x8C, next="STOP")
                if nack_after == 3:
                    yield from sim_i2c.nack(self.i2c)
                else:
                    yield from sim_i2c.ack(self.i2c)

        yield from sim_i2c.stop(self.i2c)
        yield from sim_i2c.steady_stopped(self.i2c)

    def _bench_nacks(self) -> sim.Generator:
        yield from self._bench_complete(nack_after=1)
        yield from self._bench_complete(nack_after=2)
        yield from self._bench_complete(nack_after=3)


if __name__ == "__main__":
    unittest.main()
