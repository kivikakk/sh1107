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

        si = sim_i2c.SimI2C(dut._i2c)

        yield from si.synchronize(0x179)
        yield from si.start()
        yield from si.send(0x79)
        yield from si.ack(retakes_sda=False)
        yield from si.receive(0xC5)
        yield from si.nack(from_us=True)
        yield from si.stop()
        yield from si.steady_stopped()

        assert not (yield dut.busy), "expected finished"
        self.assertEqual((yield from sim.fifo_content(dut._result)), [0xC5])

    @sim.always_args(0x3D, 2)
    @sim.i2c_speeds
    def test_sim_i2c_read_two(self, dut: TestI2CReadTop) -> sim.Procedure:
        yield dut.switch.eq(1)
        yield
        yield Settle()
        yield dut.switch.eq(0)

        si = sim_i2c.SimI2C(dut._i2c)

        yield from si.synchronize(0x17B)
        yield from si.start()
        yield from si.send(0x7B)
        yield from si.ack(retakes_sda=False)
        yield from si.receive(0xA3)
        yield from si.ack(from_us=True, retakes_sda=False)
        yield from si.receive(0x5F)
        yield from si.nack(from_us=True)
        yield from si.stop()
        yield from si.steady_stopped()

        assert not (yield dut.busy), "expected finished"
        self.assertEqual((yield from sim.fifo_content(dut._result)), [0xA3, 0x5F])
