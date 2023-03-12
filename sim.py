from typing import List, Tuple, Literal, Optional

from amaranth import Signal
from amaranth.sim import Simulator, Delay, Settle

from .top import Top
from .config import SIM_CLOCK


def _i2c_switch(dut: Top):
    # Force the button push, we don't need to test it here.
    yield dut.button.o_up.eq(1)
    yield Delay(SIM_CLOCK)
    yield Settle()
    yield dut.button.o_up.eq(0)


def _i2c_start(dut: Top):
    # Strobed.  I2C start condition.
    assert not (yield dut.i2c.i_stb)
    assert (yield dut.i2c._scl.o)
    assert not (yield dut.i2c._sda.o)
    yield Delay(5e-06)
    yield Settle()

    # I2C clock starts.
    assert not (yield dut.i2c._scl.o)
    assert not (yield dut.i2c._sda.o)


def _i2c_send(dut: Top, byte: int, *, next: int | Literal["STOP"] = None):
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


def _i2c_ack(dut: Top, *, ack: bool = True):
    # Master releases SDA; we ACK by driving SDA low.
    assert (yield dut.i2c._sda.oe)
    yield Delay(1e-06)
    if ack:
        yield dut.i2c._sda.i.eq(0)
    yield Delay(3e-06)
    yield Settle()
    assert not (yield dut.i2c._sda.oe)
    yield Delay(1e-06)

    yield Delay(4e-06)
    yield Settle()
    assert (yield dut.i2c._sda.oe)
    if ack:
        yield dut.i2c._sda.i.eq(1)
    yield Delay(1e-06)


def _i2c_nack(dut: Top):
    yield from _i2c_ack(dut, ack=False)


def _i2c_stop(dut: Top):
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


def bench(dut: Top):
    # Init: _sda.i defaults to being held high.
    yield dut.i2c._sda.i.eq(1)

    yield from bench_complete(dut)
    yield from bench_nacks(dut)


def bench_complete(dut: Top, *, nack_after: Optional[int] = None):
    # Push the button.
    yield from _i2c_switch(dut)

    # Enqueue the data.
    assert not (yield dut.i2c.i_stb)
    assert (yield dut.i2c.fifo.w_en)
    assert (yield dut.i2c.fifo.w_data) == 0xAF
    assert not (yield dut.i2c.fifo.r_rdy)
    assert (yield dut.i2c.fifo.r_level) == 0
    yield Delay(SIM_CLOCK)
    yield Settle()

    # Data is enqueued, we're strobing I2C.  I2C still high.
    assert (yield dut.i2c.i_stb)
    assert not (yield dut.i2c.fifo.w_en)
    assert (yield dut.i2c.fifo.r_rdy)
    assert (yield dut.i2c.fifo.r_level) == 1

    assert (yield dut.i2c._scl.o)
    assert (yield dut.i2c._sda.o)
    yield Delay(SIM_CLOCK)
    yield Settle()

    yield from _i2c_start(dut)

    yield from _i2c_send(dut, (0x3C << 1) | 0)
    if nack_after == 1:
        yield from _i2c_nack(dut)
    else:
        yield from _i2c_ack(dut)
        yield from _i2c_send(dut, 0xAF, next=0x8C)
        if nack_after == 2:
            yield from _i2c_nack(dut)
        else:
            yield from _i2c_ack(dut)
            yield from _i2c_send(dut, 0x8C, next="STOP")
            if nack_after == 3:
                yield from _i2c_nack(dut)
            else:
                yield from _i2c_ack(dut)

    yield from _i2c_stop(dut)

    for _ in range(3):
        yield Delay(SIM_CLOCK)
        yield Settle()
        assert (yield dut.i2c._scl.o)
        assert (yield dut.i2c._sda.o)


def bench_nacks(dut: Top):
    yield from bench_complete(dut, nack_after=1)
    yield from bench_complete(dut, nack_after=2)
    yield from bench_complete(dut, nack_after=3)


def prep() -> Tuple[Top, Simulator, List[Signal]]:
    dut = Top()

    def bench_wrapper():
        yield from bench(dut)

    sim = Simulator(dut)
    sim.add_clock(SIM_CLOCK)
    sim.add_sync_process(bench_wrapper)

    return (
        dut,
        sim,
        [
            dut.button.o_up,
            dut.i2c.i_addr,
            dut.i2c.i_rw,
            dut.i2c.i_stb,
            dut.i2c.fifo.w_rdy,
            dut.i2c.fifo.w_en,
            dut.i2c.fifo.w_data,
            dut.i2c.fifo.w_level,
            dut.i2c.fifo.r_rdy,
            dut.i2c.fifo.r_en,
            dut.i2c.fifo.r_data,
            dut.i2c.fifo.r_level,
            dut.i2c.o_busy,
            dut.i2c.o_ack,
            dut.i2c._I2C__byte,
            dut.i2c._I2C__byte_ix,
            dut.i2c._scl.o,
            dut.i2c._sda.oe,
            dut.i2c._sda.o,
            dut.i2c._sda.i,
        ],
    )
