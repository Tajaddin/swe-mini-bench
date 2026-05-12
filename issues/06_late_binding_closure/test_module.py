from module import make_multipliers


def test_each_closure_captures_its_factor():
    fns = make_multipliers([1, 2, 3])
    assert fns[0](10) == 10
    assert fns[1](10) == 20
    assert fns[2](10) == 30


def test_empty_input():
    assert make_multipliers([]) == []


def test_zero_in_factors():
    fns = make_multipliers([0, 4])
    assert fns[0](99) == 0
    assert fns[1](99) == 396
