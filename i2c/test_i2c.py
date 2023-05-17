import unittest

from amaranth.sim import Delay

import sim
from common import Hz
from i2c import RW, Transfer
from . import sim_i2c
from .test_i2c_top import TestI2CTop


class TestI2C(sim.TestCase):
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
        def trigger() -> sim.Generator:
            # Force the button push, we don't need to test it here.
            yield dut.switch.eq(1)
            yield Delay(sim.clock())
            yield dut.switch.eq(0)

        yield from sim_i2c.full_sequence(
            dut.i2c,
            trigger,
            [
                0x178,
                0xAF,
                0x8C,
            ],
        )


if __name__ == "__main__":
    unittest.main()
