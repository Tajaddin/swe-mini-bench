def filter_blocked(events: list[dict], blocked_ids: list[int]) -> list[dict]:
    """Return events whose id is NOT in ``blocked_ids``."""
    return [e for e in events if e["id"] not in blocked_ids]
