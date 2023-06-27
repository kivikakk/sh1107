from amaranth.sim import Delay, Settle

from ... import sim
from .timer import Timer


class TestTimer(sim.TestCase):
    SIM_CLOCK = 1e-6

    @sim.args(time=1e-4)
    def test_sim_timer(self, d: Timer) -> sim.Procedure:
        assert not (yield d.i)
        assert not (yield d.o)

        yield d.i.eq(1)
        yield
        assert not (yield d.o)

        yield Delay(d.time)
        yield
        assert (yield d.o)

        yield d.i.eq(0)
        yield
        yield Settle()
        assert not (yield d.o)
