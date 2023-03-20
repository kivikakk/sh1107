try:
    import pyglet  # noqa: F401

    from .display import run
except ModuleNotFoundError:

    def run(_args):
        print("pyglet not found. Please `pip install pyglet` to use vsh.")


__all__ = ["run"]
