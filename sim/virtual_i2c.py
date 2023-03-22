from typing import Literal, cast

from amaranth import Signal
from amaranth.sim import Delay, Settle

from sim_config import SimGenerator, sim_clock
from .start_top import Top

__all__ = ["VirtualI2C"]


class VirtualI2C:
    dut: Top
    tick: float

    def __init__(self, dut: Top):
        self.dut = dut
        self.tick = 0.1 / dut.speed.hz

    def start(self) -> SimGenerator:
        # Strobed.  I2C start condition.
        assert not (yield self.dut.i2c.i_stb)
        assert (yield self.dut.i2c.scl_o)
        assert not (yield self.dut.i2c.sda_o)
        yield Delay(5 * self.tick)
        yield Settle()

        # I2C clock starts.
        assert not (yield self.dut.i2c.scl_o)
        assert not (yield self.dut.i2c.sda_o)

    def send(
        self, byte: int, *, next: int | Literal["STOP"] | None = None
    ) -> SimGenerator:
        for bit in range(8):
            yield Delay(sim_clock() * 2)
            yield Settle()
            if bit == 0:
                if isinstance(next, int):
                    assert (yield self.dut.i2c.fifo.w_en)
                    assert (yield self.dut.i2c.fifo.w_data) == next
                elif next == "STOP":
                    assert not (yield self.dut.i2c.fifo.w_en)
            yield Delay(5 * self.tick - sim_clock() * 2)
            yield Settle()
            if bit == 0 and isinstance(next, int):
                assert not (yield self.dut.i2c.fifo.w_en)
            assert (yield self.dut.i2c.scl_o)
            if byte & (1 << (7 - bit)):  # MSB
                assert (yield self.dut.i2c.sda_o)
            else:
                assert not (yield self.dut.i2c.sda_o)
            yield Delay(5 * self.tick)
            yield Settle()

            assert not (yield self.dut.i2c.scl_o)

    def ack(self, *, ack: bool = True) -> SimGenerator:
        # Master releases SDA; we ACK by driving SDA low.
        assert (yield self.dut.i2c.sda_oe)
        yield Delay(self.tick)
        if ack:
            yield cast(Signal, self.dut.i2c.sda.i).eq(0)
        yield Delay(3 * self.tick)
        yield Settle()
        assert not (yield self.dut.i2c.sda_oe)
        yield Delay(self.tick)

        yield Delay(4 * self.tick)
        yield Settle()
        assert (yield self.dut.i2c.sda_oe)
        if ack:
            yield cast(Signal, self.dut.i2c.sda.i).eq(1)
        yield Delay(self.tick)

    def nack(self) -> SimGenerator:
        yield from self.ack(ack=False)

    def stop(self) -> SimGenerator:
        # While SCL is low, bring SDA low.
        last_sda = yield self.dut.i2c.sda_o
        yield Delay(self.tick)
        assert not (yield self.dut.i2c.scl_o)
        assert (yield self.dut.i2c.sda_o) == last_sda
        yield Delay(3 * self.tick)
        yield Settle()
        assert not (yield self.dut.i2c.scl_o)
        assert not (yield self.dut.i2c.sda_o)
        yield Delay(self.tick)
        yield Settle()

        # Then when SCL is high, bring SDA high.
        assert (yield self.dut.i2c.scl_o)
        assert not (yield self.dut.i2c.sda_o)
        yield Delay(self.tick)
        assert not (yield self.dut.i2c.sda_o)
        yield Delay(3 * self.tick)
        yield Settle()
        assert (yield self.dut.i2c.sda_o)
        yield Delay(self.tick)
        yield Settle()
