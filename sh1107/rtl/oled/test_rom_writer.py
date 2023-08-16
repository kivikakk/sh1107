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
from .rom_writer import ROMWriter


class TestROMWriterTop(Elaboratable):
    ADDR: Final[int] = 0x3D

    speed: Hz

    i2c: I2C
    rom_rd: ReadPort
    rom_writer: ROMWriter

    def __init__(self, *, speed: Hz):
        self.speed = speed

        self.i2c = I2C(speed=speed)
        self.rom_rd = Memory(
            width=8,
            depth=rom.ROM_LENGTH,
            init=rom.ROM_CONTENT,
        ).read_port()
        self.rom_writer = ROMWriter(addr=TestROMWriterTop.ADDR)

    def elaborate(self, platform: Optional[Platform]) -> Elaboratable:
        m = Module()

        m.submodules.i2c = self.i2c
        m.submodules.rom_rd = self.rom_rd
        m.submodules.rom_writer = self.rom_writer

        connect(m, self.i2c.bus, self.rom_writer.i2c_bus)
        ROMBus.connect_read_port(m, self.rom_rd, self.rom_writer.rom_bus)

        return m


class TestROMWriter(sim.TestCase):
    @sim.i2c_speeds
    def test_sim_rom_writer_dispoff(self, dut: TestROMWriterTop) -> sim.Procedure:
        def trigger() -> sim.Procedure:
            assert not (yield dut.rom_writer.busy)
            yield dut.rom_writer.index.eq(rom.OFFSET_DISPLAY_OFF)
            yield dut.rom_writer.stb.eq(1)
            yield Delay(sim.clock())
            yield dut.rom_writer.stb.eq(0)

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
    def test_sim_rom_writer_chara(self, dut: TestROMWriterTop) -> sim.Procedure:
        def trigger() -> sim.Procedure:
            assert not (yield dut.rom_writer.busy)
            yield dut.rom_writer.index.eq(rom.OFFSET_CHAR + 0x41)
            yield dut.rom_writer.stb.eq(1)
            yield Delay(sim.clock())
            yield dut.rom_writer.stb.eq(0)

        yield from sim_i2c.full_sequence(
            dut.i2c,
            trigger,
            [
                0x17A,
                0x40,
                0b00110000,
                0b01111000,
                0b11001100,
                0b11001100,
                0b11111100,
                0b11001100,
                0b11001100,
                0b00000000,
            ],
        )
