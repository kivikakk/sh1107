import unittest

from amaranth.sim import Delay, Settle

from .. import sim
from .debounce import Debounce


class TestDebounce(sim.TestCase):
    SIM_CLOCK = 1e-6

    def test_sim_debounce(self, d: Debounce) -> sim.Procedure:
        assert not (yield d.i)
        assert not (yield d.o)

        yield d.i.eq(1)
        yield Delay(d.hold_time / 2)
        yield Settle()
        yield
        yield Settle()
        assert not (yield d.o)
        yield Delay(d.hold_time / 2)
        yield Settle()
        yield
        yield Settle()
        assert (yield d.o)

        yield d.i.eq(0)
        yield Delay(d.hold_time / 2)
        yield Settle()
        yield
        yield Settle()
        assert (yield d.o)
        yield Delay(d.hold_time / 2)
        yield Settle()
        yield
        yield Settle()
        assert not (yield d.o)


if __name__ == "__main__":
    unittest.main()
