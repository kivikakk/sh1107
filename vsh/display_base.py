from typing import Any, List, Literal, Tuple

import pyglet
from pyglet import gl
from pyglet.image import ImageData, Texture
from pyglet.text import HTMLLabel


class DisplayBase:
    voyager2: Texture

    I2C_WIDTH = 128
    I2C_HEIGHT = 128
    DISPLAY_SCALE = 4

    BORDER_WIDTH = 4
    PADDING = 10

    TOP_AREA = 112
    CHECKBOX_SIZE = 10
    CHECKBOX_TEXT_GAP = 6
    CHECKBOX_ACROSS = 80
    CHECKBOX_DOWN = 6

    TOP_COL_WIDTH = 142
    TOP_ROW_HEIGHT = 16

    ###

    BORDER_ALPHA = 240
    ALPHA = 200
    OFF = [0, 10, 50, ALPHA]
    OFF_BORDER = [64, 64, 64, BORDER_ALPHA]
    ON_BORDER = [192, 192, 192, BORDER_ALPHA]

    BLACK = [0, 10, 100, ALPHA]
    WHITE = [255, 255, 255, ALPHA]

    ###

    WINDOW_WIDTH = I2C_WIDTH * DISPLAY_SCALE + 2 * PADDING + 2 * BORDER_WIDTH
    WINDOW_HEIGHT = (
        I2C_HEIGHT * DISPLAY_SCALE + 2 * PADDING + 2 * BORDER_WIDTH + TOP_AREA
    )

    BORDER_FILL_WIDTH = I2C_WIDTH * DISPLAY_SCALE + 2 * BORDER_WIDTH
    BORDER_FILL_HEIGHT = I2C_HEIGHT * DISPLAY_SCALE + 2 * BORDER_WIDTH

    ###

    __texts: dict[Tuple[str, bool], HTMLLabel]

    ###

    off_border: ImageData
    on_border: ImageData
    unchecked: ImageData
    checked: ImageData

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        Texture.default_min_filter = Texture.default_mag_filter = gl.GL_LINEAR
        self.voyager2 = pyglet.resource.image("vsh/voyager2.jpg", atlas=False)
        Texture.default_min_filter = Texture.default_mag_filter = gl.GL_NEAREST

        self.__texts = {}

        pyglet.font.add_file("vsh/ibm3161-7f.ttf")

        self.__generate_textures()

    def __generate_textures(self):
        off_border = bytearray(
            self.OFF_BORDER * self.BORDER_FILL_WIDTH * self.BORDER_FILL_HEIGHT
        )
        for y in range(
            self.BORDER_WIDTH, self.I2C_HEIGHT * self.DISPLAY_SCALE + self.BORDER_WIDTH
        ):
            start = 4 * (y * self.BORDER_FILL_WIDTH + self.BORDER_WIDTH)
            end = start + 4 * self.I2C_WIDTH * self.DISPLAY_SCALE
            off_border[start:end] = bytearray(
                self.OFF * self.I2C_WIDTH * self.DISPLAY_SCALE
            )
        self.off_border = ImageData(
            self.BORDER_FILL_WIDTH, self.BORDER_FILL_HEIGHT, "RGBA", bytes(off_border)
        )

        on_border = bytearray(
            self.ON_BORDER * self.BORDER_FILL_WIDTH * self.BORDER_FILL_HEIGHT
        )
        for y in range(
            self.BORDER_WIDTH, self.I2C_HEIGHT * self.DISPLAY_SCALE + self.BORDER_WIDTH
        ):
            start = 4 * (y * self.BORDER_FILL_WIDTH + self.BORDER_WIDTH)
            end = start + 4 * self.I2C_WIDTH * self.DISPLAY_SCALE
            on_border[start:end] = bytearray(
                [0, 0, 0, 0] * self.I2C_WIDTH * self.DISPLAY_SCALE
            )

        self.on_border = ImageData(
            self.BORDER_FILL_WIDTH, self.BORDER_FILL_HEIGHT, "RGBA", bytes(on_border)
        )

        unchecked = bytearray(self.OFF_BORDER * self.CHECKBOX_SIZE * self.CHECKBOX_SIZE)
        for y in range(1, self.CHECKBOX_SIZE - 1):
            start = 4 * (y * self.CHECKBOX_SIZE + 1)
            end = start + 4 * (self.CHECKBOX_SIZE - 2)
            unchecked[start:end] = bytearray(self.OFF * (self.CHECKBOX_SIZE - 2))
        self.unchecked = ImageData(
            self.CHECKBOX_SIZE, self.CHECKBOX_SIZE, "RGBA", bytes(unchecked)
        )

        checked = bytearray(self.ON_BORDER * self.CHECKBOX_SIZE * self.CHECKBOX_SIZE)
        for y in range(1, self.CHECKBOX_SIZE - 1):
            start = 4 * (y * self.CHECKBOX_SIZE + 1)
            end = start + 4 * (self.CHECKBOX_SIZE - 2)
            checked[start:end] = bytearray(self.WHITE * (self.CHECKBOX_SIZE - 2))
        self.checked = ImageData(
            self.CHECKBOX_SIZE, self.CHECKBOX_SIZE, "RGBA", bytes(checked)
        )

    def render_text(
        self,
        text: str,
        color: List[int],
        *,
        x: int,
        y: int,
        anchor_x: Literal["left", "center", "right"] = "left",
        anchor_y: Literal["bottom", "baseline", "center", "top"] = "baseline",
        bold: bool = False,
    ) -> HTMLLabel:
        if bold:
            text = f"<b>{text}</b>"
        text = f"<font face='IBM 3161' real_size='8'>{text}</font>"

        key = (text, bold)

        if key not in self.__texts:
            self.__texts[key] = HTMLLabel(
                text,
                dpi=144,
                anchor_x=anchor_x,
                anchor_y=anchor_y,
            )
        t = self.__texts[key]
        if t.x != x:
            t.x = x
        if t.y != y:
            t.y = y
        if t.color != color:
            t.color = color
        if t.anchor_x != anchor_x:
            t.anchor_x = anchor_x
        if t.anchor_y != anchor_y:
            t.anchor_y = anchor_y
        return t
