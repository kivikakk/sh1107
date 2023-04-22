#!/usr/bin/env python

import ctypes
import importlib.util
import os
import re
import subprocess
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Dict, Optional, Type, cast
from unittest import TestLoader, TextTestRunner

from amaranth import Module
from amaranth._toolchain.cxx import build_cxx
from amaranth._toolchain.yosys import (
    find_yosys,  # pyright: reportUnknownVariableType=false
)
from amaranth._toolchain.yosys import YosysBinary
from amaranth.back import cxxrtl, rtlil
from amaranth.build import Platform
from amaranth.hdl import Fragment
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

from common import Hz
from formal import formal as prep_formal
from oled import OLED, ROM, Top

BOARDS: Dict[str, Type[Platform]] = {
    "icebreaker": ICEBreakerPlatform,
    "orangecrab": OrangeCrabR0_2_85FPlatform,
}


def _top(name: str) -> Type[Module]:
    mod, klass = name.rsplit(".", 1)
    return getattr(importlib.import_module(mod), klass)


def _outdir(dir: str) -> Path:
    base = Path(sys.argv[0]).absolute()
    return base.parent / dir


def _outfile(dir: str, ext: str) -> str:
    return str(_outdir(dir) / f"oled_i2c{ext}")


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
    # XXX: spaces in directory names
    subprocess.run(f"sby --prefix build/oled_i2c -f {sby_file}", shell=True, check=True)


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
    m = _top(args.top)
    if isinstance(m, Top):
        elaboratable = m(speed=Hz(args.speed))
    else:
        elaboratable = m()

    BOARDS[args.board]().build(
        elaboratable,
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


def rom(args: Namespace):
    path = Path(__file__).parent / "rom.bin"
    with open(path, "wb") as f:
        f.write(ROM)

    if args.program:
        # XXX: spaces in directory names
        subprocess.run(f"iceprog -o 0x800000 {path}", shell=True, check=True)


def vsh(args: Namespace):
    from vsh import run

    top = _top(args.top)
    if isinstance(top, Top):
        design = top(speed=Hz(args.speed))
    else:
        design = top()

    yosys = cast(YosysBinary, find_yosys(lambda _: True))

    output = cast(str, cxxrtl.convert(design, ports=design.ports))
    cxxrtl_cc_file = _outfile("build", ".cc")
    with open(cxxrtl_cc_file, "w") as f:
        f.write(output)

    cxxrtl_lib_path = _outfile("build", ".o")

    args: list[str] = [
        "zig",
        "c++",
        "-DCXXRTL_INCLUDE_CAPI_IMPL",
        "-I" + str(_outdir("vsh")),
        "-I" + str(_outdir("build")),
        "-I" + str(cast(Path, yosys.data_dir()) / "include"),
        "-c",
        cxxrtl_cc_file,
        "-o",
        cxxrtl_lib_path,
    ]
    subprocess.run(args, check=True)

    subprocess.run(
        [
            "zig",
            "build",
            "run",
            f"-Dyosys_data_dir={yosys.data_dir()}",
            f"-Dcxxrtl_lib_path={cxxrtl_lib_path}",
        ],
        cwd=_outdir("vsh"),
        check=True,
    )
    # library = ctypes.cdll.LoadLibrary(cxxrtl_lib_path)
    # print(library.vsh())

    # run(elaboratable, args)


def main():
    parser = ArgumentParser(prog="driver")
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

    # TODO!
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
        "-t",
        "--top",
        help="which top-level module to build (default: oled.Top)",
        default="oled.Top",
    )
    build_parser.add_argument(
        "board",
        choices=BOARDS.keys(),
        help="which board to build for",
    )
    build_parser.add_argument(
        "-s",
        "--speed",
        choices=[str(s) for s in OLED.VALID_SPEEDS],
        help="I2C bus speed to build at",
        default=str(OLED.DEFAULT_SPEED),
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

    rom_parser = subparsers.add_parser(
        "rom",
        help="build the ROM image, and optionally program it",
    )
    rom_parser.set_defaults(func=rom)
    rom_parser.add_argument(
        "-p",
        "--program",
        action="store_true",
        help="program the ROM onto the board",
    )

    if importlib.util.find_spec("pyglet") is not None:
        vsh_parser = subparsers.add_parser(
            "vsh",
            help="run the Virtual SH1107",
        )
        vsh_parser.set_defaults(func=vsh)
        vsh_parser.add_argument(
            "-t",
            "--top",
            help="which top-level module to simulate (default: oled.Top)",
            default="oled.Top",
        )
        vsh_parser.add_argument(
            "-v",
            "--vcd",
            action="store_true",
            help="output a VCD file",
        )

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
