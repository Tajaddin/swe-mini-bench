from module import is_same_name


def test_canonically_equivalent():
    precomposed = "café"            # café  (precomposed é)
    decomposed = "café"            # café  (e + combining acute)
    assert is_same_name(precomposed, decomposed) is True


def test_truly_different_names():
    assert is_same_name("Alice", "Bob") is False


def test_identical_strings():
    assert is_same_name("Zoe", "Zoe") is True
