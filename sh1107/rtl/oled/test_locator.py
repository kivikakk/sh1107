from typing import Final, Optional

from amaranth import Elaboratable, Module
from amaranth.build import Platform
from amaranth.lib.wiring import connect
from amaranth.sim import Settle

from ... import sim
from ..common import Hz
from ..i2c import I2C, sim_i2c
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

    def elaborate(self, platform: Optional[Platform]) -> Elaboratable:
        m = Module()

        m.submodules.i2c = self.i2c
        m.submodules.locator = self.locator

        connect(m, self.i2c.bus, self.locator.i2c_bus)

        return m


class TestLocator(sim.TestCase):
    @sim.i2c_speeds
    def test_sim_locator(self, dut: TestLocatorTop) -> sim.Procedure:
        def trigger() -> sim.Procedure:
            yield dut.locator.row.eq(16)
            yield dut.locator.col.eq(8)
            yield dut.locator.stb.eq(1)
            yield
            yield Settle()
            yield dut.locator.stb.eq(0)

        yield from sim_i2c.full_sequence(
            dut.i2c,
            trigger,
            [
                0x17A,
                0x00,
                0xB8,
                0x08,
                0x17,
            ],
        )

    @sim.i2c_speeds
    def test_sim_locator_row_only(self, dut: TestLocatorTop) -> sim.Procedure:
        def trigger() -> sim.Procedure:
            yield dut.locator.row.eq(7)
            yield dut.locator.col.eq(0)
            yield dut.locator.stb.eq(1)
            yield
            yield Settle()
            yield dut.locator.stb.eq(0)

        yield from sim_i2c.full_sequence(
            dut.i2c,
            trigger,
            [
                0x17A,
                0x00,
                0x00,
                0x13,
            ],
        )

    @sim.i2c_speeds
    def test_sim_locator_col_only(self, dut: TestLocatorTop) -> sim.Procedure:
        def trigger() -> sim.Procedure:
            yield dut.locator.row.eq(0)
            yield dut.locator.col.eq(13)
            yield dut.locator.stb.eq(1)
            yield
            yield Settle()
            yield dut.locator.stb.eq(0)

        yield from sim_i2c.full_sequence(
            dut.i2c,
            trigger,
            [
                0x17A,
                0x00,
                0xB3,
            ],
        )
