#!/usr/bin/env python

import importlib.util
import inspect
import os
import re
import subprocess
import sys
import warnings
from argparse import ArgumentParser, Namespace
from enum import Enum
from pathlib import Path
from typing import Any, Optional, cast
from unittest import TestLoader, TextTestRunner

from amaranth import Elaboratable, Signal
from amaranth._toolchain.yosys import YosysBinary, find_yosys
from amaranth.back import rtlil
from amaranth.hdl import Fragment

from base import Blackbox, Blackboxes, Config
from common import Hz
from formal import formal as prep_formal
from oled import OLED, ROM_CONTENT
from target import Target


class Optimize(Enum):
    none = 'none'
    rtl = 'rtl'
    zig = 'zig'
    both = 'both'

    def __str__(self):
        return self.value

    @property
    def opt_rtl(self) -> bool:
        return self in (self.rtl, self.both)

    @property
    def opt_zig(self) -> bool:
        return self in (self.zig, self.both)


def _args_target(args: Namespace | str) -> Target:
    name = args.target if isinstance(args, Namespace) else args
    return Target[name]


def _build_top(args: Namespace, target: Target, **kwargs: Any) -> Elaboratable:
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

    kwargs["config"] = Config(target=target, blackboxes=blackboxes)

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
    target = _args_target(args)

    component = _build_top(args, target)

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


def rom(args: Namespace):
    path = Path(__file__).parent / "rom.bin"
    with open(path, "wb") as f:
        f.write(ROM_CONTENT)

    if args.target:
        _args_target(args).flash_rom(path)


def _cxxrtl_convert_with_header(
    cc_out: Path,
    design: Elaboratable,
    *,
    black_boxes: dict[str, str],
    ports: list[Signal],
) -> None:
    if cc_out.is_absolute():
        try:
            cc_out = cc_out.relative_to(Path.cwd())
        except ValueError:
            raise AssertionError(
                "cc_out must be relative to cwd for builtin-yosys to write to it"
            )
    rtlil_text = rtlil.convert(design, ports=ports)
    yosys = find_yosys(lambda ver: ver >= (0, 10))
    script = []
    for box_source in black_boxes.values():
        script.append(f"read_rtlil <<rtlil\n{box_source}\nrtlil")
    script.append(f"read_rtlil <<rtlil\n{rtlil_text}\nrtlil")
    script.append(f"write_cxxrtl -header {cc_out}")
    yosys.run(["-q", "-"], "\n".join(script))


def vsh(args: Namespace):
    # NOTE: builtin-yosys works better on Windows since osscad's yosys-config a)
    # doesn't execute cleanly as-is (bash script), and b) its answers are wrong
    # anyway (!!!).
    os.environ["AMARANTH_USE_YOSYS"] = "builtin"
    yosys = cast(YosysBinary, find_yosys(lambda _: True))

    design = _build_top(args, _args_target("vsh"))

    black_boxes = {}
    if args.blackbox_i2c:
        with open(_path("vsh/i2c_blackbox.il"), "r") as f:
            black_boxes["i2c"] = f.read()
    if args.blackbox_spifr:
        with open(_path("vsh/spifr_blackbox.il"), "r") as f:
            black_boxes["spifr"] = f.read()
    else:
        with open(_path("vsh/spifr_whitebox.il"), "r") as f:
            black_boxes["spifr_whitebox"] = f.read()

    cxxrtl_cc_path = _path("build/sh1107.cc")
    _cxxrtl_convert_with_header(
        cxxrtl_cc_path,
        design,
        black_boxes=black_boxes,
        ports=getattr(design, "ports", []),
    )

    cc_o_paths = {cxxrtl_cc_path: cxxrtl_cc_path.with_suffix(".o")}
    if args.blackbox_i2c:
        cc_o_paths[_path("vsh/i2c_blackbox.cc")] = _path("build/i2c_blackbox.o")
    if args.blackbox_spifr:
        cc_o_paths[_path("vsh/spifr_blackbox.cc")] = _path("build/spifr_blackbox.o")
    else:
        cc_o_paths[_path("vsh/spifr_whitebox.cc")] = _path("build/spifr_whitebox.o")

    for cc_path, o_path in cc_o_paths.items():
        subprocess.run(
            [
                "zig",
                "c++",
                *(["-O3"] if args.optimize.opt_rtl else []),
                "-DCXXRTL_INCLUDE_CAPI_IMPL",
                "-DCXXRTL_INCLUDE_VCD_CAPI_IMPL",
                "-I" + str(_path(".")),
                "-I" + str(cast(Path, yosys.data_dir()) / "include"),
                "-c",
                cc_path,
                "-o",
                o_path,
            ],
            check=True,
        )

    with open(Path(__file__).parent / "vsh" / "src" / "rom.bin", "wb") as f:
        f.write(ROM_CONTENT)

    cmd: list[str] = ["zig", "build"]
    if not args.compile:
        cmd += ["run"]
    cmd += [
        *(["-Doptimize=ReleaseFast"] if args.optimize.opt_zig else []),
        f"-Dyosys_data_dir={yosys.data_dir()}",
        f"-Dcxxrtl_lib_paths={','.join(str(o_path) for o_path in cc_o_paths.values())}",
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
        "target",
        choices=Target.platform_targets,
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
        dest="target",
        choices=Target.platform_targets,
        help="program the ROM onto the specified board",
    )

    vsh_parser = subparsers.add_parser(
        "vsh",
        help="run the Virtual SH1107",
    )
    vsh_parser.set_defaults(func=vsh)
    vsh_parser.add_argument(
        "-i",
        "--whitebox-i2c",
        dest="blackbox_i2c",
        action="store_false",
        help="simulate the full I2C protocol; by default it is replaced with a blackbox for speed",
    )
    vsh_parser.add_argument(
        "-f",
        "--whitebox-spifr",
        dest="blackbox_spifr",
        action="store_false",
        help="simulate the full SPI protocol for the flash reader; by default it is replaced with a blackbox for speed",
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
        "--optimize",
        type=Optimize,
        choices=Optimize,
        help="build RTL or Zig with optimizations (default: both)",
        default=Optimize.both,
    )

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    warnings.simplefilter("default")
    main()
