from typing import Optional, cast

from amaranth import Elaboratable, Memory, Module, Record, Signal
from amaranth.build import Platform
from amaranth.hdl.mem import ReadPort
from amaranth_boards.icebreaker import ICEBreakerPlatform
from amaranth_boards.orangecrab_r0_2 import OrangeCrabR0_2_85FPlatform

from common import Button, ButtonWithHold, Hz
from .oled import OLED

__all__ = ["Top"]

SEQUENCES: list[list[int]] = []

# msg1 = ("1234567890abcdef" * 15) + "1234567890abcde"
# SEQUENCES.append([
#     0x02,  # DISPLAY_OFF
#     0x03,  # CLS
#     0x01,  # DISPLAY_ON
#     0x04,
#     0x01,
#     0x01,  # LOCATE 1, 1
#     0x05,
#     len(msg1),
#     *[ord(c) for c in msg1],  # PRINT msg1
# ])

# msg1 = "123.123.ID: "
# msg2 = "/"
# SEQUENCES.append([
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
# ])

msg1 = "Nyonk\n plonk"
msg2 = "14: Hej\n 15: Mm\n  16: Z!\n   17: :)"
SEQUENCES.append(
    [
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
)

SEQUENCES.append([0x05, 0x01, 0x0A])  # PRINT "\n"

msg3 = "SHOMK"
SEQUENCES.append([0x05, len(msg3), *[ord(c) for c in msg3]])  # PRINT msg3

# msg = "Hello, world! This should wrap correctly."
# SEQUENCES.append([
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
# ])


class Top(Elaboratable):
    oled: OLED
    sequences: list[list[int]]
    speed: Hz
    build_i2c: bool

    switches: list[Signal]

    rom_len: int
    rom_rd: ReadPort

    def __init__(
        self,
        *,
        sequences: list[list[int]] = SEQUENCES,
        speed: Hz = Hz(400_000),
        build_i2c: bool = False,
    ):
        self.oled = OLED(speed=speed, build_i2c=build_i2c)
        self.sequences = sequences
        self.speed = speed
        self.build_i2c = build_i2c

        self.switches = [Signal(name=f"switch_{i}") for i, _ in enumerate(sequences)]

        self.rom_len = sum(len(seq) for seq in sequences)
        self.rom_rd = Memory(
            width=8,
            depth=self.rom_len,
            init=[i for seq in sequences for i in seq],
        ).read_port(transparent=False)

    @property
    def ports(self) -> list[Signal]:
        ports = self.switches[:]

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

        button_up_signals: list[Signal] = []

        match platform:
            case ICEBreakerPlatform():
                led_busy = cast(Signal, platform.request("led", 0).o)
                led_ack = cast(Signal, platform.request("led", 1).o)

                m.d.comb += [
                    led_busy.eq(self.oled.i2c_bus.o_busy),
                    led_ack.eq(self.oled.i2c_bus.o_ack),
                ]

                platform.add_resources(platform.break_off_pmod)

                for i, _ in enumerate(self.switches):
                    switch = cast(Signal, platform.request("button", i).i)
                    m.submodules[f"button_{i}"] = button = Button()
                    m.d.comb += button.i.eq(switch)
                    button_up_signals.append(button.o_up)

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
                m.submodules.button_0 = button_0 = ButtonWithHold()
                m.d.comb += button_0.i.eq(main_switch)
                button_up_signals.append(button_0.o_up)

                program = cast(Signal, platform.request("program").o)
                with m.If(button_0.o_held):
                    m.d.sync += program.eq(1)

                for i, _ in list(enumerate(self.switches))[1:]:
                    switch = cast(Signal, platform.request("button", i).i)
                    m.submodules[f"button_{i}"] = button = Button()
                    m.d.comb += button.i.eq(switch)
                    button_up_signals.append(button.o_up)

            case None:
                for i, switch in enumerate(self.switches):
                    buffer = Signal()
                    button_up = Signal()
                    m.d.sync += buffer.eq(switch)
                    m.d.comb += button_up.eq(buffer & ~switch)
                    button_up_signals.append(button_up)

            case _:
                raise NotImplementedError

        offset = Signal(range(self.rom_len))
        remain = Signal(range(self.rom_len))

        m.d.comb += self.rom_rd.addr.eq(offset)

        with m.FSM():
            with m.State("IDLE"):
                m.d.sync += self.oled.i_fifo.w_en.eq(0)

                for i, button_up in enumerate(button_up_signals):
                    with m.If(button_up & self.oled.i_fifo.w_rdy):
                        m.d.sync += [
                            offset.eq(sum(len(seq) for seq in self.sequences[:i])),
                            remain.eq(len(self.sequences[i])),
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
