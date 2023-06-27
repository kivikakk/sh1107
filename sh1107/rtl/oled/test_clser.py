from typing import Final, Optional

from amaranth import Elaboratable, Module
from amaranth.build import Platform
from amaranth.sim import Delay

from ... import sim
from ..common import Hz
from ..i2c import I2C, sim_i2c
from .clser import Clser


class TestClserTop(Elaboratable):
    ADDR: Final[int] = 0x3D

    speed: Hz

    i2c: I2C
    clser: Clser

    def __init__(self, *, speed: Hz):
        self.speed = speed

        self.i2c = I2C(speed=speed)
        self.clser = Clser(addr=TestClserTop.ADDR)

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.i2c = self.i2c
        m.submodules.clser = self.clser

        m.d.comb += self.i2c.bus.connect(self.clser.i2c_bus)

        return m


class TestClser(sim.TestCase):
    @sim.args(speed=Hz(100_000), ci_only=True)
    @sim.args(speed=Hz(400_000), ci_only=True)
    @sim.args(speed=Hz(2_000_000))
    def test_sim_clser(self, dut: TestClserTop) -> sim.Procedure:
        def trigger() -> sim.Procedure:
            yield dut.clser.i_stb.eq(1)
            yield Delay(sim.clock())
            yield dut.clser.i_stb.eq(0)

        yield from sim_i2c.full_sequence(
            dut.i2c,
            trigger,
            [
                0x17A,
                0x00,
                0x00,
                0x10,
                0xB0,
                0x17A,
                0x40,
                [0x00 for _ in range(128)],
                *[
                    [
                        0x17A,
                        0x00,
                        0xB0 + page,
                        0x17A,
                        0x40,
                        *[0x00 for _ in range(128)],
                    ]
                    for page in range(1, 16)
                ],
            ],
            test_nacks=False,
        )
