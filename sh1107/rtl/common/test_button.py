from amaranth.sim import Delay, Tick

from ... import sim
from .button import Button, ButtonWithHold


class TestButton(sim.TestCase):
    SIM_CLOCK = 1e-6

    def _button_down(self, b: Button) -> sim.Procedure:
        assert not (yield b.i)

        assert not (yield b.down)
        assert not (yield b.up)

        yield b.i.eq(1)

        yield Delay(b._debounce._hold_time)
        yield Tick()
        assert (yield b.down)
        assert not (yield b.up)

        yield Tick()
        assert not (yield b.down)

    def _button_up(self, b: Button) -> sim.Procedure:
        assert (yield b.i)
        yield b.i.eq(0)

        yield Delay(b._debounce._hold_time)
        yield Tick()
        assert not (yield b.down)
        assert (yield b.up)

    def _button_up_post(self, b: Button) -> sim.Procedure:
        assert (yield b.up)
        yield Tick()
        assert not (yield b.up)

    def test_sim_button(self, b: Button) -> sim.Procedure:
        yield from self._button_down(b)
        yield from self._button_up(b)
        yield from self._button_up_post(b)

    def test_sim_button_with_hold(self, b: ButtonWithHold) -> sim.Procedure:
        yield from self._button_down(b)
        # No delay
        yield from self._button_up(b)
        assert not (yield b.held)
        yield from self._button_up_post(b)

        yield from self._button_down(b)
        yield Delay(b._hold_time)
        yield from self._button_up(b)
        assert (yield b.up & b.held)
        yield from self._button_up_post(b)

        yield from self._button_down(b)
        yield Delay(b._hold_time / 2)
        assert not (yield b.held)
        yield Delay(b._hold_time)
        yield from self._button_up(b)
        assert (yield b.up & b.held)
        yield from self._button_up_post(b)
