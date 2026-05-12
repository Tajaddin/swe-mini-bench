def remove_suffix(text: str, suffix: str) -> str:
    """Return ``text`` with the literal ``suffix`` removed from the end.

    If ``text`` does not end with ``suffix``, return ``text`` unchanged.
    """
    return text.rstrip(suffix)
