import inspect
import os
import re
import typing
import unittest
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional, Self, Tuple

from amaranth import Elaboratable, Signal
from amaranth.hdl.ast import Operator, Statement
from amaranth.hdl.ir import Fragment
from amaranth.lib.fifo import SyncFIFO
from amaranth.sim import Delay, Settle, Simulator

from .base import path
from .platform import Platform

__all__ = [
    "clock",
    "Procedure",
    "TestCase",
    "args",
    "i2c_speeds",
    "always_args",
    "fifo_content",
]

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


ValueLike = Signal | Delay | Settle | Statement | Operator | None

T = typing.TypeVar("T")
Generator = typing.Generator[ValueLike, bool | int, T]
Procedure = Generator[None]

Args = list[Any]
Kwargs = dict[str, Any]
SimArgs = Tuple[Args, Kwargs]


class TestCase(unittest.TestCase):
    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        for name, value in list(cls.__dict__.items()):
            if name.startswith("test_sim_"):
                cls._wrap_test(name, value)

    @classmethod
    def _wrap_test(
        cls,
        name: str,
        sim_test: Callable[[Self, Elaboratable], Procedure],
    ) -> None:
        sig = inspect.signature(sim_test)
        assert len(sig.parameters) >= 2
        dutpn = list(sig.parameters)[1]
        dutc = sig.parameters[dutpn].annotation

        sim_always_args: list[SimArgs] = getattr(sim_test, "_sim_always_args", [])
        all_sim_args: list[SimArgs] = getattr(sim_test, "_sim_args", [([], {})])

        delattr(cls, name)

        pattern = re.compile(r"[\W_]+")

        platform = Platform["test"]

        def sim_args_into_str(sim_args: SimArgs) -> str:
            subbed = pattern.sub("_", "_".join(str(v) for v in sim_args))
            return subbed.removesuffix("_").removeprefix("_")

        for sim_args in all_sim_args:
            expected_failure = sim_args[1].pop("expected_failure", False)
            ci_only = sim_args[1].pop("ci_only", False)

            suffix = sim_args_into_str(sim_args)
            if len(all_sim_args) > 1 and suffix:
                target = f"{name}_{suffix}"
            else:
                target = name

            dutc_sig = inspect.signature(dutc)
            platformp = dutc_sig.parameters.get("platform")
            if platformp is not None:
                assert platformp.annotation is Platform
                sim_args[1]["platform"] = platform

            for args, kwargs in sim_always_args:
                sim_args = (args + sim_args[0], {**kwargs, **sim_args[1]})

            @override_clock(getattr(cls, "SIM_CLOCK", None))
            def wrapper(self: TestCase, target: str, sim_args: SimArgs):
                dutc_args, dutc_kwargs = sim_args
                dut = dutc(*dutc_args, **dutc_kwargs)

                def bench() -> Procedure:
                    sim_test_kwargs = {}
                    sim_test_sig = inspect.signature(sim_test)
                    for arg_name, arg_value in dutc_kwargs.items():
                        if arg_name in sim_test_sig.parameters:
                            sim_test_kwargs[arg_name] = arg_value
                    yield from sim_test(self, dut, **sim_test_kwargs)

                sim = Simulator(Fragment.get(dut, platform))
                sim.add_clock(clock())
                sim.add_sync_process(bench)

                vcd_path = path(f"build/{cls.__name__}.{target}.vcd")
                sim_exc = None
                with sim.write_vcd(str(vcd_path)):
                    try:
                        sim.run()
                    except AssertionError as exc:
                        sim_exc = exc

                if sim_exc is not None:
                    print("\nFailing VCD at: ", vcd_path)
                    raise sim_exc

            def proxy(
                self: TestCase,
                target: str = target,
                sim_args: SimArgs = sim_args,
            ):
                return wrapper(self, target, sim_args)

            if expected_failure:
                proxy = unittest.expectedFailure(proxy)

            if not ci_only or os.getenv("CI", False):
                assert not hasattr(cls, target)
                setattr(cls, target, proxy)


def args(*args: Any, **kwargs: Any):
    def wrapper(sim_test: Callable[..., Procedure]) -> Callable[..., Procedure]:
        if not hasattr(sim_test, "_sim_args"):
            sim_test._sim_args = []  # pyright: ignore[reportFunctionMemberAccess]
        sim_test._sim_args.append(  # pyright: ignore[reportFunctionMemberAccess]
            (list(args), kwargs)
        )
        return sim_test

    return wrapper


def i2c_speeds(sim_test: Callable[..., Procedure]) -> Callable[..., Procedure]:
    from .rtl.common import Hz

    if not hasattr(sim_test, "_sim_args"):
        sim_test._sim_args = []  # pyright: ignore[reportFunctionMemberAccess]
    sim_test._sim_args.extend(  # pyright: ignore[reportFunctionMemberAccess]
        [
            ([], {"speed": Hz(100_000)}),
            ([], {"speed": Hz(400_000)}),
            ([], {"speed": Hz(1_000_000)}),
            ([], {"speed": Hz(2_000_000)}),
        ]
    )
    return sim_test


def always_args(*args: Any, **kwargs: Any):
    def wrapper(sim_test: Callable[..., Procedure]) -> Callable[..., Procedure]:
        if not hasattr(sim_test, "_sim_always_args"):
            sim_test._sim_always_args = (  # pyright: ignore[reportFunctionMemberAccess]
                []
            )
        sim_test._sim_always_args.append(  # pyright: ignore[reportFunctionMemberAccess]
            (list(args), kwargs)
        )
        return sim_test

    return wrapper


def fifo_content(fifo: SyncFIFO) -> Generator[list[int]]:
    content: list[int] = []

    while (yield fifo.r_rdy):
        content.append((yield fifo.r_data))
        yield fifo.r_en.eq(1)
        yield
        yield fifo.r_en.eq(0)
        yield

    return content
