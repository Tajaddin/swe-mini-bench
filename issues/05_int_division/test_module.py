from module import split_bill


def test_even_split():
    assert split_bill(900, 3) == [300, 300, 300]


def test_remainder_lands_on_first():
    assert split_bill(1000, 3) == [334, 333, 333]


def test_two_cent_remainder():
    # 1001 / 3 = 333 r 2 — first two get 334.
    assert split_bill(1001, 3) == [334, 334, 333]


def test_sum_always_equals_total():
    for total in (10, 17, 100, 9999):
        for n in (1, 2, 3, 5, 7):
            parts = split_bill(total, n)
            assert sum(parts) == total
            assert len(parts) == n
