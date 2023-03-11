from typing import List, Tuple

from amaranth import Signal
from amaranth.sim import Simulator, Delay

from .top import Top
from .main import SIM_CLOCK


def bench(dut: Top):
    yield dut.button.eq(1)
    yield Delay(1e-3)
    yield dut.button.eq(0)
    yield Delay(1e-3)


def prep() -> Tuple[Top, Simulator, List[Signal]]:
    dut = Top()

    sim = Simulator(dut)
    sim.add_clock(SIM_CLOCK)
    sim.add_sync_process(lambda: bench(dut))

    return (
        dut,
        sim,
        [
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
            dut.i2c._scl,
            dut.i2c._sda,
        ],
    )
