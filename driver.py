#!/usr/bin/env python

import importlib.util
import re
import subprocess
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Dict, Optional, Type
from unittest import TestLoader, TextTestRunner

from amaranth.back import rtlil
from amaranth.build import Platform
from amaranth.hdl import Fragment
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

from formal import formal as prep_formal
from i2c import Speed
from oled import OLED

BOARDS: Dict[str, Type[Platform]] = {
    "icebreaker": ICEBreakerPlatform,
    "orangecrab": OrangeCrabR0_2_85FPlatform,
}


def _outfile(dir: str, ext: str):
    base = Path(sys.argv[0])
    return str(base.parent / dir / f"oled_i2c{ext}")


def test(args: Namespace):
    top = path = Path(__file__).parent
    if args.dir:
        path /= args.dir
    loader = TestLoader()
    suite = loader.discover(str(path), top_level_dir=str(top))
    result = TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())


def formal(args: Namespace):
    design, ports = prep_formal()
    fragment = Fragment.get(design, None)
    output = rtlil.convert(fragment, name="formal_top", ports=ports)
    with open(_outfile("build", ".il"), "w") as f:
        f.write(output)

    sby_file = _outfile("formal", ".sby")
    subprocess.run(f"sby --prefix build/oled_i2c -f {sby_file}", shell=True)


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


def build(args: Namespace):
    BOARDS[args.board]().build(
        OLED(speed=Speed(args.speed)),
        do_program=args.program,
        debug_verilog=args.verilog,
    )

    heading = re.compile(r"^\d+\.\d+\. Printing statistics\.$", flags=re.MULTILINE)
    next_heading = re.compile(r"^\d+\.\d+\. ", flags=re.MULTILINE)
    _print_file_between("build/top.rpt", heading, next_heading)

    print("Device utilisation:")
    heading = re.compile(r"^Info: Device utilisation:$", flags=re.MULTILINE)
    next_heading = re.compile(r"^Info: Placed ", flags=re.MULTILINE)
    _print_file_between("build/top.tim", heading, next_heading, prefix="Info: ")


def vsh(args: Namespace):
    from vsh import run

    run(args)


def main():
    parser = ArgumentParser(prog="fpgaxp.oled.main")
    subparsers = parser.add_subparsers(required=True)

    test_parser = subparsers.add_parser(
        "test",
        help="run the unit tests and sim tests",
    )
    test_parser.set_defaults(func=test)
    test_parser.add_argument(
        "dir",
        nargs="?",
        help="run tests from a specific subdirectory",
    )

    formal_parser = subparsers.add_parser(
        "formal",
        help="formally verify the design",
    )
    formal_parser.set_defaults(func=formal)

    build_parser = subparsers.add_parser(
        "build",
        help="build the design, and optionally program it",
    )
    build_parser.set_defaults(func=build)
    build_parser.add_argument(
        "board",
        choices=BOARDS.keys(),
        help="which board to build for",
    )
    build_parser.add_argument(
        "-s",
        "--speed",
        choices=[str(s) for s in Speed.VALID_SPEEDS],
        help="bus speed to build at",
        default=str(Speed.VALID_SPEEDS[0]),
    )
    build_parser.add_argument(
        "-p",
        "--program",
        action="store_true",
        help="program the design onto the board",
    )
    build_parser.add_argument(
        "-v",
        "--verilog",
        action="store_true",
        help="output debug Verilog",
    )

    if importlib.util.find_spec("pyglet") is not None:
        vsh_parser = subparsers.add_parser(
            "vsh",
            help="run the Virtual SH1107",
        )
        vsh_parser.set_defaults(func=vsh)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
