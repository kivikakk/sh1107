from typing import Final, Optional

from amaranth import Elaboratable, Memory, Module
from amaranth.build import Platform
from amaranth.hdl.mem import ReadPort
from amaranth.lib.wiring import connect
from amaranth.sim import Delay

from ... import rom, sim
from ..common import Hz
from ..i2c import I2C, sim_i2c
from .rom_bus import ROMBus
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
            depth=rom.ROM_LENGTH,
            init=rom.ROM_CONTENT,
        ).read_port()
        self.scroller = Scroller(addr=TestScrollerTop.ADDR)

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.i2c = self.i2c
        m.submodules.rom_rd = self.rom_rd
        m.submodules.scroller = self.scroller

        connect(m, self.i2c.bus, self.scroller.i2c_bus)
        ROMBus.connect_read_port(m, self.rom_rd, self.scroller.rom_bus)

        return m


class TestScroller(sim.TestCase):
    @sim.args(speed=Hz(100_000), ci_only=True)
    @sim.args(speed=Hz(400_000), ci_only=True)
    @sim.args(speed=Hz(2_000_000))
    def test_sim_scroller(self, dut: TestScrollerTop) -> sim.Procedure:
        def trigger() -> sim.Procedure:
            assert not (yield dut.scroller.busy)
            yield dut.scroller.stb.eq(1)
            yield Delay(sim.clock())
            yield dut.scroller.stb.eq(0)

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
