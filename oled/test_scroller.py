from typing import Final, Optional

from amaranth import Elaboratable, Memory, Module
from amaranth.build import Platform
from amaranth.hdl.mem import ReadPort
from amaranth.sim import Delay

import sim
from common import Hz
from i2c import I2C, sim_i2c
from oled import rom
from .scroller import Scroller


class TestScrollerTop(Elaboratable):
    ADDR: Final[int] = 0x3D

    speed: Hz

    i2c: I2C
    rom_rd: ReadPort
    scroller: Scroller

    def __init__(self, *, speed: Hz):
        self.speed = speed

        self.i2c = I2C(speed=speed)
        self.rom_rd = Memory(
            width=8,
            depth=len(rom.ROM),
            init=rom.ROM,
        ).read_port(transparent=False)
        self.scroller = Scroller(memory=self.rom_rd.memory, addr=TestScrollerTop.ADDR)

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.i2c = self.i2c
        m.submodules.rom_rd = self.rom_rd
        m.submodules.scroller = self.scroller

        m.d.comb += [
            self.i2c.bus.connect(self.scroller.i2c_bus),
            self.rom_rd.addr.eq(self.scroller.rom_bus.i_addr),
            self.scroller.rom_bus.o_data.eq(self.rom_rd.data),
        ]

        return m


class TestScroller(sim.TestCase):
    @sim.args(speed=Hz(100_000), ci_only=True)
    @sim.args(speed=Hz(400_000), ci_only=True)
    @sim.args(speed=Hz(2_000_000))
    def test_sim_scroller(self, dut: TestScrollerTop) -> sim.Procedure:
        def trigger() -> sim.Procedure:
            assert not (yield dut.scroller.o_busy)
            yield dut.scroller.i_stb.eq(1)
            yield Delay(sim.clock())
            yield dut.scroller.i_stb.eq(0)

        yield from sim_i2c.full_sequence(
            dut.i2c,
            trigger,
            [
                0x17A,
                0x00,
                0x21,
                0xB0,
                0x10,
            ]
            + [
                [
                    0x17A,
                    0x80,
                    0x00 + i,
                    0x40,
                ]
                + [0x00] * 16
                for i in range(8)
            ]
            + [
                0x17A,
                0x00,
                0x20,
                0xDC,
                0x08,
            ],
            test_nacks=False,
        )
