from typing import Optional, cast

from amaranth import Signal

import sim
from oled import OLED, Top

__all__ = ["Connector"]


class Connector:
    top: Top

    press_button: bool

    _pressing_button: bool
    _known_last_command: Optional[OLED.Command]

    def __init__(self, top: Top):
        self.top = top

        self.press_button = False

        self._known_last_command = None
        self._pressing_button = False

    def sim_process(self) -> sim.Generator:
        switch = self.top.sim_switch

        scl_o = self.top.oled.i2c.scl_o
        scl_oe = self.top.oled.i2c.scl_oe
        sda_o = self.top.oled.i2c.sda_o
        sda_oe = self.top.oled.i2c.sda_oe
        sda_i = self.top.oled.i2c.sda_i

        last_sda = 0
        last_scl = 0
        last_result = OLED.Result.SUCCESS
        last_remain = 0
        last_offset = 0
        last_offlens_rd_addr = 0
        last_offlens_rd_data = 0

        while True:
            if self.press_button:
                self.press_button = False
                self._pressing_button = True
                yield switch.eq(1)
            elif self._pressing_button:
                self._pressing_button = False
                yield switch.eq(0)

            last_command_n = cast(int, (yield self.top.o_last_cmd))
            last_command = None if last_command_n == 0 else OLED.Command(last_command_n)
            if last_command and last_command != self._known_last_command:
                print(f"last command: {last_command.name}")
                self._known_last_command = last_command

            sda = yield sda_o
            scl = yield scl_o

            if sda != last_sda:
                print("sda: ", " -> ", sda)
                last_sda = sda

            if scl != last_scl:
                print("scl: ", " -> ", scl)
                last_scl = scl

            result = OLED.Result(cast(int, (yield self.top.oled.o_result)))
            if result != last_result:
                print("result: ", " -> ", result.name)
                last_result = result

            remain = cast(int, (yield self.top.oled.remain))
            if remain != last_remain:
                print("remain: ", " -> ", remain)
                last_remain = remain

            offset = cast(int, (yield self.top.oled.offset))
            if offset != last_offset:
                print("offset: ", " -> ", offset)
                last_offset = offset

            offlens_rd_addr = cast(int, (yield self.top.oled.offlens_rd.addr))
            if offlens_rd_addr != last_offlens_rd_addr:
                print("offlens_rd_addr: ", " -> ", offlens_rd_addr)
                last_offlens_rd_addr = offlens_rd_addr

            offlens_rd_data = cast(int, (yield self.top.oled.offlens_rd.data))
            if offlens_rd_data != last_offlens_rd_data:
                print("offlens_rd_data: ", " -> ", offlens_rd_data)
                last_offlens_rd_data = offlens_rd_data

            yield
