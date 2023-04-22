from typing import Literal

from amaranth import Signal

import sim


class SwitchConnector:
    switch: Signal

    _state: Literal["idle", "pressing", "releasing"]

    def __init__(self, switch: Signal):
        self.switch = switch

        self._state = "idle"

    def sim_process(self) -> sim.Generator:
        while True:
            if self._state == "pressing":
                self._state = "releasing"
                yield self.switch.eq(1)
            elif self._state == "releasing":
                self._state = "idle"
                yield self.switch.eq(0)
            yield

    def press(self):
        assert self._state == "idle"
        self._state = "pressing"
