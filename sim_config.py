import inspect
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Generator, Iterator, Optional, Self

from amaranth import Elaboratable, Record, Signal
from amaranth.hdl.ast import Statement
from amaranth.sim import Delay, Settle, Simulator

__all__ = ["sim_clock", "SimGenerator", "SimTestCase"]

_active_sim_clock = 1 / 12e6


def sim_clock() -> float:
    return _active_sim_clock


@contextmanager
def override_sim_clock(new_clock: Optional[float]) -> Iterator[None]:
    if new_clock is None:
        yield
        return

    global _active_sim_clock
    old_sim_clock = _active_sim_clock
    try:
        _active_sim_clock = new_clock
        yield
    finally:
        _active_sim_clock = old_sim_clock


SimGenerator = Generator[Signal | Record | Delay | Settle | Statement, bool | int, None]


class SimTestCase(unittest.TestCase):
    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        new_tests: dict[str, Callable[[Self], None]] = {}
        for name, value in cls.__dict__.items():
            if name.startswith("test_sim_"):
                new_tests[name] = cls._wrap_test(value)

        for name, value in new_tests.items():
            setattr(cls, name, value)

    @classmethod
    def _wrap_test(
        cls,
        sim_test: Callable[[Self, Elaboratable], SimGenerator],
    ) -> Callable[[Self], None]:
        sig = inspect.signature(sim_test)
        assert len(sig.parameters) == 2
        dutpn = list(sig.parameters)[1]
        dutc = sig.parameters[dutpn].annotation

        dutc_kwargs = {}

        dutc_sig = inspect.signature(dutc)
        in_simp = dutc_sig.parameters.get("in_sim")
        if in_simp is not None:
            assert in_simp.annotation is bool
            dutc_kwargs["in_sim"] = True

        vcd_path = (
            Path(__file__).parent / "build" / f"{cls.__name__}.{sim_test.__name__}.vcd"
        )

        @override_sim_clock(getattr(cls, "SIM_TEST_CLOCK"))
        def wrapper(self: SimTestCase):
            dut = dutc(**dutc_kwargs)

            def bench() -> SimGenerator:
                yield from sim_test(self, dut)

            sim = Simulator(dut)
            sim.add_clock(sim_clock())
            sim.add_sync_process(bench)

            sim_exc = None
            with sim.write_vcd(str(vcd_path)):
                try:
                    sim.run()
                except AssertionError as exc:
                    sim_exc = exc

            if sim_exc is not None:
                print("############### ", vcd_path)
                raise sim_exc

        return wrapper
