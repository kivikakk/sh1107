#!/usr/bin/env python

import importlib.util
import inspect
import os
import re
import subprocess
import sys
import warnings
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Any, Dict, Optional, Type, cast
from unittest import TestLoader, TextTestRunner

from amaranth import Elaboratable
from amaranth._toolchain.yosys import YosysBinary, find_yosys
from amaranth.back import cxxrtl, rtlil
from amaranth.build import Platform
from amaranth.hdl import Fragment
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

from common import Hz
from formal import formal as prep_formal
from oled import OLED, ROM_CONTENT, ROM_OFFSET

BOARDS: Dict[str, Type[Platform]] = {
    "icebreaker": ICEBreakerPlatform,
    "orangecrab": OrangeCrabR0_2_85FPlatform,
}


def _build_top(args: Namespace, **kwargs: Any) -> Elaboratable:
    mod, klass_name = args.top.rsplit(".", 1)
    klass = getattr(importlib.import_module(mod), klass_name)

    sig = inspect.signature(klass)
    if "speed" in sig.parameters and "speed" in args:
        kwargs["speed"] = Hz(args.speed)

    if not kwargs.get("build_i2c") and args.i2c:
        kwargs["build_i2c"] = True

    return klass(**kwargs)


def _path(rest: str) -> Path:
    base = Path(sys.argv[0]).absolute()
    return base.parent / rest


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
    with open(_path("build/sh1107.il"), "w") as f:
        f.write(output)

    sby_file = _path("formal/sh1107.sby")
    subprocess.run(
        ["sby", "--prefix", "build/sh1107", "-f", sby_file, *args.tasks], check=True
    )


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
    elaboratable = _build_top(args, build_i2c=True)

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
        f.write(ROM_CONTENT)

    if args.program:
        subprocess.run(["iceprog", "-o", hex(ROM_OFFSET), path], check=True)


def vsh(args: Namespace):
    design = _build_top(args)

    # NOTE(ari): works better on Windows since osscad's yosys-config a) doesn't
    # execute cleanly automatically (bash script), and b) its answers are wrong
    # anyway.
    os.environ["AMARANTH_USE_YOSYS"] = "builtin"

    yosys = cast(YosysBinary, find_yosys(lambda _: True))

    with open(_path("vsh/i2c_blackbox.il"), "r") as f:
        i2c_blackbox_rtlil = f.read()

    output = cast(
        str,
        cxxrtl.convert(
            design,
            black_boxes={} if args.i2c else {"i2c": i2c_blackbox_rtlil},
            ports=getattr(design, "ports", []),
        ),
    )
    cxxrtl_cc_file = _path("build/sh1107.cc")
    with open(cxxrtl_cc_file, "w") as f:
        f.write(output)

    cxxrtl_lib_path = _path("build/sh1107.o")

    subprocess.run(
        [
            "zig",
            "c++",
            "-DCXXRTL_INCLUDE_CAPI_IMPL",
            "-DCXXRTL_INCLUDE_VCD_CAPI_IMPL",
            "-I" + str(_path("build")),
            "-I" + str(cast(Path, yosys.data_dir()) / "include"),
            "-c",
            cxxrtl_cc_file if args.i2c else _path("vsh/i2c_blackbox.cc"),
            "-o",
            cxxrtl_lib_path,
        ],
        check=True,
    )

    cmd: list[str] = ["zig", "build"]
    if not args.compile:
        cmd += ["run"]
    cmd += [
        *(["-Doptimize=ReleaseFast"] if args.opt else []),
        f"-Dyosys_data_dir={yosys.data_dir()}",
        f"-Dcxxrtl_lib_path={cxxrtl_lib_path}",
    ]
    if not args.compile:
        cmd += ["--"]
        if args.vcd:
            cmd += ["--vcd"]

    subprocess.run(cmd, cwd=_path("vsh"), check=True)


def main():
    parser = ArgumentParser(prog="main")
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
    formal_parser.add_argument(
        "tasks",
        help="tasks to run; defaults to all",
        nargs="*",
    )

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
        help="(WIP) build the ROM image, and optionally program it",
    )
    rom_parser.set_defaults(func=rom)
    rom_parser.add_argument(
        "-p",
        "--program",
        action="store_true",
        help="program the ROM onto the board",
    )

    vsh_parser = subparsers.add_parser(
        "vsh",
        help="run the Virtual SH1107",
    )
    vsh_parser.set_defaults(func=vsh)
    vsh_parser.add_argument(
        "-i",
        "--i2c",
        action="store_true",
        help="simulate the full I2C protocol; by default it is replaced with a blackbox for speed",
    )
    vsh_parser.add_argument(
        "-c",
        "--compile",
        action="store_true",
        help="compile only; don't run",
    )
    vsh_parser.add_argument(
        "-s",
        "--speed",
        choices=[str(s) for s in OLED.VALID_SPEEDS],
        help="I2C bus speed to build at",
        default=str(OLED.DEFAULT_SPEED_VSH),
    )
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
    vsh_parser.add_argument(
        "-O",
        "--opt",
        action="store_true",
        help="build with -Doptimize=ReleaseFast",
    )

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    warnings.simplefilter("default")
    main()
