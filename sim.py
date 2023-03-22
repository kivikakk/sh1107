import inspect
import typing
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, List, Optional, Self

from amaranth import Elaboratable, Record, Signal
from amaranth.hdl.ast import Statement
from amaranth.sim import Delay, Settle, Simulator

__all__ = ["clock", "Generator", "TestCase", "args"]

_active_clock = 1 / 12e6


def clock() -> float:
    return _active_clock


@contextmanager
def override_clock(new_clock: Optional[float]) -> Iterator[None]:
    if new_clock is None:
        yield
        return

    global _active_clock
    old_sim_clock = _active_clock
    try:
        _active_clock = new_clock
        yield
    finally:
        _active_clock = old_sim_clock


Generator = typing.Generator[
    Signal | Record | Delay | Settle | Statement | None,
    bool | int,
    None,
]


class TestCase(unittest.TestCase):
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
        sim_test: Callable[[Self, Elaboratable], Generator],
    ) -> Callable[[Self], None]:
        sig = inspect.signature(sim_test)
        assert len(sig.parameters) == 2
        dutpn = list(sig.parameters)[1]
        dutc = sig.parameters[dutpn].annotation

        dutc_args: List[Any] = []
        dutc_kwargs: dict[str, Any] = {}
        if hasattr(sim_test, "_sim_args"):
            dutc_args, dutc_kwargs = sim_test._sim_args

        dutc_sig = inspect.signature(dutc)
        in_simp = dutc_sig.parameters.get("in_sim")
        if in_simp is not None:
            assert in_simp.annotation is bool
            dutc_kwargs["in_sim"] = True

        vcd_path = (
            Path(__file__).parent / "build" / f"{cls.__name__}.{sim_test.__name__}.vcd"
        )

        @override_clock(getattr(cls, "SIM_CLOCK", None))
        def wrapper(self: TestCase):
            dut = dutc(*dutc_args, **dutc_kwargs)

            def bench() -> Generator:
                yield from sim_test(self, dut)

            sim = Simulator(dut)
            sim.add_clock(clock())
            sim.add_sync_process(bench)

            sim_exc = None
            with sim.write_vcd(str(vcd_path)):
                try:
                    sim.run()
                except AssertionError as exc:
                    sim_exc = exc

            if sim_exc is not None:
                print("\nFailing VCD at: ", vcd_path)
                raise sim_exc

        return wrapper


def args(*args: Any, **kwargs: Any):
    def wrapper(sim_test: Callable[..., Generator]) -> Callable[..., Generator]:
        sim_test._sim_args = (args, kwargs)  # pyright: reportFunctionMemberAccess=none
        return sim_test

    return wrapper
