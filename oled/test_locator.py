from typing import Final, Optional

from amaranth import Elaboratable, Module
from amaranth.build import Platform
from amaranth.sim import Delay

import sim
from common import Hz
from i2c import I2C, sim_i2c
from .locator import Locator


class TestLocatorTop(Elaboratable):
    ADDR: Final[int] = 0x3D

    speed: Hz

    i2c: I2C
    locator: Locator

    def __init__(self, *, speed: Hz):
        self.speed = speed

        self.i2c = I2C(speed=speed)
        self.locator = Locator(addr=TestLocatorTop.ADDR)

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.i2c = self.i2c
        m.submodules.locator = self.locator

        self.locator.connect_i2c_in(m, self.i2c)
        self.locator.connect_i2c_out(m, self.i2c)

        return m


class TestLocator(sim.TestCase):
    @sim.i2c_speeds
    def test_sim_locator(self, dut: TestLocatorTop) -> sim.Generator:
        def trigger() -> sim.Generator:
            yield dut.locator.i_row.eq(16)
            yield dut.locator.i_col.eq(8)
            yield dut.locator.i_stb.eq(1)
            yield Delay(sim.clock())
            yield dut.locator.i_stb.eq(0)

        yield from sim_i2c.full_sequence(
            dut.i2c,
            trigger,
            [
                0x17A,
                0x00,
                0xBF,
                0x08,
                0x13,
            ],
        )

    @sim.i2c_speeds
    def test_sim_locator_row_only(self, dut: TestLocatorTop) -> sim.Generator:
        def trigger() -> sim.Generator:
            yield dut.locator.i_row.eq(7)
            yield dut.locator.i_col.eq(0)
            yield dut.locator.i_stb.eq(1)
            yield Delay(sim.clock())
            yield dut.locator.i_stb.eq(0)

        yield from sim_i2c.full_sequence(
            dut.i2c,
            trigger,
            [
                0x17A,
                0x00,
                0xB6,
            ],
        )

    @sim.i2c_speeds
    def test_sim_locator_col_only(self, dut: TestLocatorTop) -> sim.Generator:
        def trigger() -> sim.Generator:
            yield dut.locator.i_row.eq(0)
            yield dut.locator.i_col.eq(13)
            yield dut.locator.i_stb.eq(1)
            yield Delay(sim.clock())
            yield dut.locator.i_stb.eq(0)

        yield from sim_i2c.full_sequence(
            dut.i2c,
            trigger,
            [
                0x17A,
                0x00,
                0x00,
                0x16,
            ],
        )
