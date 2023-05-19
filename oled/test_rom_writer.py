from typing import Final, Optional

from amaranth import Elaboratable, Module
from amaranth.build import Platform
from amaranth.sim import Delay

import sim
from common import Hz
from i2c import I2C, sim_i2c
from .rom import OFFSET_CHAR, OFFSET_DISPLAY_OFF
from .rom_writer import ROMWriter


class TestROMWriterTop(Elaboratable):
    ADDR: Final[int] = 0x3D

    speed: Hz

    i2c: I2C
    rom_writer: ROMWriter

    def __init__(self, *, speed: Hz):
        self.speed = speed

        self.i2c = I2C(speed=speed)
        self.rom_writer = ROMWriter(addr=TestROMWriterTop.ADDR)

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.i2c = self.i2c
        m.submodules.rom_writer = self.rom_writer

        self.rom_writer.connect_i2c_in(m, self.i2c)
        self.rom_writer.connect_i2c_out(m, self.i2c)

        return m


class TestROMWriter(sim.TestCase):
    @sim.i2c_speeds
    def test_sim_rom_writer_dispoff(self, dut: TestROMWriterTop) -> sim.Generator:
        def trigger() -> sim.Generator:
            assert not (yield dut.rom_writer.o_busy)
            yield dut.rom_writer.i_index.eq(OFFSET_DISPLAY_OFF)
            yield dut.rom_writer.i_stb.eq(1)
            yield Delay(sim.clock())
            yield dut.rom_writer.i_stb.eq(0)

        yield from sim_i2c.full_sequence(
            dut.i2c,
            trigger,
            [
                0x17A,
                0x00,
                0xAE,
            ],
        )

    @sim.i2c_speeds
    def test_sim_rom_writer_chara(self, dut: TestROMWriterTop) -> sim.Generator:
        def trigger() -> sim.Generator:
            assert not (yield dut.rom_writer.o_busy)
            yield dut.rom_writer.i_index.eq(OFFSET_CHAR + 0x41)
            yield dut.rom_writer.i_stb.eq(1)
            yield Delay(sim.clock())
            yield dut.rom_writer.i_stb.eq(0)

        yield from sim_i2c.full_sequence(
            dut.i2c,
            trigger,
            [
                0x17A,
                0x40,
                0b01111100,
                0b01111110,
                0b00010011,
                0b00010011,
                0b01111110,
                0b01111100,
                0b00000000,
                0b00000000,
            ],
        )
