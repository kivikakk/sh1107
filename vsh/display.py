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
    dclk_freq: int  # NE
    dclk_ratio: int  # NE
    precharge_period: int  # NE
    discharge_period: int  # NE
    vcom_desel: int  # TODO
    all_on: bool  # TODO
    reversed: bool  # TODO
    contrast: int  # TODO
    start_line: int  # TODO
    start_column: int  # TODO
    page_address: int  # NOP
    column_address: int  # NOP
    addressing_mode: Literal[0, 1]  # NOP
    multiplex: int  # XXX
    segment_remap: bool
    com_scan_reversed: bool

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
        self.dclk_freq = 0
        self.dclk_ratio = 1
        self.precharge_period = 2
        self.discharge_period = 2
        self.vcom_desel = 0x35
        self.all_on = False
        self.reversed = False
        self.contrast = 0x80
        self.start_line = 0
        self.start_column = 0
        self.page_address = 0
        self.column_address = 0
        self.addressing_mode = 0
        self.multiplex = 128
        self.segment_remap = False
        self.com_scan_reversed = False

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
            ("dclk", lambda d: f"{d.dclk_freq}% {d.dclk_ratio}x"),
            ("pre/dis", lambda d: f"{d.precharge_period}/{d.discharge_period}"),
            ("vcom desel", lambda d: f"{d.vcom_desel:02x}"),
        ],
        [
            ("all on", lambda d: d.all_on),
            ("reversed", lambda d: d.reversed),
            ("contrast", lambda d: f"{d.contrast:02x}"),
        ],
        [
            ("start", lambda d: f"{d.start_line:02x}/{d.start_column:02x}"),
            ("address", lambda d: f"{d.page_address:02x}/{d.column_address:02x}"),
            ("mode", lambda d: "page" if d.addressing_mode == 0 else "column"),
            ("multiplex", lambda d: f"{d.multiplex:02x}"),
        ],
        [
            ("seg remap", lambda d: d.segment_remap),
            ("com rev", lambda d: d.com_scan_reversed),
        ],
    ]

    def _draw_top(self):
        left = self.PADDING

        for col in self.TOP_COLS:
            top = self.WINDOW_HEIGHT - self.PADDING
            for name, lamb in col:
                x = left

                val: bool | str = lamb(self)
                if isinstance(val, bool):
                    x += self.CHECKBOX_SIZE + self.CHECKBOX_TEXT_GAP
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
                    + (
                        self.I2C_WIDTH * self.DISPLAY_SCALE
                        if self.com_scan_reversed
                        else 0
                    )
                ),
                y=(
                    self.PADDING
                    + self.BORDER_WIDTH
                    + (
                        0
                        if self.segment_remap
                        else self.I2C_HEIGHT * self.DISPLAY_SCALE
                    )
                ),
                width=(
                    self.I2C_WIDTH
                    * self.DISPLAY_SCALE
                    * (-1 if self.com_scan_reversed else 1)
                ),
                height=(
                    self.I2C_HEIGHT
                    * self.DISPLAY_SCALE
                    * (1 if self.segment_remap else -1)
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
            self.segment_remap = not self.segment_remap
        if symbol == key.PAGEDOWN:
            self.com_scan_reversed = not self.com_scan_reversed

    def run(self):
        pyglet.app.run()


__all__ = ["run"]
