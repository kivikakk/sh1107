#!/usr/bin/env python

import test  # XXX(Ch): isort puts this here because of top-level test.  This in turn is because we don't have a separate package. Yuck?
import warnings
from argparse import ArgumentParser

import build
import formal
import vsh
from oled import rom


def main():
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


if __name__ == "__main__":
    warnings.simplefilter("default")
    main()
