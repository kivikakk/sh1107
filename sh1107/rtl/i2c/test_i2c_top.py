from typing import Optional

from amaranth import Elaboratable, Module, Value
from amaranth.build import Platform
from amaranth.lib.wiring import Component, In, Out, Signature

from ..common import Hz
from . import I2C


class TestI2CTop(Component):
    data: list[int]
    speed: Hz

    i2c: I2C

    def __init__(self, data: list[int | Value], *, speed: Hz):
        assert len(data) >= 1
        for datum in data:
            assert isinstance(datum, Value) or (0 <= datum <= 0x1FF)
        self.data = data
        self.speed = speed

        super().__init__()

        self.i2c = I2C(speed=speed)

    @property
    def signature(self):
        return Signature(
            {
                "switch": In(1),
                "aborted_at": Out(range(len(self.data))),
            }
        )

    def elaborate(self, platform: Optional[Platform]) -> Elaboratable:
        m = Module()

        m.submodules.i2c = self.i2c

        bus = self.i2c.bus

        with m.FSM():
            with m.State("IDLE"):
                with m.If(self.switch):
                    m.d.sync += [
                        bus.in_fifo_w_data.eq(self.data[0]),
                        bus.in_fifo_w_en.eq(1),
                    ]
                    m.next = "START: W_EN LATCHED"

            with m.State("START: W_EN LATCHED"):
                m.d.sync += [
                    bus.in_fifo_w_en.eq(0),
                    bus.stb.eq(1),
                ]
                m.next = "START: STROBED"

            with m.State("START: STROBED"):
                m.d.sync += bus.stb.eq(0)
                m.next = "LOOP: UNLATCHED DATA[0]"

            for i, datum in list(enumerate(self.data))[1:]:
                with m.State(f"LOOP: UNLATCHED DATA[{i-1}]"):
                    with m.If(bus.busy & bus.ack & bus.in_fifo_w_rdy):
                        m.d.sync += [
                            bus.in_fifo_w_data.eq(datum),
                            bus.in_fifo_w_en.eq(1),
                        ]
                        m.next = f"LOOP: LATCHED DATA[{i}]"
                    with m.Elif(~bus.busy):
                        m.d.sync += self.aborted_at.eq(i - 1)
                        m.next = "IDLE"

                with m.State(f"LOOP: LATCHED DATA[{i}]"):
                    m.d.sync += bus.in_fifo_w_en.eq(0)
                    if i < len(self.data) - 1:
                        m.next = f"LOOP: UNLATCHED DATA[{i}]"
                    else:
                        m.d.sync += self.aborted_at.eq(i)
                        m.next = "IDLE"

        return m
