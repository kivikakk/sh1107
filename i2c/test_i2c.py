from amaranth.sim import Delay, Settle

import sim
from i2c import RW, Transfer
from . import sim_i2c
from .test_i2c_top import TestI2CTop


class TestI2C(sim.TestCase):
    @sim.always_args(
        [
            Transfer.C_start(RW.W, 0x3C),
            Transfer.C_data(0xAF),
            Transfer.C_data(0x8C),
        ]
    )
    @sim.i2c_speeds
    def test_sim_i2c(self, dut: TestI2CTop) -> sim.Procedure:
        def trigger() -> sim.Procedure:
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

    @sim.always_args(
        [
            Transfer.C_start(RW.W, 0x3C),
            Transfer.C_data(0xAF),
            Transfer.C_start(RW.W, 0x3D),
            Transfer.C_data(0x8C),
        ]
    )
    @sim.i2c_speeds
    def test_sim_i2c_repeated_start(self, dut: TestI2CTop) -> sim.Procedure:
        def trigger() -> sim.Procedure:
            yield dut.switch.eq(1)
            yield
            yield Settle()
            yield dut.switch.eq(0)

        yield from sim_i2c.full_sequence(
            dut.i2c,
            trigger,
            [
                0x178,
                0xAF,
                0x17A,
                0x8C,
            ],
        )
