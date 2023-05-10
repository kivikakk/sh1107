from typing import Literal, cast

from amaranth import Signal
from amaranth.sim import Delay, Settle

import sim
from .i2c import I2C

__all__ = ["start", "repeated_start", "send", "ack", "nack", "stop"]


def _tick(i2c: I2C) -> float:
    return 0.1 / i2c.speed.value


def start(i2c: I2C) -> sim.Generator:
    # Strobed.  I2C start condition.
    assert not (yield i2c.i_stb)
    assert (yield i2c.scl_o)
    assert not (yield i2c.sda_o)
    yield Delay(5 * _tick(i2c))
    yield Settle()

    # I2C clock starts.
    assert not (yield i2c.scl_o)
    assert not (yield i2c.sda_o)


def repeated_start(i2c: I2C) -> sim.Generator:
    assert (yield i2c.scl_o_last)
    assert not (yield i2c.scl_o)

    assert (yield i2c.sda_o)
    yield Delay(10 * _tick(i2c))
    yield Settle()

    # I2C clock starts.
    assert not (yield i2c.scl_o)
    assert not (yield i2c.sda_o)


def send(
    i2c: I2C, byte: int, *, next: int | Literal["STOP"] | None = None
) -> sim.Generator:
    actual = 0
    for bit in range(8):
        yield Delay(sim.clock() * 2)
        yield Settle()
        if bit == 0:
            if isinstance(next, int):
                assert (yield i2c.fifo.r_rdy)
                assert (yield i2c.fifo.w_data) == next
            elif next == "STOP":
                assert not (yield i2c.fifo.r_rdy)
        yield Delay(5 * _tick(i2c) - sim.clock() * 2)
        yield Settle()
        if bit == 0 and isinstance(next, int):
            assert not (yield i2c.fifo.w_en)
        assert (yield i2c.scl_o)
        actual = (actual << 1) | (yield i2c.sda_o)
        yield Delay(5 * _tick(i2c))
        yield Settle()

        assert not (yield i2c.scl_o), f"expected SCL low at end of bit {bit}"

    assert actual == byte, f"expected {byte:02x}, got {actual:02x}"


def ack(i2c: I2C, *, ack: bool = True) -> sim.Generator:
    # Master releases SDA; we ACK by driving SDA low.
    assert (yield i2c.sda_oe)
    yield Delay(_tick(i2c))
    if ack:
        yield cast(Signal, i2c.sda.i).eq(0)
    yield Delay(3 * _tick(i2c))
    yield Settle()
    assert not (yield i2c.sda_oe)
    yield Delay(_tick(i2c))

    yield Delay(4 * _tick(i2c))
    yield Settle()
    assert (yield i2c.sda_oe)
    if ack:
        yield cast(Signal, i2c.sda.i).eq(1)
    yield Delay(_tick(i2c))

    if ack:
        assert (yield i2c.o_ack)
    else:
        assert not (yield i2c.o_ack)


def nack(i2c: I2C) -> sim.Generator:
    yield from ack(i2c, ack=False)


def stop(i2c: I2C) -> sim.Generator:
    # While SCL is low, bring SDA low.
    last_sda = yield i2c.sda_o
    yield Delay(_tick(i2c))
    assert not (yield i2c.scl_o)
    assert (yield i2c.sda_o) == last_sda
    yield Delay(3 * _tick(i2c))
    yield Settle()
    assert not (yield i2c.scl_o)
    assert not (yield i2c.sda_o)
    yield Delay(_tick(i2c))
    yield Settle()

    # Then when SCL is high, bring SDA high.
    assert (yield i2c.scl_o)
    assert not (yield i2c.sda_o)
    yield Delay(_tick(i2c))
    assert not (yield i2c.sda_o)
    yield Delay(3 * _tick(i2c))
    yield Settle()
    assert (yield i2c.sda_o)
    yield Delay(_tick(i2c))
    yield Settle()
