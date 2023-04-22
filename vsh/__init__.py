from argparse import Namespace

from amaranth import Elaboratable

try:
    import pyglet  # noqa: F401

    from .display import run
except ModuleNotFoundError:

    def run(_top: Elaboratable, _args: Namespace):
        print("pyglet not found. Please `pip install pyglet` to use vsh.")


__all__ = ["run"]
