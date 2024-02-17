from typing import Optional, cast

from amaranth import Cat, Memory, Module, Record, Signal
from amaranth.build.res import ResourceError
from amaranth.hdl.mem import ReadPort
from amaranth.lib.wiring import Component, In, Signature

from ..base import Blackbox
from ..platform import Platform, icebreaker, orangecrab, vsh
from .common import Button, ButtonWithHold, Hz
from .oled import OLED

__all__ = ["Top"]

SEQUENCES: list[list[int]] = []

Cm = OLED.Command

# msg1 = ("1234567890abcdef" * 15) + "1234567890abcde"
# SEQUENCES.append([
#     Cm.DISPLAY_OFF,
#     Cm.CLS,
#     Cm.INIT,
#     Cm.LOCATE,
#     0x01,
#     0x01,
#     Cm.PRINT,
#     len(msg1),
#     *[ord(c) for c in msg1],
# ])

msg1 = "Nyonk\n plonk"
msg2 = "14: Hej\n 15: Mm\n  16: Z!\n   17: :)"
SEQUENCES.append(
    [
        Cm.DISPLAY_OFF,
        Cm.CLS,
        Cm.INIT,
        Cm.LOCATE,
        0x01,
        0x01,
        Cm.PRINT,
        len(msg1),
        *[ord(c) for c in msg1],
        Cm.LOCATE,
        0x0E,
        0x01,
        Cm.PRINT,
        len(msg2),
        *[ord(c) for c in msg2],
        Cm.CURSOR_ON,
    ]
)

msg3 = "/"
SEQUENCES.append(
    [
        Cm.ID,
        Cm.PRINT,
        len(msg3),
        *[ord(c) for c in msg3],
        Cm.DISPLAY_OFF,
        Cm.ID,
        Cm.DISPLAY_ON,
    ]
)

SEQUENCES.append(
    [
        Cm.CLS,
    ]
)

SEQUENCES.append(
    [
        # Cm.PRINT_BYTE,
        # 0x01,
        # Cm.PRINT_BYTE,
        # 0x23,
        # Cm.PRINT_BYTE,
        # 0x45,
        # Cm.PRINT_BYTE,
        # 0x67,
        # Cm.PRINT_BYTE,
        # 0x89,
        # Cm.PRINT_BYTE,
        # 0xAB,
        # Cm.PRINT_BYTE,
        # 0xCD,
        # Cm.PRINT_BYTE,
        # 0xEF,
        Cm.SPI_TEST,
    ]
)

# 5
SEQUENCES.append([Cm.CURSOR_ON])

# 6
SEQUENCES.append([Cm.CURSOR_OFF])


class Top(Component):
    _oled: OLED
    _sequences: list[list[int]]
    _speed: Hz

    _rom_len: int
    _rom_rd: ReadPort

    def __init__(
        self,
        *,
        platform: Platform,
        sequences: list[list[int]] = SEQUENCES,
        speed: Hz = Hz(400_000),
    ):
        self._sequences = sequences
        super().__init__(
            {
                # Note that these remain disconnected/unused when building for an
                # actual target.
                f"switch_{i}": In(1)
                for i in range(len(self._sequences))
            }
        )

        self._oled = OLED(platform=platform, speed=speed)
        self._speed = speed

        self._rom_len = sum(len(seq) for seq in sequences)
        rom_mem = Memory(
            width=8,
            depth=self._rom_len,
            init=[i for seq in sequences for i in seq],
        )
        self._rom_rd = rom_mem.read_port()

    @property
    def switches(self) -> list[Signal]:
        return [getattr(self, f"switch_{i}") for i in range(len(self._sequences))]

    def ports(self, platform: Platform) -> list[Signal]:
        ports = self.switches[:]

        if Blackbox.I2C not in platform.blackboxes:
            ports += [
                self._oled._i2c.hw_bus.scl_o,
                self._oled._i2c.hw_bus.scl_oe,
                self._oled._i2c.hw_bus.sda_o,
                self._oled._i2c.hw_bus.sda_oe,
                self._oled._i2c.hw_bus.sda_i,
            ]
        else:
            ports += [
                self._oled._i_i2c_bb_in_ack,
                self._oled._i_i2c_bb_in_out_fifo_data,
                self._oled._i_i2c_bb_in_out_fifo_stb,
            ]

        return ports

    def elaborate(self, platform: Optional[Platform]):
        m = Module()

        m.submodules.oled = self._oled
        m.submodules.rom_rd = self._rom_rd

        button_up_signals: list[Signal] = []

        match platform:
            case icebreaker():
                led_busy = cast(Signal, platform.request("led", 0).o)
                led_ack = cast(Signal, platform.request("led", 1).o)

                m.d.comb += [
                    led_busy.eq(self._oled.i2c_bus.busy),
                    led_ack.eq(self._oled.i2c_bus.ack),
                ]

                platform.add_resources(platform.break_off_pmod)

                for i, _ in enumerate(self.switches):
                    try:
                        switch = cast(Signal, platform.request("button", i).i)
                    except ResourceError:
                        break
                    else:
                        m.submodules[f"button_{i}"] = button = Button()
                        m.d.comb += button.i.eq(switch)
                        button_up_signals.append(button.up)

                led_l = platform.request("led_g", 1)
                led_m = platform.request("led_r", 1)
                led_r = platform.request("led_g", 2)

                m.d.comb += [
                    led_r.o.eq(self._oled.result[0]),
                    led_m.o.eq(self._oled.result[1]),
                    led_l.o.eq(0),
                ]

            case orangecrab():
                rgb = platform.request("rgb_led")
                led_busy = cast(Signal, cast(Record, rgb.r).o)
                led_ack = cast(Signal, cast(Record, rgb.g).o)

                m.d.comb += [
                    led_busy.eq(self._oled.i2c_bus.busy),
                    led_ack.eq(self._oled.i2c_bus.ack),
                ]

                main_switch = cast(Signal, platform.request("button", 0).i)
                m.submodules.button_0 = button_0 = ButtonWithHold()
                m.d.comb += button_0.i.eq(main_switch)
                button_up_signals.append(button_0.up)

                program = cast(Signal, platform.request("program").o)
                with m.If(button_0.held):
                    m.d.sync += program.eq(1)

                for i, _ in list(enumerate(self.switches))[1:]:
                    try:
                        switch = cast(Signal, platform.request("button", i).i)
                    except ResourceError:
                        break
                    else:
                        m.submodules[f"button_{i}"] = button = Button()
                        m.d.comb += button.i.eq(switch)
                        button_up_signals.append(button.up)

            case vsh():
                for i, switch in enumerate(self.switches):
                    buffer = Signal()
                    button_up = Signal()
                    m.d.sync += buffer.eq(switch)
                    m.d.comb += button_up.eq(buffer & ~switch)
                    button_up_signals.append(button_up)

            case _:
                raise NotImplementedError

        offset = Signal(range(self._rom_len))
        remain = Signal(range(self._rom_len))

        m.d.comb += self._rom_rd.addr.eq(offset)

        with m.FSM():
            with m.State("IDLE"):
                m.d.sync += self._oled.fifo_in.w_en.eq(0)

                for i, button_up in enumerate(button_up_signals):
                    with m.If(button_up & self._oled.fifo_in.w_rdy):
                        m.d.sync += [
                            offset.eq(sum(len(seq) for seq in self._sequences[:i])),
                            remain.eq(len(self._sequences[i])),
                        ]
                        m.next = "LOOP: ADDRESSED"

            with m.State("LOOP: ADDRESSED"):
                m.next = "LOOP: AVAILABLE"

            with m.State("LOOP: AVAILABLE"):
                with m.If(self._oled.fifo_in.w_rdy):
                    m.d.sync += [
                        self._oled.fifo_in.w_data.eq(self._rom_rd.data),
                        self._oled.fifo_in.w_en.eq(1),
                    ]
                    m.next = "LOOP: STROBED W_EN"

            with m.State("LOOP: STROBED W_EN"):
                m.d.sync += self._oled.fifo_in.w_en.eq(0)
                with m.If(remain == 1):
                    m.next = "IDLE"
                with m.Else():
                    m.d.sync += [
                        offset.eq(offset + 1),
                        remain.eq(remain - 1),
                    ]
                    m.next = "LOOP: ADDRESSED"

        return m
