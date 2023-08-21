from amaranth.sim import Settle

from ... import sim
from . import sim_i2c
from .test_i2c_read_top import TestI2CReadTop


class TestI2CRead(sim.TestCase):
    @sim.always_args(0x3C, 1)
    @sim.i2c_speeds
    def test_sim_i2c_read_one(self, dut: TestI2CReadTop) -> sim.Procedure:
        yield dut.switch.eq(1)
        yield
        yield Settle()
        yield dut.switch.eq(0)

        yield from sim_i2c.synchronise(dut._i2c, 0x179)
        yield from sim_i2c.start(dut._i2c)
        yield from sim_i2c.send(dut._i2c, 0x79)
        yield from sim_i2c.ack(dut._i2c, retakes_sda=False)
        yield from sim_i2c.receive(dut._i2c, 0xC5)
        yield from sim_i2c.nack(dut._i2c, from_us=True)
        yield from sim_i2c.stop(dut._i2c)
        yield from sim_i2c.steady_stopped(dut._i2c)

        assert not (yield dut.busy), "expected finished"
        self.assertEqual((yield from sim.fifo_content(dut._result)), [0xC5])

    @sim.always_args(0x3D, 2)
    @sim.i2c_speeds
    def test_sim_i2c_read_two(self, dut: TestI2CReadTop) -> sim.Procedure:
        yield dut.switch.eq(1)
        yield
        yield Settle()
        yield dut.switch.eq(0)

        yield from sim_i2c.synchronise(dut._i2c, 0x17B)
        yield from sim_i2c.start(dut._i2c)
        yield from sim_i2c.send(dut._i2c, 0x7B)
        yield from sim_i2c.ack(dut._i2c, retakes_sda=False)
        yield from sim_i2c.receive(dut._i2c, 0xA3)
        yield from sim_i2c.ack(dut._i2c, from_us=True, retakes_sda=False)
        yield from sim_i2c.receive(dut._i2c, 0x5F)
        yield from sim_i2c.nack(dut._i2c, from_us=True)
        yield from sim_i2c.stop(dut._i2c)
        yield from sim_i2c.steady_stopped(dut._i2c)

        assert not (yield dut.busy), "expected finished"
        self.assertEqual((yield from sim.fifo_content(dut._result)), [0xA3, 0x5F])
