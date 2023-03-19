from typing import Literal, List

import pyglet
from pyglet.window import key

# from ..oled import SH1107Command


def run(_args):
    v = VirtualSH1107()
    v.set_px(0, 0, 1)
    v.set_px(10, 10, 1)
    v.set_px(11, 10, 1)
    v.set_px(12, 10, 1)
    v.set_px(13, 10, 1)
    v.set_px(125, 125, 1)
    v.set_px(126, 126, 1)
    v.set_px(127, 127, 1)
    v.run()


pyglet.image.Texture.default_min_filter = pyglet.gl.GL_NEAREST
pyglet.image.Texture.default_mag_filter = pyglet.gl.GL_NEAREST


class VirtualSH1107(pyglet.window.Window):
    BLACK = [0, 10, 50]
    WHITE = [255, 255, 255]

    idata: bytearray
    power: bool

    img: pyglet.image.ImageData
    img_stale: bool

    def __init__(self):
        super().__init__(width=540, height=540)

        self.idata = bytearray(self.BLACK * 128 * 128)
        self.power = False

        self.img = pyglet.image.ImageData(128, 128, "RGB", bytes(self.idata))
        self.img_stale = False

    def on_draw(self):
        self.clear()
        if self.img_stale:
            self.img.set_data("RGB", 3 * 128, bytes(self.idata))
            self.img_stale = False
        if self.power:
            self.img.blit(14, 14, width=512, height=512)

    def set_px(self, x: int, y: int, val: Literal[0, 1]):
        off = 3 * (y * 128 + x)
        self.idata[off : off + 3] = self.WHITE if val else self.BLACK
        self.img_stale = True

    def i2c_msg(self, msg: List[int]):
        if msg == [0, 0xAE]:
            self.power = False
        # TODO: clk div?
        # TODO: multiplex?
        # TODO: display offset/start line/seg remap?
        # TODO: contrast?
        # TODO: vcom deselect?
        # TODO: non-inverted?
        elif msg == [0, 0xAF]:
            self.power = True

    def on_key_press(self, symbol, modifiers):
        if symbol == key.ESCAPE and not (
            modifiers & ~(key.MOD_NUMLOCK | key.MOD_CAPSLOCK | key.MOD_SCROLLLOCK)
        ):
            self.dispatch_event("on_close")
            return

        if symbol == key.RETURN:
            # TODO: Send the button push
            pass

    def run(self):
        pyglet.app.run()


__all__ = ["run"]
