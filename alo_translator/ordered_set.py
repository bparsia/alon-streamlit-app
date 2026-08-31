"""Insertion-ordered set, used wherever accumulation order feeds serialized output.

Plain `set` iteration order depends on PYTHONHASHSEED (randomized per process
by default), so code that iterates a `set` to assign IDs or emit axioms in
that order produces non-reproducible output across runs on identical input.
"""


class InsertionOrderedSet:
    """Set with add()/iteration/membership, ordered by first insertion."""

    def __init__(self):
        self._data: dict = {}

    def add(self, item):
        self._data[item] = None

    def __iter__(self):
        return iter(self._data)

    def __contains__(self, item):
        return item in self._data

    def __len__(self):
        return len(self._data)
