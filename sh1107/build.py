import re
from argparse import ArgumentParser, Namespace
from typing import Optional

from .base import build_top
from .rtl.oled import OLED
from .target import Target

__all__ = ["add_main_arguments"]


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
        choices=Target.platform_targets,
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
    target = Target[args.target]

    component = build_top(args, target)

    target.platform().build(
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
