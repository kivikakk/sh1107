from typing import List, Tuple

from amaranth import Signal
from amaranth.sim import Simulator

from .top import Top

SIM_CLOCK = 1e-6


def bench(dut: Top):
    # Init: _sda.i defaults to being held high.
    yield dut.i2c._sda.i.eq(1)

    # Push the button.
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

    # Address: 0b111100 / RW: 0b0
    for bit in [0, 1, 1, 1, 1, 0, 0] + [0]:
        yield
        yield
        yield
        assert (yield dut.i2c._scl.o)
        if bit:
            assert (yield dut.i2c._sda.o)
        else:
            assert not (yield dut.i2c._sda.o)
        yield
        yield
        yield

        assert not (yield dut.i2c._scl.o)

    # Master releases SDA; we'll ACK by driving SDA low.
    yield dut.i2c._sda.i.eq(0)
    yield
    assert (yield dut.i2c._sda.oe)
    yield
    assert not (yield dut.i2c._sda.oe)
    yield

    yield
    assert not (yield dut.i2c._sda.oe)
    yield
    assert (yield dut.i2c._sda.oe)
    yield

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
            dut.i2c._scl.o,
            dut.i2c._sda.oe,
            dut.i2c._sda.o,
            dut.i2c._sda.i,
        ],
    )
