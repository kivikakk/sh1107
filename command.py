from typing import List
from contextlib import contextmanager

from amaranth.lib.enum import IntEnum

from .sh1107 import SH1107Command


class _Writer:
    def __init__(self):
        self.buf = []

    def write(self, cmd: List[int | SH1107Command]):
        self.buf.extend(Command.write(cmd))

    def done(self) -> List[int]:
        self.buf.append(Command.FINISH)
        return self.buf


class Command(IntEnum):
    NOP = 0x00
    # 0x01 ~ 0x81: Write that many bytes
    FINISH = 0xFF

    @staticmethod
    def write(cmd: List[int | SH1107Command]) -> List[int]:
        out: List[int] = []
        for c in cmd:
            if isinstance(c, SH1107Command):
                out.extend(c.to_bytes())
            else:
                assert 0 <= c <= 0xFF
                out.append(c)
        assert 1 <= len(out) <= 0x81
        return [len(out)] + out

    @contextmanager
    def writer():
        yield _Writer()


__all__ = ["Command"]
