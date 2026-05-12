from datetime import datetime, timedelta, timezone

from module import is_in_future


def test_future_aware():
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    assert is_in_future(future) is True


def test_past_aware():
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    assert is_in_future(past) is False


def test_future_non_utc_zone():
    tz = timezone(timedelta(hours=-5))
    future = datetime.now(tz) + timedelta(hours=1)
    assert is_in_future(future) is True
