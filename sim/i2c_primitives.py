from typing import Literal, cast

from amaranth import Signal
from amaranth.sim import Delay, Settle

from ..config import SIM_CLOCK
from .start_top import Top


def switch(dut: Top):
    # Force the button push, we don't need to test it here.
    yield dut.button.o_up.eq(1)
    yield Delay(SIM_CLOCK)
    yield Settle()
    yield dut.button.o_up.eq(0)


def start(dut: Top):
    # Strobed.  I2C start condition.
    assert not (yield dut.i2c.i_stb)
    assert (yield dut.i2c._scl.o)
    assert not (yield dut.i2c._sda.o)
    yield Delay(5e-06)
    yield Settle()

    # I2C clock starts.
    assert not (yield dut.i2c._scl.o)
    assert not (yield dut.i2c._sda.o)


def send(dut: Top, byte: int, *, next: int | Literal["STOP"] | None = None):
    for bit in range(8):
        yield Delay(SIM_CLOCK * 2)
        yield Settle()
        if bit == 0:
            if isinstance(next, int):
                assert (yield dut.i2c.fifo.w_en)
                assert (yield dut.i2c.fifo.w_data) == next
            elif next == "STOP":
                assert not (yield dut.i2c.fifo.w_en)
        yield Delay(5e-06 - SIM_CLOCK * 2)
        yield Settle()
        if bit == 0 and isinstance(next, int):
            assert not (yield dut.i2c.fifo.w_en)
        assert (yield dut.i2c._scl.o)
        if byte & (1 << (7 - bit)):  # MSB
            assert (yield dut.i2c._sda.o)
        else:
            assert not (yield dut.i2c._sda.o)
        yield Delay(5e-06)
        yield Settle()

        assert not (yield dut.i2c._scl.o)


def ack(dut: Top, *, ack: bool = True):
    # Master releases SDA; we ACK by driving SDA low.
    assert (yield dut.i2c._sda.oe)
    yield Delay(1e-06)
    if ack:
        yield cast(Signal, dut.i2c._sda.i).eq(0)
    yield Delay(3e-06)
    yield Settle()
    assert not (yield dut.i2c._sda.oe)
    yield Delay(1e-06)

    yield Delay(4e-06)
    yield Settle()
    assert (yield dut.i2c._sda.oe)
    if ack:
        yield cast(Signal, dut.i2c._sda.i).eq(1)
    yield Delay(1e-06)


def nack(dut: Top):
    yield from ack(dut, ack=False)


def stop(dut: Top):
    # While SCL is low, bring SDA low.
    last_sda = yield dut.i2c._sda.o
    yield Delay(1e-06)
    assert not (yield dut.i2c._scl.o)
    assert (yield dut.i2c._sda.o) == last_sda
    yield Delay(3e-06)
    yield Settle()
    assert not (yield dut.i2c._scl.o)
    assert not (yield dut.i2c._sda.o)
    yield Delay(1e-06)
    yield Settle()

    # Then when SCL is high, bring SDA high.
    assert (yield dut.i2c._scl.o)
    assert not (yield dut.i2c._sda.o)
    yield Delay(1e-06)
    assert not (yield dut.i2c._sda.o)
    yield Delay(3e-06)
    yield Settle()
    assert (yield dut.i2c._sda.o)
    yield Delay(1e-06)
    yield Settle()


__all__ = ["switch", "start", "send", "ack", "nack", "stop"]
