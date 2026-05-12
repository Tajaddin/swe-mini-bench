from datetime import datetime


def is_in_future(dt: datetime) -> bool:
    """Return True iff ``dt`` is strictly after the current UTC time."""
    return dt > datetime.utcnow()
