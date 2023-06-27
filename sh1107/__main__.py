import warnings
from argparse import ArgumentParser
from os import makedirs

from . import build, formal, rom, test, vsh
from .base import path

warnings.simplefilter("default")
makedirs(path("build"), exist_ok=True)

parser = ArgumentParser(prog="sh1107")
subparsers = parser.add_subparsers(required=True)


test.add_main_arguments(
    subparsers.add_parser(
        "test",
        help="run the unit tests and sim tests",
    )
)
formal.add_main_arguments(
    subparsers.add_parser(
        "formal",
        help="formally verify the design",
    )
)
build.add_main_arguments(
    subparsers.add_parser(
        "build",
        help="build the design, and optionally program it",
    )
)
rom.add_main_arguments(
    subparsers.add_parser(
        "rom",
        help="build the ROM image, and optionally program it",
    )
)
vsh.add_main_arguments(
    subparsers.add_parser(
        "vsh",
        help="run the Virtual SH1107",
    )
)

args = parser.parse_args()
args.func(args)
