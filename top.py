from typing import Optional

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform

from .minor import Button
from .i2c import I2C


class Top(Elaboratable):
    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.i2c = self.i2c = i2c = I2C()

        if platform:
            self.led_busy = platform.request("led", 0)
            self.led_ack = platform.request("led", 1)
            m.d.comb += self.led_busy.eq(i2c.o_busy)
            m.d.comb += self.led_ack.eq(i2c.o_ack)

            self.switch = platform.request("button")
        else:
            self.switch = Signal()

        m.submodules.button = self.button = button = Button()
        m.d.comb += button.i_switch.eq(self.switch)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(button.o_up & i2c.fifo.w_rdy):
                    m.d.sync += i2c.i_addr.eq(0x3C)
                    m.d.sync += i2c.i_rw.eq(0)
                    m.d.sync += i2c.i_stb.eq(1)
                    m.d.sync += i2c.fifo.w_data.eq(0xAF)  # 0x00 later really
                    m.d.sync += i2c.fifo.w_en.eq(1)
                    m.next = "FIRST_DONE"
            with m.State("FIRST_DONE"):
                m.d.sync += i2c.i_stb.eq(0)
                m.d.sync += i2c.fifo.w_en.eq(0)
                # Wait until we need the next byte.
                m.next = "WAIT_SECOND"
            with m.State("WAIT_SECOND"):
                with m.If(i2c.fifo.w_rdy):
                    m.d.sync += i2c.fifo.w_data.eq(0x8C)  # 0xAF later really
                    m.d.sync += i2c.fifo.w_en.eq(1)
                    m.next = "SECOND_DONE"
            with m.State("SECOND_DONE"):
                m.d.sync += i2c.fifo.w_en.eq(0)
                m.next = "IDLE"

        return m
