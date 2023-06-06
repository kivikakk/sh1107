from typing import Optional, cast

from amaranth import Elaboratable, Memory, Module, Record, Signal
from amaranth.build import Platform
from amaranth.hdl.mem import ReadPort
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

from common import Button, ButtonWithHold, Hz
from .oled import OLED

__all__ = ["Top"]

# msg1 = ("1234567890abcdef" * 15) + "1234567890abcde"
# MAIN_SEQUENCE = [
#     0x02,  # DISPLAY_OFF
#     0x03,  # CLS
#     0x01,  # DISPLAY_ON
#     0x04,
#     0x01,
#     0x01,  # LOCATE 1, 1
#     0x05,
#     len(msg1),
#     *[ord(c) for c in msg1],  # PRINT msg1
# ]

# msg1 = "123.123.ID: "
# msg2 = "/"
# MAIN_SEQUENCE = [
#     0x02,  # DISPLAY_OFF
#     0x03,  # CLS
#     0x01,  # DISPLAY_ON
#     0x04,
#     0x01,
#     0x01,  # LOCATE 1, 1
#     0x05,
#     len(msg1),
#     *[ord(c) for c in msg1],  # PRINT msg1
#     0x08,  # ID
#     0x05,
#     len(msg2),
#     *[ord(c) for c in msg2],  # PRINT msg2
#     0x02,  # DISPLAY_OFF
#     0x08,  # ID
#     0x01,  # DISPLAY_ON
# ]

msg1 = "Nyonk\n plonk"
msg2 = "14: Hej\n 15: Mm\n  16: Z!\n   17: :)"
MAIN_SEQUENCE = [
    0x02,  # DISPLAY_OFF
    0x03,  # CLS
    0x01,  # DISPLAY_ON
    0x04,
    0x01,
    0x01,  # LOCATE 1, 1
    0x05,
    len(msg1),
    *[ord(c) for c in msg1],  # PRINT msg1
    0x04,
    0x0E,
    0x01,  # LOCATE 14, 1
    0x05,
    len(msg2),
    *[ord(c) for c in msg2],  # PRINT msg2
    0x06,  # CURSOR_ON
]

SECONDARY_SEQUENCE = [0x05, 0x01, 0x0A]  # PRINT "\n"

# msg = "Hello, world! This should wrap correctly."
# MAIN_SEQUENCE = [
#     0x02,  # DISPLAY_OFF
#     0x03,  # CLS
#     0x01,  # DISPLAY_ON
#     0x04,
#     0x01,
#     0x01,  # LOCATE 1, 1
#     0x05,
#     0x01,
#     0x01,  # PRINT smiley
#     0x04,
#     0x02,
#     0x02,  # LOCATE 2, 2
#     0x05,
#     0x01,
#     0x01,  # PRINT smiley
#     0x04,
#     0x03,
#     0x03,  # LOCATE 3, 3
#     0x05,
#     len(msg),
#     *[ord(c) for c in msg],  # PRINT msg
#     0x06,  # CURSOR_ON
# ]


class Top(Elaboratable):
    oled: OLED
    main_sequence: list[int]
    secondary_sequence: list[int]
    speed: Hz
    build_i2c: bool

    main_switch: Signal
    secondary_switch: Signal

    rom_len: int
    rom_rd: ReadPort

    def __init__(
        self,
        *,
        main_sequence: list[int] = MAIN_SEQUENCE,
        secondary_sequence: list[int] = SECONDARY_SEQUENCE,
        speed: Hz = Hz(400_000),
        build_i2c: bool = False,
    ):
        self.oled = OLED(speed=speed, build_i2c=build_i2c)
        self.main_sequence = main_sequence
        self.secondary_sequence = secondary_sequence
        self.speed = speed
        self.build_i2c = build_i2c

        self.main_switch = Signal()
        self.secondary_switch = Signal()

        self.rom_len = len(main_sequence) + len(secondary_sequence)
        self.rom_rd = Memory(
            width=8,
            depth=self.rom_len,
            init=main_sequence + secondary_sequence,
        ).read_port(transparent=False)

    @property
    def ports(self) -> list[Signal]:
        ports = [
            self.main_switch,
            self.secondary_switch,
        ]
        if self.build_i2c:
            ports += [
                self.oled.i2c.scl_o,
                self.oled.i2c.scl_oe,
                self.oled.i2c.sda_o,
                self.oled.i2c.sda_oe,
                self.oled.i2c.sda_i,
            ]
        else:
            ports += [
                self.oled.i_i2c_bb_in_ack,
                self.oled.i_i2c_bb_in_out_fifo_data,
                self.oled.i_i2c_bb_in_out_fifo_stb,
            ]
        return ports

    def elaborate(self, platform: Optional[Platform]):
        m = Module()

        m.submodules.oled = self.oled
        m.submodules.rom_rd = self.rom_rd

        button_up_main: Signal
        button_up_secondary: Signal

        match platform:
            case ICEBreakerPlatform():
                led_busy = cast(Signal, platform.request("led", 0).o)
                led_ack = cast(Signal, platform.request("led", 1).o)

                m.d.comb += [
                    led_busy.eq(self.oled.i2c_bus.o_busy),
                    led_ack.eq(self.oled.i2c_bus.o_ack),
                ]

                main_switch = cast(Signal, platform.request("button", 0).i)
                m.submodules.button_main = button_main = Button()
                m.d.comb += button_main.i.eq(main_switch)
                button_up_main = button_main.o_up

                platform.add_resources(platform.break_off_pmod)
                secondary_switch = cast(Signal, platform.request("button", 1).i)
                m.submodules.button_secondary = button_secondary = Button()
                m.d.comb += button_secondary.i.eq(secondary_switch)
                button_up_secondary = button_secondary.o_up
                # led_l = platform.request("led_g", 1)
                # led_m = platform.request("led_r", 1)
                # led_r = platform.request("led_g", 2)

            case OrangeCrabR0_2_85FPlatform():
                rgb = platform.request("rgb_led")
                led_busy = cast(Signal, cast(Record, rgb.r).o)
                led_ack = cast(Signal, cast(Record, rgb.g).o)

                m.d.comb += [
                    led_busy.eq(self.oled.i2c_bus.o_busy),
                    led_ack.eq(self.oled.i2c_bus.o_ack),
                ]

                main_switch = cast(Signal, platform.request("button", 0).i)
                m.submodules.button_main = button_main = ButtonWithHold()
                m.d.comb += button_main.i.eq(main_switch)
                button_up_main = button_main.o_up

                program = cast(Signal, platform.request("program").o)
                with m.If(button_main.o_held):
                    m.d.sync += program.eq(1)

                secondary_switch = cast(Signal, platform.request("button", 1).i)
                m.submodules.button_secondary = button_secondary = ButtonWithHold()
                m.d.comb += button_secondary.i.eq(secondary_switch)
                button_up_secondary = button_secondary.o_up

            case None:
                buffer_main = Signal()
                button_up_main = Signal()
                m.d.sync += buffer_main.eq(self.main_switch)
                m.d.comb += button_up_main.eq(buffer_main & ~self.main_switch)

                buffer_secondary = Signal()
                button_up_secondary = Signal()
                m.d.sync += buffer_secondary.eq(self.secondary_switch)
                m.d.comb += button_up_secondary.eq(
                    buffer_secondary & ~self.secondary_switch
                )

            case _:
                raise NotImplementedError

        offset = Signal(range(self.rom_len))
        remain = Signal(range(self.rom_len))

        m.d.comb += self.rom_rd.addr.eq(offset)

        with m.FSM():
            with m.State("IDLE"):
                m.d.sync += self.oled.i_fifo.w_en.eq(0)
                with m.If(button_up_main & self.oled.i_fifo.w_rdy):
                    m.d.sync += [
                        offset.eq(0),
                        remain.eq(len(self.main_sequence)),
                    ]
                    m.next = "LOOP: ADDRESSED"

                with m.If(button_up_secondary & self.oled.i_fifo.w_rdy):
                    m.d.sync += [
                        offset.eq(len(self.main_sequence)),
                        remain.eq(len(self.secondary_sequence)),
                    ]
                    m.next = "LOOP: ADDRESSED"

            with m.State("LOOP: ADDRESSED"):
                m.next = "LOOP: AVAILABLE"

            with m.State("LOOP: AVAILABLE"):
                with m.If(self.oled.i_fifo.w_rdy):
                    m.d.sync += [
                        self.oled.i_fifo.w_data.eq(self.rom_rd.data),
                        self.oled.i_fifo.w_en.eq(1),
                    ]
                    m.next = "LOOP: STROBED W_EN"

            with m.State("LOOP: STROBED W_EN"):
                m.d.sync += self.oled.i_fifo.w_en.eq(0)
                with m.If(remain == 1):
                    m.next = "IDLE"
                with m.Else():
                    m.d.sync += [
                        offset.eq(offset + 1),
                        remain.eq(remain - 1),
                    ]
                    m.next = "LOOP: ADDRESSED"

        return m
