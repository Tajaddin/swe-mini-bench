`recursive_sum([7])` raises `IndexError: list index out of range`. The base case for a 1-element list is wrong; only the empty-list case is handled.
