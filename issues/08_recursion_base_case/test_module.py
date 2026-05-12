from module import recursive_sum


def test_empty():
    assert recursive_sum([]) == 0


def test_single_element():
    assert recursive_sum([7]) == 7


def test_general():
    assert recursive_sum([1, 2, 3, 4, 5]) == 15


def test_odd_length():
    assert recursive_sum([10, 20, 30]) == 60
