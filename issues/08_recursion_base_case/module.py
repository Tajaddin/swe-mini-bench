def recursive_sum(xs: list[int]) -> int:
    """Return the sum of ``xs`` by recursion."""
    if not xs:
        return 0
    return xs[0] + xs[1] + recursive_sum(xs[2:])
