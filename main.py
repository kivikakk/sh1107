import sys
import subprocess
import traceback
from argparse import ArgumentParser

from amaranth import Elaboratable
from amaranth.back import rtlil
from amaranth.hdl import Fragment
from amaranth_boards.icebreaker import ICEBreakerPlatform

from .sim import prep as prep_sim
from .formal import formal as prep_formal
from .top import Top


def _outfile(ext):
    return sys.argv[0].replace(".py", ext)


def sim(_a):
    _, sim, traces = prep_sim()

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
        Top(),
        do_program=args.program,
        debug_verilog=args.verilog,
    )


def main():
    parser = ArgumentParser(prog="fpgaxp.oled.main")
    subparsers = parser.add_subparsers(required=True)

    sim_parser = subparsers.add_parser("sim", help="simulate the design")
    sim_parser.set_defaults(func=sim)

    formal_parser = subparsers.add_parser("formal", help="formally verify the design")
    formal_parser.set_defaults(func=formal)

    build_parser = subparsers.add_parser(
        "build", help="build the design, and optionally program it"
    )
    build_parser.add_argument("-p", "--program", action="store_true")
    build_parser.add_argument("-v", "--verilog", action="store_true")
    build_parser.set_defaults(func=build)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
