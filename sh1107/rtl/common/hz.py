__all__ = ["Hz"]


class Hz:
    value: int

    def __init__(self, value: int | str):
        self.value = int(value)

    def __repr__(self) -> str:
        return f"{self.value}Hz"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Hz):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)
