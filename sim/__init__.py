from typing import Dict, Protocol, Tuple, List

from amaranth import Elaboratable, Signal
from amaranth.sim import Simulator

from i2c import Speed
from .start_bench import prep_start


class BenchCallable(Protocol):
    def __call__(self, *, speed: Speed) -> Tuple[Elaboratable, Simulator, List[Signal]]:
        ...


BENCHES: Dict[str, BenchCallable] = {
    "start": prep_start,
}

__all__ = ["BENCHES"]
