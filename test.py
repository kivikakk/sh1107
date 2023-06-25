import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path
from unittest import TestLoader, TextTestRunner


def add_main_arguments(parser: ArgumentParser):
    parser.set_defaults(func=test_main)
    parser.add_argument(
        "dir",
        nargs="?",
        help="run tests from a specific subdirectory",
    )


def test_main(args: Namespace):
    top = path = Path(__file__).parent
    if args.dir:
        path /= args.dir
    loader = TestLoader()
    suite = loader.discover(str(path), top_level_dir=str(top))
    result = TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
