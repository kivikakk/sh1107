from typing import Literal, List, Tuple, Callable, Self

import pyglet
from pyglet import gl
from pyglet.image import Texture, ImageData
from pyglet.window import key, Window

from .display_base import DisplayBase

# from ..oled import SH1107Command


def run(_args):
    v = Display()
    v.set_px(0, 0, 1)
    v.set_px(10, 10, 1)
    v.set_px(11, 10, 1)
    v.set_px(12, 10, 1)
    v.set_px(13, 10, 1)
    v.set_px(125, 125, 1)
    v.set_px(126, 126, 1)
    v.set_px(127, 127, 1)
    v.run()


class Display(DisplayBase, Window):
    voyager2: Texture

    power: bool
    all_on: bool
    reversed: bool
    start_line: int
    start_column: int
    y_flipped: bool
    x_flipped: bool

    idata: bytearray
    img: ImageData
    img_stale: bool

    def __init__(self):
        super().__init__(
            width=self.WINDOW_WIDTH,
            height=self.WINDOW_HEIGHT,
            caption="SH1107 OLED I²C",
        )

        Texture.default_min_filter = Texture.default_mag_filter = gl.GL_LINEAR
        self.voyager2 = pyglet.resource.image("vsh/voyager2.jpg", atlas=False)
        Texture.default_min_filter = Texture.default_mag_filter = gl.GL_NEAREST

        self.power = False
        self.all_on = False
        self.reversed = False
        self.start_line = 0
        self.start_column = 0
        self.y_flipped = False
        self.x_flipped = False

        self.idata = bytearray(self.BLACK * self.I2C_WIDTH * self.I2C_HEIGHT)
        self.img = ImageData(self.I2C_WIDTH, self.I2C_HEIGHT, "RGBA", bytes(self.idata))
        self.img_stale = False

    def on_draw(self):
        self.voyager2.blit(0, 0, width=self.WINDOW_WIDTH, height=self.WINDOW_HEIGHT)

        self._draw_top()
        self._draw_oled()

    TOP_COLS: List[List[Tuple[str, Callable[[Self], bool | str]]]] = [
        [
            ("power on", lambda d: d.power),
        ],
        [
            ("all on", lambda d: d.all_on),
            ("reversed", lambda d: d.reversed),
        ],
        [
            ("start", lambda d: f"{d.start_line:02x}/{d.start_column:02x}"),
        ],
        [
            ("y flipped", lambda d: d.y_flipped),
            ("x flipped", lambda d: d.x_flipped),
        ],
    ]

    def _draw_top(self):
        left = self.PADDING

        for col in self.TOP_COLS:
            top = self.WINDOW_HEIGHT - self.PADDING
            for name, lamb in col:
                x = left + self.CHECKBOX_SIZE + self.CHECKBOX_TEXT_GAP

                val: bool | str = lamb(self)
                if isinstance(val, bool):
                    self.render_text(
                        name, self.WHITE, x=x, y=top, anchor_y="center", bold=val
                    ).draw()
                    (self.checked if val else self.unchecked).blit(
                        left, top - self.CHECKBOX_DOWN
                    )
                else:
                    label = self.render_text(
                        f"{name}: <b>{val}</b>",
                        self.WHITE,
                        x=x,
                        y=top,
                        anchor_y="center",
                    )
                    label.draw()

                top -= self.TOP_ROW_HEIGHT

            left += self.TOP_COL_WIDTH

    def _draw_oled(self):
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

        if self.img_stale:
            self.img.set_data("RGBA", 4 * self.I2C_WIDTH, bytes(self.idata))
            self.img_stale = False

        if self.power:
            self.on_border.blit(
                self.PADDING,
                self.PADDING,
                width=self.BORDER_FILL_WIDTH,
                height=self.BORDER_FILL_HEIGHT,
            )
            self.img.blit(
                x=(
                    self.PADDING
                    + self.BORDER_WIDTH
                    + (self.I2C_WIDTH * self.DISPLAY_SCALE if self.x_flipped else 0)
                ),
                y=(
                    self.PADDING
                    + self.BORDER_WIDTH
                    + (self.I2C_HEIGHT * self.DISPLAY_SCALE if self.y_flipped else 0)
                ),
                width=(
                    self.I2C_WIDTH * self.DISPLAY_SCALE * (-1 if self.x_flipped else 1)
                ),
                height=(
                    self.I2C_HEIGHT * self.DISPLAY_SCALE * (-1 if self.y_flipped else 1)
                ),
            )
        else:
            self.off_border.blit(
                self.PADDING,
                self.PADDING,
                width=self.BORDER_FILL_WIDTH,
                height=self.BORDER_FILL_HEIGHT,
            )

    def set_px(self, x: int, y: int, val: Literal[0, 1]):
        off = 4 * (y * self.I2C_HEIGHT + x)
        self.idata[off : off + 4] = self.WHITE if val else self.BLACK
        self.img_stale = True

    def i2c_msg(self, msg: List[int]):
        if msg == [0, 0xAE]:
            self.power = False
        # TODO: clk div?
        # TODO: multiplex?
        # TODO: display start_line/start line/seg remap?
        # TODO: contrast?
        # TODO: vcom deselect?
        # TODO: non-inverted?
        elif msg == [0, 0xAF]:
            self.power = True

    def on_key_press(self, symbol, _modifiers):
        if symbol == key.ESCAPE:
            self.dispatch_event("on_close")
            return

        if symbol == key.RETURN:
            # TODO: Send the button push
            self.power = not self.power

        if symbol == key.PAGEUP:
            self.y_flipped = not self.y_flipped
        if symbol == key.PAGEDOWN:
            self.x_flipped = not self.x_flipped

    def run(self):
        pyglet.app.run()


__all__ = ["run"]
