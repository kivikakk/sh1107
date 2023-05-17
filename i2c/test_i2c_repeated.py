import unittest

from amaranth.sim import Delay

import sim
from common import Hz
from . import sim_i2c
from .i2c import RW, Transfer
from .test_i2c_top import TestI2CTop


class TestI2CRepeatedStart(sim.TestCase):
    @sim.always_args(
        [
            Transfer.const(
                {
                    "kind": Transfer.Kind.START,
                    "payload": {"start": {"addr": 0x3C, "rw": RW.W}},
                }
            ),
            Transfer.const({"kind": Transfer.Kind.DATA, "payload": {"data": 0xAF}}),
            Transfer.const(
                {
                    "kind": Transfer.Kind.START,
                    "payload": {"start": {"addr": 0x3D, "rw": RW.W}},
                }
            ),
            Transfer.const({"kind": Transfer.Kind.DATA, "payload": {"data": 0x8C}}),
        ]
    )
    @sim.args(speed=Hz(100_000))
    @sim.args(speed=Hz(400_000))
    @sim.args(speed=Hz(1_000_000))
    @sim.args(speed=Hz(2_000_000))
    def test_sim_i2c_repeated_start(self, dut: TestI2CTop) -> sim.Generator:
        def trigger() -> sim.Generator:
            yield dut.switch.eq(1)
            yield Delay(sim.clock())
            yield dut.switch.eq(0)

        yield from sim_i2c.full_sequence(
            dut.i2c,
            trigger,
            [
                0x178,
                0x78,
                0xAF,
                0x17A,
                0x8C,
            ],
        )


if __name__ == "__main__":
    unittest.main()
