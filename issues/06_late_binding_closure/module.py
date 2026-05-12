from typing import Callable


def make_multipliers(factors: list[int]) -> list[Callable[[int], int]]:
    """Return a list of callables; callables[i](x) should return factors[i] * x."""
    callables = []
    for f in factors:
        callables.append(lambda x: f * x)
    return callables
