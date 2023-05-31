from amaranth.sim import Settle

import sim
from . import sim_i2c
from .test_i2c_read_top import TestI2CReadTop


class TestI2CRead(sim.TestCase):
    @sim.always_args(0x3C, 1)
    @sim.i2c_speeds
    def test_sim_i2c_read_one(self, dut: TestI2CReadTop) -> sim.Generator:
        yield dut.switch.eq(1)
        yield
        yield Settle()
        yield dut.switch.eq(0)

        yield from sim_i2c.synchronise(dut.i2c, 0x179)
        yield from sim_i2c.start(dut.i2c)
        yield from sim_i2c.send(dut.i2c, 0x79)
        yield from sim_i2c.ack(dut.i2c, retakes_sda=False)
        yield from sim_i2c.receive(dut.i2c, 0xC5)
        yield from sim_i2c.nack(dut.i2c, from_us=True)
        yield from sim_i2c.stop(dut.i2c)
        yield from sim_i2c.steady_stopped(dut.i2c)

        assert not (yield dut.busy), "expected finished"
        assert (
            yield dut.result.r_level
        ) == 1, f"expected 1 byte in result FIFO, got {(yield dut.result.r_level)}"
        assert (
            yield dut.result.r_data
        ) == 0xC5, f"expected C5, got {(yield dut.result.r_data):02x}"

    @sim.always_args(0x3D, 2)
    @sim.i2c_speeds
    def test_sim_i2c_read_two(self, dut: TestI2CReadTop) -> sim.Generator:
        yield dut.switch.eq(1)
        yield
        yield Settle()
        yield dut.switch.eq(0)

        yield from sim_i2c.synchronise(dut.i2c, 0x17B)
        yield from sim_i2c.start(dut.i2c)
        yield from sim_i2c.send(dut.i2c, 0x7B)
        yield from sim_i2c.ack(dut.i2c, retakes_sda=False)
        yield from sim_i2c.receive(dut.i2c, 0xA3)
        yield from sim_i2c.ack(dut.i2c, from_us=True, retakes_sda=False)
        yield from sim_i2c.receive(dut.i2c, 0x5F)
        yield from sim_i2c.nack(dut.i2c, from_us=True)
        yield from sim_i2c.stop(dut.i2c)
        yield from sim_i2c.steady_stopped(dut.i2c)

        assert not (yield dut.busy), "expected finished"
        assert (
            yield dut.result.r_level
        ) == 2, f"expected 2 bytes in result FIFO, got {(yield dut.result.r_level)}"
        assert (yield dut.result.r_rdy)
        assert (
            yield dut.result.r_data
        ) == 0xA3, f"expected A3, got {(yield dut.result.r_data):02x}"
        yield dut.result.r_en.eq(1)
        yield
        yield dut.result.r_en.eq(0)
        yield
        assert (
            yield dut.result.r_data
        ) == 0x5F, f"expected 5F, got {(yield dut.result.r_data):02x}"
