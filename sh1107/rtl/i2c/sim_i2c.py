from enum import Enum
from typing import Callable, Literal, Optional, cast

from amaranth import Signal
from amaranth.sim import Delay

from ... import sim
from . import I2C

__all__ = [
    "start",
    "repeated_start",
    "send",
    "receive",
    "ack",
    "nack",
    "stop",
    "steady_stopped",
    "full_sequence",
]


def _tick(i2c: I2C) -> float:
    return 0.1 / i2c.speed.value


def synchronise(i2c: I2C, start_value: int, *, wait_steps: int = 20) -> sim.Procedure:
    for i in range(wait_steps):
        if i > 0:
            yield Delay(sim.clock())

        assert not (yield i2c.bus.stb)
        if (yield i2c.bus.in_fifo_w_en):
            break
    else:
        raise AssertionError(f"I2C didn't start in {wait_steps} steps")

    assert (
        yield i2c.bus.in_fifo_w_data
    ) == start_value, f"expected FIFO preloaded with {start_value:02x}, got {(yield i2c.bus.in_fifo_w_data):02x}"
    assert not (yield i2c.bus.in_fifo_r_rdy)
    yield Delay(sim.clock())

    # Data is enqueued, we're strobing I2C.  Lines still high.
    assert (yield i2c.bus.stb)
    assert not (yield i2c.bus.in_fifo_w_en)
    assert (yield i2c.bus.in_fifo_r_rdy)

    assert (yield i2c.hw_bus.scl_o)
    assert (yield i2c.hw_bus.sda_o)
    yield Delay(sim.clock())


def start(i2c: I2C) -> sim.Procedure:
    # Strobed.  I2C start condition.
    assert not (yield i2c.bus.stb)
    assert (yield i2c.hw_bus.scl_o)
    assert not (yield i2c.hw_bus.sda_o)
    yield Delay(5 * _tick(i2c))

    # I2C clock starts.
    assert not (yield i2c.hw_bus.scl_o)
    assert not (yield i2c.hw_bus.sda_o)


def repeated_start(i2c: I2C) -> sim.Procedure:
    assert not (yield i2c.hw_bus.scl_o)
    yield Delay(5 * _tick(i2c))

    assert (yield i2c.hw_bus.sda_o)
    yield Delay(5 * _tick(i2c))

    # I2C clock starts.
    assert not (yield i2c.hw_bus.scl_o)
    assert not (yield i2c.hw_bus.sda_o)


class ValueChangeWatcher:
    def start(self) -> sim.Procedure:
        return
        yield

    def update(self) -> sim.Procedure:
        return
        yield

    def finish(self) -> None:
        pass


class VCWSteady(ValueChangeWatcher):
    source: Signal

    def __init__(self, source: Signal):
        self.source = source

    def start(self) -> sim.Procedure:
        self.value = yield self.source

    def update(self) -> sim.Procedure:
        new_value = yield self.source
        assert new_value == self.value


class VCWFall(ValueChangeWatcher):
    source: Signal
    value: int

    def __init__(self, source: Signal):
        self.source = source

    def start(self) -> sim.Procedure:
        self.value = yield self.source
        assert self.value

    def update(self) -> sim.Procedure:
        new_value = yield self.source
        if not self.value:
            assert not new_value
        else:
            self.value = new_value

    def finish(self) -> None:
        assert not self.value


class ValueChange(Enum):
    DONT_CARE = 1
    STEADY = 2
    FALL = 3

    def watcher_for(self, source: Signal) -> ValueChangeWatcher:
        match self:
            case ValueChange.DONT_CARE:
                return ValueChangeWatcher()
            case ValueChange.STEADY:
                return VCWSteady(source)
            case ValueChange.FALL:
                return VCWFall(source)


def wait_scl(
    i2c: I2C,
    level: int,
    *,
    sda_o: ValueChange = ValueChange.DONT_CARE,
    sda_oe: ValueChange = ValueChange.STEADY,
) -> sim.Procedure:
    assert (yield i2c.hw_bus.scl_o) != level

    vcw_sda_o = sda_o.watcher_for(i2c.hw_bus.sda_o)
    yield from vcw_sda_o.start()
    vcw_sda_oe = sda_oe.watcher_for(i2c.hw_bus.sda_oe)
    yield from vcw_sda_oe.start()

    while True:
        yield Delay(_tick(i2c))

        yield from vcw_sda_o.update()
        yield from vcw_sda_oe.update()

        if (yield i2c.hw_bus.scl_o) == level:
            break

    vcw_sda_o.finish()
    vcw_sda_oe.finish()


def send(
    i2c: I2C, byte: int, *, next: int | Literal["STOP"] | None = None
) -> sim.Procedure:
    actual = 0
    assert not (yield i2c.hw_bus.scl_o)
    assert (yield i2c.hw_bus.sda_oe)
    for bit in range(8):
        yield from wait_scl(i2c, 1)

        actual = (actual << 1) | (yield i2c.hw_bus.sda_o)

        yield from wait_scl(
            i2c,
            0,
            sda_o=ValueChange.STEADY,
            sda_oe=ValueChange.STEADY if bit < 7 else ValueChange.FALL,
        )

        if bit == 0:
            if isinstance(next, int):
                assert (yield i2c.bus.in_fifo_r_rdy)
                assert (
                    yield i2c.bus.in_fifo_w_data
                ) == next, f"checking next: expected {next:02x}, got {(yield i2c.bus.in_fifo_w_data):02x}"
                assert not (yield i2c.bus.in_fifo_w_en)
            elif next == "STOP":
                assert not (
                    yield i2c.bus.in_fifo_r_rdy
                ), f"checking next: expected empty FIFO, contained ({(yield i2c.bus.in_fifo_w_data):02x})"

    assert actual == byte, f"expected {byte:02x}, got {actual:02x}"


def receive(i2c: I2C, byte: int) -> sim.Procedure:
    assert not (yield i2c.hw_bus.scl_o)
    for bit in range(8):
        yield i2c.hw_bus.sda_i.eq((byte >> (7 - bit)) & 1)

        yield from wait_scl(i2c, 1)

        assert not (yield i2c.hw_bus.sda_oe)

        yield from wait_scl(i2c, 0, sda_oe=ValueChange.STEADY)


def ack(
    i2c: I2C, *, ack: bool = True, from_us: bool = False, retakes_sda: bool = True
) -> sim.Procedure:
    if from_us:
        # Controller takes SDA.
        assert not (yield i2c.hw_bus.sda_oe)

        yield Delay(4 * _tick(i2c))
        assert (yield i2c.hw_bus.sda_oe)
        assert ack ^ (
            yield i2c.hw_bus.sda_o
        ), f"expected ack {ack} from us, got {not ack}"  # ACK/low or NACK/high
        yield Delay(6 * _tick(i2c))

        assert retakes_sda == (yield i2c.hw_bus.sda_oe)

    else:
        # Controller releases SDA; we ACK by driving SDA low.
        assert not (yield i2c.hw_bus.sda_oe)
        yield Delay(_tick(i2c))
        if ack:
            yield cast(Signal, i2c.hw_bus.sda_i).eq(0)
        yield Delay(3 * _tick(i2c))
        assert not (yield i2c.hw_bus.sda_oe)
        yield Delay(_tick(i2c))

        yield Delay(4 * _tick(i2c))
        if ack:
            yield cast(Signal, i2c.hw_bus.sda_i).eq(1)
        yield Delay(_tick(i2c))

        assert retakes_sda == (yield i2c.hw_bus.sda_oe)
        assert ack == (yield i2c.bus.ack)


def nack(i2c: I2C, *, from_us: bool = False) -> sim.Procedure:
    yield from ack(i2c, ack=False, from_us=from_us)


def stop(i2c: I2C) -> sim.Procedure:
    # While SCL is low, bring SDA low.
    sda_start = yield i2c.hw_bus.sda_o
    yield from wait_scl(
        i2c, 1, sda_o=ValueChange.FALL if sda_start else ValueChange.STEADY
    )

    # Now while SCL is high, bring SDA high.
    while True:
        yield Delay(_tick(i2c))
        assert (yield i2c.hw_bus.scl_o)
        if (yield i2c.hw_bus.sda_o):
            break


def steady_stopped(i2c: I2C, *, wait_steps: int = 5) -> sim.Procedure:
    for _ in range(wait_steps):
        yield Delay(_tick(i2c))
        assert (yield i2c.hw_bus.scl_o)
        assert (yield i2c.hw_bus.sda_o)

    assert not (
        yield i2c.bus.in_fifo_r_rdy
    ), f"unexpected data waiting on I2C in fifo: {(yield i2c.bus.in_fifo_w_data):02x}"
    assert not (yield i2c.bus.busy)


def full_sequence(
    i2c: I2C,
    trigger: Callable[[], sim.Procedure],
    sequences: list[int | list[int]],
    *,
    test_nacks: bool = True,
) -> sim.Procedure:
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
            if i < len(sequence) - 1:
                check_next = sequence[i + 1]
            else:
                check_next = "STOP"
            yield from send(i2c, check_byte, next=check_next)

            if i == nack_after:
                yield from nack(i2c)
                break
            yield from ack(i2c)

        yield from stop(i2c)
        yield from steady_stopped(i2c)
