from pathlib import Path

__all__ = ["CHARS"]

FONT_FILE = "IBM_VGA_8x8.bin"
FONT_WIDTH = 8
FONT_HEIGHT = 8
assert (FONT_WIDTH * FONT_HEIGHT) % 8 == 0

with open(Path(__file__).parent / FONT_FILE, "rb") as f:
    rawfont = f.read()

CHARS: list[list[int]] = []

rawchar_size = (FONT_WIDTH * FONT_HEIGHT) // 8
for i in range(256):
    rawchar = rawfont[i * rawchar_size : (i + 1) * rawchar_size]
    assert len(rawchar) == FONT_HEIGHT
    CHARS.append(rawchar)
