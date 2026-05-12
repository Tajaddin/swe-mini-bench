from module import add_item


def test_no_default_state_leak():
    assert add_item("foo") == ["foo"]
    assert add_item("bar") == ["bar"]


def test_explicit_bucket_still_works():
    b = ["x"]
    add_item("y", b)
    assert b == ["x", "y"]
