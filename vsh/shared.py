from enum import Enum
from typing import Any, Optional, TypeAlias

Level: TypeAlias = int
SIGNALS: Level = 0
LOW_STATES: Level = 1
MED_STATES: Level = 2
HIGH_STATES: Level = 3
ERRORS: Level = 4

DEBUG_LEVEL: Level = HIGH_STATES


class Value:
    value: int
    stable: bool

    def __init__(self, value: int, stable: bool):
        self.value = value
        self.stable = stable

    @property
    def stable_high(self) -> bool:
        return bool(self.stable and self.value)

    @property
    def stable_low(self) -> bool:
        return bool(self.stable and not self.value)

    @property
    def falling(self) -> bool:
        return bool(not self.stable and not self.value)

    @property
    def rising(self) -> bool:
        return bool(not self.stable and self.value)


_tracked: dict[str, Any] = {}


def track(
    level: Level,
    name: str,
    value: Any,
    type: Optional[type] = None,
    *,
    show: bool = True,
) -> Value:
    global _tracked, DEBUG_LEVEL
    orig = value
    if type:
        try:
            value = type(value)
        except ValueError:
            pass
    if isinstance(value, Enum):
        value = value.name
    stable = True
    if name not in _tracked:
        _tracked[name] = value
    elif _tracked[name] != value:
        stable = False
        _tracked[name] = value
        if show and level >= DEBUG_LEVEL:
            if isinstance(value, int):
                value = f"0x{value:04x}"
            print(f"{name}: -> {value}")
    return Value(orig, stable)
