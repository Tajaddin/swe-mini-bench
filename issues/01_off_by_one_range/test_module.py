from module import inclusive_range


def test_inclusive_both_ends():
    assert inclusive_range(1, 5) == [1, 2, 3, 4, 5]


def test_single_value():
    assert inclusive_range(7, 7) == [7]


def test_negative_to_positive():
    assert inclusive_range(-2, 2) == [-2, -1, 0, 1, 2]
