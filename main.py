import re
import sys
import subprocess
import traceback
from argparse import ArgumentParser
from typing import cast

from amaranth.back import rtlil
from amaranth.hdl import Fragment
from amaranth_boards.icebreaker import ICEBreakerPlatform

from .sim import BENCHES
from .i2c import Speed, SPEEDS
from .formal import formal as prep_formal
from .top import Top


def _outfile(ext):
    return sys.argv[0].replace(".py", ext)


def sim(args):
    _, sim, traces = BENCHES[args.bench](speed=cast(Speed, int(args.speed)))

    gtkw_file = _outfile(".gtkw")
    with sim.write_vcd(_outfile(".vcd"), gtkw_file=gtkw_file, traces=traces):
        try:
            sim.run()
        except AssertionError as e:
            traceback.print_exception(e)

    if sys.platform == "darwin":
        cmd = f"open {gtkw_file}"
    else:
        cmd = gtkw_file
    subprocess.run(cmd, shell=True)


def formal(_):
    design, ports = prep_formal()
    fragment = Fragment.get(design, None)
    output = rtlil.convert(fragment, ports=ports)
    with open(_outfile(".il"), "w") as f:
        f.write(output)

    sby_file = _outfile(".sby")
    subprocess.run(f"sby -f {sby_file}", shell=True)


def build(args):
    ICEBreakerPlatform().build(
        Top(speed=cast(Speed, int(args.speed))),
        do_program=args.program,
        debug_verilog=args.verilog,
    )
    heading = re.compile(r"^\d+\.\d+\. (.+)$", flags=re.MULTILINE)
    with open("build/top.rpt", "r") as f:
        dumping = False
        for line in f:
            md = heading.match(line)
            if dumping:
                if md:
                    break
                else:
                    print(line.rstrip())
            elif md:
                if md.group(1) == "Printing statistics.":
                    dumping = True


def main():
    parser = ArgumentParser(prog="fpgaxp.oled.main")
    subparsers = parser.add_subparsers(required=True)

    sim_parser = subparsers.add_parser(
        "sim",
        help="simulate the design",
    )
    sim_parser.set_defaults(func=sim)
    sim_parser.add_argument(
        "bench",
        choices=BENCHES.keys(),
        help="which bench to run",
    )
    sim_parser.add_argument(
        "-s",
        "--speed",
        choices=[str(s) for s in SPEEDS],
        help="bus speed to sim at",
        default=str(SPEEDS[0]),
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
        "-s",
        "--speed",
        choices=[str(s) for s in SPEEDS],
        help="bus speed to build at",
        default=str(SPEEDS[0]),
    )
    build_parser.add_argument(
        "-p",
        "--program",
        action="store_true",
        help="program the design onto the iCEBreaker",
    )
    build_parser.add_argument(
        "-v",
        "--verilog",
        action="store_true",
        help="output debug Verilog",
    )

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
