from typing import Optional

from amaranth import Elaboratable, Module, Signal
from amaranth.build import Platform

from common import Hz
from .i2c import I2C


class TestI2CTop(Elaboratable):
    data: list[int]
    speed: Hz
    switch: Signal
    aborted_at: Signal

    def __init__(self, data: list[int], *, speed: Hz):
        assert len(data) >= 1
        for datum in data:
            assert 0 <= datum <= 0x1FF
        self.data = data
        self.speed = speed
        self.switch = Signal()
        self.aborted_at = Signal(range(len(data)))

    def elaborate(self, platform: Optional[Platform]) -> Module:
        m = Module()

        m.submodules.i2c = self.i2c = i2c = I2C(speed=self.speed)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.switch):
                    m.d.sync += i2c.fifo.w_data.eq(self.data[0])
                    m.d.sync += i2c.fifo.w_en.eq(1)
                    m.next = "START: W_EN LATCHED"

            with m.State("START: W_EN LATCHED"):
                m.d.sync += i2c.fifo.w_en.eq(0)
                m.d.sync += i2c.i_stb.eq(1)
                m.next = "START: STROBED"

            with m.State("START: STROBED"):
                m.d.sync += i2c.i_stb.eq(0)
                m.next = "LOOP: UNLATCHED DATA[0]"

            for i, datum in list(enumerate(self.data))[1:]:
                with m.State(f"LOOP: UNLATCHED DATA[{i-1}]"):
                    with m.If(i2c.o_busy & i2c.o_ack & i2c.fifo.w_rdy):
                        m.d.sync += i2c.fifo.w_data.eq(datum)
                        m.d.sync += i2c.fifo.w_en.eq(1)
                        m.next = f"LOOP: LATCHED DATA[{i}]"
                    with m.Elif(~i2c.o_busy):
                        m.d.sync += self.aborted_at.eq(i - 1)
                        m.next = "IDLE"

                with m.State(f"LOOP: LATCHED DATA[{i}]"):
                    m.d.sync += i2c.fifo.w_en.eq(0)
                    if i < len(self.data) - 1:
                        m.next = f"LOOP: UNLATCHED DATA[{i}]"
                    else:
                        m.d.sync += self.aborted_at.eq(i)
                        m.next = "IDLE"

        return m
