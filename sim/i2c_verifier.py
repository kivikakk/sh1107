from typing import Literal, cast

from amaranth import Signal
from amaranth.sim import Delay, Settle

from ..config import SIM_CLOCK
from .start_top import Top


class I2CVerifier:
    dut: Top
    tick: float

    def __init__(self, dut: Top):
        self.dut = dut
        self.tick = 0.1 / dut.speed

    def switch(self):
        # Force the button push, we don't need to test it here.
        yield self.dut.button.o_up.eq(1)
        yield Delay(SIM_CLOCK)
        yield Settle()
        yield self.dut.button.o_up.eq(0)

    def start(self):
        # Strobed.  I2C start condition.
        assert not (yield self.dut.i2c.i_stb)
        assert (yield self.dut.i2c._scl.o)
        assert not (yield self.dut.i2c._sda.o)
        yield Delay(5 * self.tick)
        yield Settle()

        # I2C clock starts.
        assert not (yield self.dut.i2c._scl.o)
        assert not (yield self.dut.i2c._sda.o)

    def send(self, byte: int, *, next: int | Literal["STOP"] | None = None):
        for bit in range(8):
            yield Delay(SIM_CLOCK * 2)
            yield Settle()
            if bit == 0:
                if isinstance(next, int):
                    assert (yield self.dut.i2c.fifo.w_en)
                    assert (yield self.dut.i2c.fifo.w_data) == next
                elif next == "STOP":
                    assert not (yield self.dut.i2c.fifo.w_en)
            yield Delay(5 * self.tick - SIM_CLOCK * 2)
            yield Settle()
            if bit == 0 and isinstance(next, int):
                assert not (yield self.dut.i2c.fifo.w_en)
            assert (yield self.dut.i2c._scl.o)
            if byte & (1 << (7 - bit)):  # MSB
                assert (yield self.dut.i2c._sda.o)
            else:
                assert not (yield self.dut.i2c._sda.o)
            yield Delay(5 * self.tick)
            yield Settle()

            assert not (yield self.dut.i2c._scl.o)

    def ack(self, *, ack: bool = True):
        # Master releases SDA; we ACK by driving SDA low.
        assert (yield self.dut.i2c._sda.oe)
        yield Delay(self.tick)
        if ack:
            yield cast(Signal, self.dut.i2c._sda.i).eq(0)
        yield Delay(3 * self.tick)
        yield Settle()
        assert not (yield self.dut.i2c._sda.oe)
        yield Delay(self.tick)

        yield Delay(4 * self.tick)
        yield Settle()
        assert (yield self.dut.i2c._sda.oe)
        if ack:
            yield cast(Signal, self.dut.i2c._sda.i).eq(1)
        yield Delay(self.tick)

    def nack(self):
        yield from self.ack(ack=False)

    def stop(self):
        # While SCL is low, bring SDA low.
        last_sda = yield self.dut.i2c._sda.o
        yield Delay(self.tick)
        assert not (yield self.dut.i2c._scl.o)
        assert (yield self.dut.i2c._sda.o) == last_sda
        yield Delay(3 * self.tick)
        yield Settle()
        assert not (yield self.dut.i2c._scl.o)
        assert not (yield self.dut.i2c._sda.o)
        yield Delay(self.tick)
        yield Settle()

        # Then when SCL is high, bring SDA high.
        assert (yield self.dut.i2c._scl.o)
        assert not (yield self.dut.i2c._sda.o)
        yield Delay(self.tick)
        assert not (yield self.dut.i2c._sda.o)
        yield Delay(3 * self.tick)
        yield Settle()
        assert (yield self.dut.i2c._sda.o)
        yield Delay(self.tick)
        yield Settle()


__all__ = ["I2CVerifier"]
