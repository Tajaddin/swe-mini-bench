import time

from module import filter_blocked


def test_basic_filtering():
    events = [{"id": 1}, {"id": 2}, {"id": 3}]
    assert filter_blocked(events, [2]) == [{"id": 1}, {"id": 3}]


def test_empty_blocked_returns_all():
    events = [{"id": 1}, {"id": 2}]
    assert filter_blocked(events, []) == events


def test_performance_uses_set():
    """If membership is still list-based, this is O(n*m) and times out."""
    n = 50_000
    blocked = list(range(0, n, 2))         # every even id is blocked
    events = [{"id": i} for i in range(n)]

    start = time.perf_counter()
    out = filter_blocked(events, blocked)
    elapsed = time.perf_counter() - start

    assert len(out) == n // 2
    # On a modern laptop a set-based impl is < 0.1 s; list-based is several seconds.
    assert elapsed < 1.0, f"too slow: {elapsed:.2f}s — did you forget to convert to a set?"
