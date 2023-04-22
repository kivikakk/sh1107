from typing import Callable, Optional

import sim
from oled import OLED
from oled.sh1107 import Base, Cmd, DataBytes
from .i2c_connector import I2CConnector
from .shared import HIGH_STATES, MED_STATES, track

__all__ = ["OLEDConnector"]


class OLEDConnector:
    oled: OLED
    process_cb: Callable[[list[Base | DataBytes]], None]
    addr: int

    i2c_connector: I2CConnector

    def __init__(
        self,
        oled: OLED,
        process_cb: Callable[[list[Base | DataBytes]], None],
        *,
        addr: int = 0x3C,
    ):
        self.oled = oled
        self.process_cb = process_cb
        self.addr = addr

        self.i2c_connector = I2CConnector(oled.i2c, addr)

    def sim_process(self) -> sim.Generator:
        parser: Optional[Cmd.Parser] = None

        while True:
            track(HIGH_STATES, "command", (yield self.oled.i_cmd), OLED.Command)

            track(HIGH_STATES, "result", (yield self.oled.o_result), OLED.Result)
            track(MED_STATES, "remain", (yield self.oled.remain))
            track(MED_STATES, "offset", (yield self.oled.offset))

            track(MED_STATES, "rom_rd.addr", (yield self.oled.rom_rd.addr))
            track(MED_STATES, "rom_rd.data", (yield self.oled.rom_rd.data))

            byte = yield from self.i2c_connector.sim_tick()
            match byte:
                case None:
                    pass

                case "addressed":
                    parser = Cmd.Parser()

                case "error":
                    parser = None

                case "fish":
                    if not parser or not parser.valid_finish:
                        print("command parser fish without valid_finish")
                    parser = None

                case byte:
                    assert parser
                    cmds = parser.feed([byte])
                    if parser.unrecoverable:
                        print(
                            "command parser noped out, resetting with: x",
                            "".join([f"{b:02x}" for b in parser.bytes]),
                            " -- partial_cmd: x",
                            "".join([f"{b:02x}" for b in parser.partial_cmd]),
                            " -- state: ",
                            parser.state,
                            " -- continuation: ",
                            parser.continuation,
                        )
                        parser = None
                        self.i2c_connector.reset()
                    self.process_cb(cmds)

            yield
