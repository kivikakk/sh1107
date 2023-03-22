import unittest

from amaranth.sim import Delay, Settle

from sim_config import SimGenerator, SimTestCase, stc_args
from .timer import Timer


class TestTimer(SimTestCase):
    SIM_TEST_CLOCK = 1e-6

    @stc_args(time=1e-4)
    def test_sim_timer(self, d: Timer) -> SimGenerator:
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


if __name__ == "__main__":
    unittest.main()
