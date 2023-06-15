import unittest

from amaranth.sim import Delay, Settle

import sim
from . import Button, ButtonWithHold


class TestButton(sim.TestCase):
    SIM_CLOCK = 1e-6

    def _button_down(self, b: Button) -> sim.Procedure:
        assert not (yield b.i)

        assert not (yield b.o_down)
        assert not (yield b.o_up)

        yield b.i.eq(1)

        yield Delay(b.debounce.hold_time)
        yield Settle()
        yield
        yield Settle()
        assert (yield b.o_down)
        assert not (yield b.o_up)

        yield
        yield Settle()
        assert not (yield b.o_down)

    def _button_up(self, b: Button) -> sim.Procedure:
        assert (yield b.i)
        yield b.i.eq(0)

        yield Delay(b.debounce.hold_time)
        yield Settle()
        yield
        yield Settle()
        assert not (yield b.o_down)
        assert (yield b.o_up)

    def _button_up_post(self, b: Button) -> sim.Procedure:
        assert (yield b.o_up)
        yield
        yield Settle()
        assert not (yield b.o_up)

    def test_sim_button(self, b: Button) -> sim.Procedure:
        yield from self._button_down(b)
        yield from self._button_up(b)
        yield from self._button_up_post(b)

    def test_sim_button_with_hold(self, b: ButtonWithHold) -> sim.Procedure:
        yield from self._button_down(b)
        # No delay
        yield from self._button_up(b)
        assert not (yield b.o_held)
        yield from self._button_up_post(b)

        yield from self._button_down(b)
        yield Delay(b.hold_time)
        yield from self._button_up(b)
        assert (yield b.o_up & b.o_held)
        yield from self._button_up_post(b)

        yield from self._button_down(b)
        yield Delay(b.hold_time / 2)
        assert not (yield b.o_held)
        yield Delay(b.hold_time)
        yield from self._button_up(b)
        assert (yield b.o_up & b.o_held)
        yield from self._button_up_post(b)


if __name__ == "__main__":
    unittest.main()
