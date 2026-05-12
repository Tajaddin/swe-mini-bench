from module import remove_suffix


def test_simple():
    assert remove_suffix("hello_world", "world") == "hello_"


def test_single_char_repeated_only_one_removed():
    # rstrip('x') would strip BOTH trailing x's; suffix removal should only
    # remove the literal one-char suffix once.
    assert remove_suffix("aaa_xx", "x") == "aaa_x"


def test_suffix_chars_overlap_with_body():
    # rstrip('abc') would consume every trailing a/b/c → "". Literal suffix
    # removal: "abcabc"[:-3] == "abc".
    assert remove_suffix("abcabc", "abc") == "abc"


def test_no_match_returns_input():
    assert remove_suffix("foo.bar", "baz") == "foo.bar"
