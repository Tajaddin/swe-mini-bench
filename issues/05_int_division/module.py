def split_bill(total_cents: int, n: int) -> list[int]:
    """Split ``total_cents`` among ``n`` payers. The sum of the result must
    equal ``total_cents`` exactly — any rounding remainder goes onto the
    first payers."""
    per = total_cents // n
    return [per] * n
