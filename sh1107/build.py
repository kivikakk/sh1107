import importlib
import inspect
import re
from argparse import ArgumentParser, Namespace
from typing import Any, Optional

from amaranth import Elaboratable

from .base import Blackbox, Blackboxes
from .platform import Platform
from .rtl.oled import OLED

__all__ = ["add_main_arguments", "build_top"]


def add_main_arguments(parser: ArgumentParser):
    parser.set_defaults(func=main)
    parser.add_argument(
        "-t",
        "--top",
        help="which top-level module to build (default: sh1107.rtl.Top)",
        default="sh1107.rtl.Top",
    )
    parser.add_argument(
        "target",
        choices=Platform.build_targets,
        help="which board to build for",
    )
    parser.add_argument(
        "-s",
        "--speed",
        choices=[str(s) for s in OLED.VALID_SPEEDS],
        help="I2C bus speed to build at",
        default=str(OLED.DEFAULT_SPEED),
    )
    parser.add_argument(
        "-p",
        "--program",
        action="store_true",
        help="program the design onto the board",
    )
    parser.add_argument(
        "-v",
        "--verilog",
        action="store_true",
        help="output debug Verilog",
    )


def main(args: Namespace):
    platform = Platform[args.target]

    component = build_top(args, platform)

    platform.build(
        component,
        do_program=args.program,
        debug_verilog=args.verilog,
        yosys_opts="-g",
    )

    heading = re.compile(r"^\d+\.\d+\. Printing statistics\.$", flags=re.MULTILINE)
    next_heading = re.compile(r"^\d+\.\d+\. ", flags=re.MULTILINE)
    _print_file_between("build/top.rpt", heading, next_heading)

    print("Device utilisation:")
    heading = re.compile(r"^Info: Device utilisation:$", flags=re.MULTILINE)
    next_heading = re.compile(r"^Info: Placed ", flags=re.MULTILINE)
    _print_file_between("build/top.tim", heading, next_heading, prefix="Info: ")


def build_top(args: Namespace, platform: Platform, **kwargs: Any) -> Elaboratable:
    from .rtl.common import Hz

    mod, klass_name = args.top.rsplit(".", 1)
    klass = getattr(importlib.import_module(mod), klass_name)

    sig = inspect.signature(klass)
    if "speed" in sig.parameters and "speed" in args:
        kwargs["speed"] = Hz(args.speed)

    blackboxes = kwargs.pop("blackboxes", Blackboxes())
    if kwargs.get("blackbox_i2c", getattr(args, "blackbox_i2c", False)):
        blackboxes.add(Blackbox.I2C)
    if kwargs.get("blackbox_spifr", getattr(args, "blackbox_spifr", False)):
        blackboxes.add(Blackbox.SPIFR)
    else:
        blackboxes.add(Blackbox.SPIFR_WHITEBOX)

    platform.blackboxes = blackboxes
    kwargs["platform"] = platform

    return klass(**kwargs)


def _print_file_between(
    path: str,
    start: re.Pattern[str],
    end: re.Pattern[str],
    *,
    prefix: Optional[str] = None,
):
    with open(path, "r") as f:
        for line in f:
            if start.match(line):
                break
        else:
            return

        for line in f:
            if end.match(line):
                return
            line = line.rstrip()
            if prefix is not None:
                line = line.removeprefix(prefix)
            print(line)
