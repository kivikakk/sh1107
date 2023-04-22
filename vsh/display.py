from argparse import Namespace
from pathlib import Path
from typing import Callable, Literal, Optional, Self, Tuple

import pyglet
from amaranth import Elaboratable, Signal
from amaranth.sim import Simulator
from pyglet import gl
from pyglet.image import ImageData
from pyglet.window import Window, key

from oled import OLED
from oled.sh1107 import Base, Cmd, DataBytes
from .display_base import DisplayBase
from .oled_connector import OLEDConnector
from .switch_connector import SwitchConnector

__all__ = ["run"]


def run(top: Elaboratable, args: Namespace):
    simulator = Simulator(top)

    v = Display(top, simulator)

    # 1Mbps on a 4MHz system clock gets us the sweet spot
    # where the I2C clock (2MHz) is at a 1:2 ratio with the
    # system clock.  This means every tick is either "half"
    # or "full".
    simulator.add_clock(1 / 4e6)
    if v.switch_connector:
        simulator.add_sync_process(v.switch_connector.sim_process)
    if v.oled_connector:
        simulator.add_sync_process(v.oled_connector.sim_process)

    if args.vcd:
        vcd_path = Path(__file__).parent.parent / "build" / "vsh.vcd"
        with simulator.write_vcd(str(vcd_path)):
            v.run()
    else:
        v.run()


class Display(DisplayBase, Window):
    top: Elaboratable
    simulator: Simulator
    press_button: bool

    switch_connector: Optional[SwitchConnector]
    oled_connector: Optional[OLEDConnector]

    power: bool
    dcdc: bool  # NE
    dclk_freq: Cmd.SetDisplayClockFrequency.Freq  # NE
    dclk_ratio: int  # NE
    precharge_period: int  # NE
    discharge_period: int  # NE
    vcom_desel: int  # TODO
    all_on: bool  # TODO
    reversed: bool  # TODO
    contrast: int  # TODO
    start_line: int  # TODO
    start_column: int  # TODO
    page_address: int
    column_address: int
    addressing_mode: Cmd.SetMemoryAddressingMode.Mode
    multiplex: int  # XXX
    segment_remap: bool
    com_scan_reversed: bool

    idata: bytearray
    img: ImageData
    img_stale: bool

    def __init__(self, top: Elaboratable, simulator: Simulator):
        super().__init__(
            width=self.WINDOW_WIDTH,
            height=self.WINDOW_HEIGHT,
            caption="SH1107 OLED I²C",
        )

        self.top = top
        self.simulator = simulator

        switch = getattr(top, "switch", None)
        if switch is not None:
            assert isinstance(switch, Signal)
            self.switch_connector = SwitchConnector(switch)

        oled = getattr(top, "oled", None)
        if oled is not None:
            assert isinstance(oled, OLED)
            self.oled_connector = OLEDConnector(oled, self.process_i2c)

        self.power = False
        self.dcdc = True
        self.dclk_freq = Cmd.SetDisplayClockFrequency.Freq.Zero
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
        self.addressing_mode = Cmd.SetMemoryAddressingMode.Mode.Page
        self.multiplex = 128
        self.segment_remap = False
        self.com_scan_reversed = False

        self.idata = bytearray(self.BLACK * self.I2C_WIDTH * self.I2C_HEIGHT)
        self.img = ImageData(self.I2C_WIDTH, self.I2C_HEIGHT, "RGBA", bytes(self.idata))
        self.img_stale = False

    def run(self):
        pyglet.app.run()

    def on_draw(self):  # pyright: reportIncompatibleMethodOverride=none
        # TODO(ari): range(?)
        for _ in range(1000):
            self.simulator.advance()

        self.voyager2.blit(0, 0, width=self.WINDOW_WIDTH, height=self.WINDOW_HEIGHT)
        self._draw_top()
        self._draw_oled()

    TOP_COLS: list[list[Tuple[str, Callable[[Self], bool | str]]]] = [
        [
            ("power on", lambda d: d.power),
            ("dc/dc on", lambda d: d.dcdc),
            ("dclk", lambda d: f"{int(d.dclk_freq)}% {d.dclk_ratio}x"),
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
                    + self.I2C_HEIGHT * self.DISPLAY_SCALE
                ),
                width=(
                    self.I2C_WIDTH
                    * self.DISPLAY_SCALE
                    * (-1 if self.com_scan_reversed else 1)
                ),
                height=(self.I2C_HEIGHT * self.DISPLAY_SCALE * (-1)),
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

    def process_i2c(self, msg: list[Base | DataBytes]):
        for c in msg:
            match c:
                case Cmd.SetLowerColumnAddress(lower=lower):
                    self.column_address = (self.column_address & 0xF0) | lower

                case Cmd.SetHigherColumnAddress(higher=higher):
                    self.column_address = (self.column_address & 0x0F) | (higher << 4)

                case Cmd.SetMemoryAddressingMode(mode=mode):
                    self.addressing_mode = mode

                case Cmd.SetContrastControlRegister(level=level):
                    self.contrast = level

                case Cmd.SetSegmentRemap(adc=adc):
                    self.segment_remap = adc == Cmd.SetSegmentRemap.Adc.Flipped

                case Cmd.SetMultiplexRatio(ratio=ratio):
                    self.multiplex = ratio

                case Cmd.SetEntireDisplayOn(on=on):
                    self.all_on = on

                case Cmd.SetDisplayReverse(reverse=reverse):
                    self.reversed = reverse

                case Cmd.SetDisplayOffset(offset=offset):
                    self.start_line = offset

                case Cmd.SetDCDC(on=on):
                    self.dcdc = on

                case Cmd.DisplayOn(on=on):
                    self.power = on

                case Cmd.SetPageAddress(page=page):
                    self.page_address = page

                case Cmd.SetCommonOutputScanDirection(direction=direction):
                    self.com_scan_reversed = (
                        direction
                        == Cmd.SetCommonOutputScanDirection.Direction.Backwards
                    )

                case Cmd.SetDisplayClockFrequency(ratio=ratio, freq=freq):
                    self.dclk_freq = freq
                    self.dclk_ratio = ratio

                case Cmd.SetPreDischargePeriod(
                    precharge=precharge, discharge=discharge
                ):
                    self.precharge_period = precharge
                    self.discharge_period = discharge

                case Cmd.SetVCOMDeselectLevel(level=level):
                    self.vcom_desel = level

                case Cmd.SetDisplayStartColumn(column=column):
                    self.start_column = column

                case Cmd.ReadModifyWrite():
                    raise NotImplementedError

                case Cmd.End():
                    raise NotImplementedError

                case Cmd.Nop():
                    pass

                case DataBytes(data=data):
                    page_count = self.I2C_HEIGHT // 8
                    for b in data:
                        for i in range(7, -1, -1):
                            if not self.segment_remap:
                                pa = self.page_address * 8 + i
                            else:
                                pa = (page_count - self.page_address - 1) * 8 + (7 - i)
                            self.set_px(
                                self.column_address,
                                pa,
                                1 if ((b >> i) & 0x01) == 0x01 else 0,
                            )
                        if (
                            self.addressing_mode
                            == Cmd.SetMemoryAddressingMode.Mode.Page
                        ):
                            self.column_address = (
                                self.column_address + 1
                            ) % self.I2C_WIDTH
                        else:
                            self.page_address = (self.page_address + 1) % page_count

                case Base():
                    assert False

    def on_key_press(self, symbol: int, modifiers: int):
        if symbol == key.ESCAPE:
            self.dispatch_event("on_close")
            return

        if symbol == key.RETURN:
            assert self.switch_connector
            self.switch_connector.press()
