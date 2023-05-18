from enum import Enum
from typing import Callable, Literal, Optional, cast

from amaranth import Signal
from amaranth.sim import Delay

import sim
from .i2c import I2C

__all__ = [
    "start",
    "repeated_start",
    "send",
    "ack",
    "nack",
    "stop",
    "steady_stopped",
    "full_sequence",
]

# XXX: There's definitely some gentle drift happening here, but it needs really
# long runs to unearth.  Take care!


def _tick(i2c: I2C) -> float:
    return 0.1 / i2c.speed.value


def synchronise(i2c: I2C, start_value: int) -> sim.Generator:
    assert not (yield i2c.i_stb)
    assert (yield i2c.fifo.w_en)
    assert (yield i2c.fifo.w_data) == start_value
    assert not (yield i2c.fifo.r_rdy)
    yield Delay(sim.clock())

    # Data is enqueued, we're strobing I2C.  Lines still high.
    assert (yield i2c.i_stb)
    assert not (yield i2c.fifo.w_en)
    assert (yield i2c.fifo.r_rdy)
    assert (yield i2c.fifo.r_level) == 1

    assert (yield i2c.scl_o)
    assert (yield i2c.sda_o)
    yield Delay(sim.clock())


def start(i2c: I2C) -> sim.Generator:
    # Strobed.  I2C start condition.
    assert not (yield i2c.i_stb)
    assert (yield i2c.scl_o)
    assert not (yield i2c.sda_o)
    yield Delay(5 * _tick(i2c))

    # I2C clock starts.
    assert not (yield i2c.scl_o)
    assert not (yield i2c.sda_o)


def repeated_start(i2c: I2C) -> sim.Generator:
    assert not (yield i2c.scl_o)
    yield Delay(5 * _tick(i2c))

    assert (yield i2c.sda_o)
    yield Delay(5 * _tick(i2c))

    # I2C clock starts.
    assert not (yield i2c.scl_o)
    assert not (yield i2c.sda_o)


class ValueChange(Enum):
    DONT_CARE = 1
    STEADY = 2
    FALL = 3


# TODO: make diff classes for diff ValueChanges so no wasted effort
class ValueChangeWatcher:
    vca: ValueChange
    source: Signal
    value: int

    def __init__(self, vca: ValueChange, source: Signal):
        self.vca = vca
        self.source = source

    def start(self) -> sim.Generator:
        if self.vca == ValueChange.DONT_CARE:
            return

        self.value = yield self.source

        if self.vca == ValueChange.FALL:
            assert self.value

    def update(self) -> sim.Generator:
        if self.vca == ValueChange.DONT_CARE:
            return

        new_value = yield self.source
        if self.vca == ValueChange.STEADY:
            assert new_value == self.value
        elif self.vca == ValueChange.FALL:
            if self.value:
                self.value = new_value
            else:
                assert not new_value

    def finish(self) -> None:
        if self.vca == ValueChange.FALL:
            assert not self.value


def wait_scl(
    i2c: I2C,
    level: int,
    *,
    sda_o: ValueChange = ValueChange.DONT_CARE,
    sda_oe: ValueChange = ValueChange.STEADY,
) -> sim.Generator:
    assert (yield i2c.scl_o) != level

    vcw_sda_o = ValueChangeWatcher(sda_o, i2c.sda_o)
    yield from vcw_sda_o.start()
    vcw_sda_oe = ValueChangeWatcher(sda_oe, i2c.sda_oe)
    yield from vcw_sda_oe.start()

    while True:
        yield Delay(_tick(i2c))

        yield from vcw_sda_o.update()
        yield from vcw_sda_oe.update()

        if (yield i2c.scl_o) == level:
            break

    vcw_sda_o.finish()
    vcw_sda_oe.finish()


def send(
    i2c: I2C, byte: int, *, next: int | Literal["STOP"] | None = None
) -> sim.Generator:
    actual = 0
    assert not (yield i2c.scl_o)
    for bit in range(8):
        if bit == 0:
            if isinstance(next, int):
                assert (yield i2c.fifo.r_rdy)
                assert (
                    yield i2c.fifo.w_data
                ) == next, f"checking next: expected {next:02x}, got {(yield i2c.fifo.w_data):02x}"
            elif next == "STOP":
                assert not (
                    yield i2c.fifo.r_rdy
                ), f"checking next: expected empty FIFO, contained ({(yield i2c.fifo.w_data):02x})"

        yield from wait_scl(i2c, 1)

        if bit == 0 and isinstance(next, int):
            assert not (yield i2c.fifo.w_en)
        actual = (actual << 1) | (yield i2c.sda_o)

        yield from wait_scl(i2c, 0, sda_o=ValueChange.STEADY)

    assert actual == byte, f"expected {byte:02x}, got {actual:02x}"


def ack(i2c: I2C, *, ack: bool = True) -> sim.Generator:
    # Master releases SDA; we ACK by driving SDA low.
    assert (yield i2c.sda_oe)
    yield Delay(_tick(i2c))
    if ack:
        yield cast(Signal, i2c.sda.i).eq(0)
    yield Delay(3 * _tick(i2c))
    assert not (yield i2c.sda_oe)
    yield Delay(_tick(i2c))

    yield Delay(4 * _tick(i2c))
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
    sda_start = yield i2c.sda_o
    yield from wait_scl(
        i2c, 1, sda_o=ValueChange.FALL if sda_start else ValueChange.STEADY
    )

    # Now while SCL is high, bring SDA high.
    while True:
        yield Delay(_tick(i2c))
        assert (yield i2c.scl_o)
        if (yield i2c.sda_o):
            break


def steady_stopped(i2c: I2C) -> sim.Generator:
    for _ in range(3):
        yield Delay(_tick(i2c))
        assert (yield i2c.scl_o)
        assert (yield i2c.sda_o)

    assert not (yield i2c.fifo.r_rdy)
    assert not (yield i2c.o_busy)


def full_sequence(
    i2c: I2C,
    trigger: Callable[[], sim.Generator],
    sequences: list[int | list[int]],
    *,
    test_nacks: bool = True,
) -> sim.Generator:
    sequence: list[int] = []
    for item in sequences:
        if isinstance(item, int):
            sequence.append(item)
        else:
            sequence += item

    nacks: list[Optional[int]] = [None]
    if test_nacks:
        nacks += list(range(len(sequence)))

    for nack_after in nacks:
        yield from trigger()

        yield from synchronise(i2c, sequence[0])
        yield from start(i2c)

        for i, byte in enumerate(sequence):
            if (byte & 0x100) and i > 0:
                yield from repeated_start(i2c)

            check_byte = byte & 0xFF
            check_next = sequence[i + 1] if i < len(sequence) - 1 else "STOP"
            yield from send(i2c, check_byte, next=check_next)

            if check_next != "STOP":
                check_next = f"{check_next:02x}"

            if i == nack_after:
                yield from nack(i2c)
                break
            yield from ack(i2c)

        yield from stop(i2c)
        yield from steady_stopped(i2c)
