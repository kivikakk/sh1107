import os
import subprocess
from argparse import ArgumentParser, Namespace
from enum import Enum
from pathlib import Path
from typing import cast

from amaranth import Elaboratable, Signal
from amaranth._toolchain.yosys import YosysBinary, find_yosys
from amaranth.back import rtlil

from .base import build_top, path
from .oled import OLED, rom
from .target import Target

__all__ = ["add_main_arguments"]


class _Optimize(Enum):
    none = "none"
    rtl = "rtl"
    zig = "zig"
    both = "both"

    def __str__(self):
        return self.value

    @property
    def opt_rtl(self) -> bool:
        return self in (self.rtl, self.both)

    @property
    def opt_zig(self) -> bool:
        return self in (self.zig, self.both)


def add_main_arguments(parser: ArgumentParser):
    parser.set_defaults(func=main)
    parser.add_argument(
        "-i",
        "--whitebox-i2c",
        dest="blackbox_i2c",
        action="store_false",
        help="simulate the full I2C protocol; by default it is replaced with a blackbox for speed",
    )
    parser.add_argument(
        "-f",
        "--whitebox-spifr",
        dest="blackbox_spifr",
        action="store_false",
        help="simulate the full SPI protocol for the flash reader; by default it is replaced with a blackbox for speed",
    )
    parser.add_argument(
        "-c",
        "--compile",
        action="store_true",
        help="compile only; don't run",
    )
    parser.add_argument(
        "-s",
        "--speed",
        choices=[str(s) for s in OLED.VALID_SPEEDS],
        help="I2C bus speed to build at",
        default=str(OLED.DEFAULT_SPEED_VSH),
    )
    parser.add_argument(
        "-t",
        "--top",
        help="which top-level module to simulate (default: sh1107.oled.Top)",
        default="sh1107.oled.Top",
    )
    parser.add_argument(
        "-v",
        "--vcd",
        action="store_true",
        help="output a VCD file",
    )
    parser.add_argument(
        "-O",
        "--_Optimize",
        type=_Optimize,
        choices=_Optimize,
        help="build RTL or Zig with optimizations (default: both)",
        default=_Optimize.both,
    )


def main(args: Namespace):
    # NOTE: builtin-yosys works better on Windows since osscad's yosys-config a)
    # doesn't execute cleanly as-is (bash script), and b) its answers are wrong
    # anyway (!!!).
    os.environ["AMARANTH_USE_YOSYS"] = "builtin"
    yosys = cast(YosysBinary, find_yosys(lambda _: True))

    design = build_top(args, Target["vsh"])

    black_boxes = {}
    if args.blackbox_i2c:
        with open(path("vsh/i2c_blackbox.il"), "r") as f:
            black_boxes["i2c"] = f.read()
    if args.blackbox_spifr:
        with open(path("vsh/spifr_blackbox.il"), "r") as f:
            black_boxes["spifr"] = f.read()
    else:
        with open(path("vsh/spifr_whitebox.il"), "r") as f:
            black_boxes["spifr_whitebox"] = f.read()

    cxxrtl_ccpath = path("build/sh1107.cc")
    _cxxrtl_convert_with_header(
        cxxrtl_ccpath,
        design,
        black_boxes=black_boxes,
        ports=getattr(design, "ports", []),
    )

    cc_opaths = {cxxrtl_ccpath: cxxrtl_ccpath.with_suffix(".o")}
    if args.blackbox_i2c:
        cc_opaths[path("vsh/i2c_blackbox.cc")] = path("build/i2c_blackbox.o")
    if args.blackbox_spifr:
        cc_opaths[path("vsh/spifr_blackbox.cc")] = path("build/spifr_blackbox.o")
    else:
        cc_opaths[path("vsh/spifr_whitebox.cc")] = path("build/spifr_whitebox.o")

    for ccpath, opath in cc_opaths.items():
        subprocess.run(
            [
                "zig",
                "c++",
                *(["-O3"] if args._Optimize.opt_rtl else []),
                "-DCXXRTL_INCLUDE_CAPI_IMPL",
                "-DCXXRTL_INCLUDE_VCD_CAPI_IMPL",
                "-I" + str(path(".")),
                "-I" + str(cast(Path, yosys.data_dir()) / "include"),
                "-c",
                ccpath,
                "-o",
                opath,
            ],
            check=True,
        )

    with open(path("vsh/src/rom.bin"), "wb") as f:
        f.write(rom.ROM_CONTENT)

    cmd: list[str] = ["zig", "build"]
    if not args.compile:
        cmd += ["run"]
    cmd += [
        *(["-Doptimize=ReleaseFast"] if args._Optimize.opt_zig else []),
        f"-Dyosys_data_dir={yosys.data_dir()}",
        f"-Dcxxrtl_lib_paths={','.join(str(opath) for opath in cc_opaths.values())}",
    ]
    if not args.compile:
        cmd += ["--"]
        if args.vcd:
            cmd += ["--vcd"]

    subprocess.run(cmd, cwd=path("vsh"), check=True)


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
