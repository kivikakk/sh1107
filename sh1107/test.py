import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path
from unittest import TestLoader, TextTestRunner

__all__ = ["add_main_arguments"]


def add_main_arguments(parser: ArgumentParser):
    parser.set_defaults(func=main)
    parser.add_argument(
        "subpkg",
        nargs="?",
        help="run tests from a specific subpackage",
    )


def main(args: Namespace):
    package = "sh1107"
    if args.subpkg:
        package += f".{args.subpkg}"
    suite = TestLoader().discover(package, top_level_dir=Path(__file__).parent.parent)
    result = TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
