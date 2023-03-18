from typing import List
from contextlib import contextmanager

from amaranth.lib.enum import IntEnum


class _Writer:
    def __init__(self):
        self.buf = []

    def write(self, cmd: List[int]):
        self.buf.extend(Command.write(cmd))

    def done(self) -> List[int]:
        self.buf.append(Command.FINISH)
        return self.buf


class Command(IntEnum):
    NOP = 0x00
    # 0x01 ~ 0x81: Write that many bytes
    FINISH = 0xFF

    @staticmethod
    def write(cmd: List[int]) -> List[int]:
        assert 1 <= len(cmd) <= 0x81
        for c in cmd:
            assert 0 <= c <= 0xFF
        return [len(cmd)] + cmd

    @contextmanager
    def writer():
        yield _Writer()


__all__ = ["Command"]
