from typing import List, Tuple, Optional

from amaranth import Signal
from amaranth.sim import Simulator, Delay, Settle

from ..config import SIM_CLOCK
from ..i2c import Speed
from . import i2c_primitives as i2c
from .start_top import Top


def bench(dut: Top):
    yield from bench_complete(dut)
    yield from bench_nacks(dut)


def bench_complete(dut: Top, *, nack_after: Optional[int] = None):
    # Push the button.
    yield from i2c.switch(dut)

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

    yield from i2c.start(dut)

    yield from i2c.send(dut, (0x3C << 1) | 0)
    if nack_after == 1:
        yield from i2c.nack(dut)
    else:
        yield from i2c.ack(dut)
        yield from i2c.send(dut, 0xAF, next=0x8C)
        if nack_after == 2:
            yield from i2c.nack(dut)
        else:
            yield from i2c.ack(dut)
            yield from i2c.send(dut, 0x8C, next="STOP")
            if nack_after == 3:
                yield from i2c.nack(dut)
            else:
                yield from i2c.ack(dut)

    yield from i2c.stop(dut)

    for _ in range(3):
        yield Delay(SIM_CLOCK)
        yield Settle()
        assert (yield dut.i2c._scl.o)
        assert (yield dut.i2c._sda.o)


def bench_nacks(dut: Top):
    yield from bench_complete(dut, nack_after=1)
    yield from bench_complete(dut, nack_after=2)
    yield from bench_complete(dut, nack_after=3)


def prep_start(*, speed: Speed) -> Tuple[Top, Simulator, List[Signal]]:
    dut = Top(speed=speed)

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
            dut.i2c._byte,
            dut.i2c._byte_ix,
            dut.i2c._scl_o,
            dut.i2c._sda_oe,
            dut.i2c._sda_o,
            dut.i2c._sda_i,
        ],
    )


__all__ = ["prep_start"]
