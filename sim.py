from typing import List, Tuple, Literal

from amaranth import Signal
from amaranth.sim import Simulator

from .top import Top

SIM_CLOCK = 1e-6


def _i2c_switch(dut: Top):
    yield dut.switch.eq(1)
    yield
    yield
    yield dut.switch.eq(0)
    yield
    assert (yield dut.button.o_down)
    yield
    yield
    assert (yield dut.button.o_up)
    yield


def _i2c_start(dut: Top):
    # Strobed.  I2C start condition.
    assert not (yield dut.i2c.i_stb)
    assert (yield dut.i2c._scl.o)
    assert not (yield dut.i2c._sda.o)
    yield
    yield
    yield

    # I2C clock starts.
    assert not (yield dut.i2c._scl.o)
    assert not (yield dut.i2c._sda.o)


def _i2c_send(dut: Top, byte: int, *, next: int | Literal["STOP"] = None):
    for bit in range(8):
        yield
        yield
        if bit == 0:
            if isinstance(next, int):
                assert (yield dut.i2c.fifo.w_en)
                assert (yield dut.i2c.fifo.w_data) == next
            elif next == "STOP":
                assert not (yield dut.i2c.fifo.w_en)
        yield
        if bit == 0 and isinstance(next, int):
            assert not (yield dut.i2c.fifo.w_en)
        assert (yield dut.i2c._scl.o)
        if byte & (1 << (7 - bit)):  # MSB
            assert (yield dut.i2c._sda.o)
        else:
            assert not (yield dut.i2c._sda.o)
        yield
        yield
        yield

        assert not (yield dut.i2c._scl.o)


def _i2c_ack(dut: Top):
    # Master releases SDA; we'll ACK by driving SDA low.
    yield
    assert (yield dut.i2c._sda.oe)
    yield dut.i2c._sda.i.eq(0)
    yield
    assert not (yield dut.i2c._sda.oe)
    yield

    yield
    assert not (yield dut.i2c._sda.oe)
    yield dut.i2c._sda.i.eq(1)  # Make it clear we're not trying.
    yield
    assert (yield dut.i2c._sda.oe)
    yield


def _i2c_stop(dut: Top):
    # While SCL is low, bring SDA low.
    yield
    assert not (yield dut.i2c._scl.o)
    # assert (yield dut.i2c._sda.o)  # <- not for 0x8C
    yield
    assert not (yield dut.i2c._scl.o)
    assert not (yield dut.i2c._sda.o)
    yield

    # Then when SCL is high, bring SDA high.
    assert (yield dut.i2c._scl.o)
    assert not (yield dut.i2c._sda.o)


def bench(dut: Top):
    # Init: _sda.i defaults to being held high.
    yield dut.i2c._sda.i.eq(1)

    # Push the button.
    yield from _i2c_switch(dut)

    # Enqueue the data.
    assert not (yield dut.i2c.i_stb)
    assert (yield dut.i2c.fifo.w_en)
    assert (yield dut.i2c.fifo.w_data) == 0xAF
    assert not (yield dut.i2c.fifo.r_rdy)
    assert (yield dut.i2c.fifo.r_level) == 0
    yield

    # Data is enqueued, we're strobing I2C.  I2C still high.
    assert (yield dut.i2c.i_stb)
    assert not (yield dut.i2c.fifo.w_en)
    assert (yield dut.i2c.fifo.r_rdy)
    assert (yield dut.i2c.fifo.r_level) == 1

    assert (yield dut.i2c._scl.o)
    assert (yield dut.i2c._sda.o)
    yield

    yield from _i2c_start(dut)

    yield from _i2c_send(dut, (0x3C << 1) | 0)
    yield from _i2c_ack(dut)
    yield from _i2c_send(dut, 0xAF, next=0x8C)
    yield from _i2c_ack(dut)
    yield from _i2c_send(dut, 0x8C, next="STOP")
    yield from _i2c_ack(dut)

    yield from _i2c_stop(dut)

    for _ in range(3):
        assert (yield dut.i2c._scl.o)
        assert (yield dut.i2c._sda.o)

    # TODO: same test but NACK.  Driver shouldn't send byte.


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
            dut.switch,
            dut.button.i_switch,
            dut.button.o_down,
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
            dut.i2c.o_ack,
            dut.i2c.o_busy,
            dut.i2c._I2C__byte,
            dut.i2c._I2C__byte_ix,
            dut.i2c._scl.o,
            dut.i2c._sda.oe,
            dut.i2c._sda.o,
            dut.i2c._sda.i,
        ],
    )
