"""File containing all of the utility classes and methods for the backend."""

def safe_format(template: str, values: dict, fallback: str) -> str:
    """Formats an admin-provided template. If the template has unknown placeholders or stray braces,
    the fallback template is used instead so that the automod still works."""
    try:
        return template.format_map(values)
    except (KeyError, IndexError, ValueError, AttributeError):
        print(f"Invalid response template, falling back to the default one: {template!r}")
        return fallback.format_map(values)

class OrderedSet:
    "Ordered set that leverages the dictionary's set like structure and order"
    def __init__(self, iterable=None):
        # Use a dictionary where keys are items and values are True
        self._data = {}
        if iterable is not None:
            for item in iterable:
                self.add(item)

    def add(self, item):
        self._data[item] = True

    def discard(self, item):
        self._data.pop(item, None)

    def __contains__(self, item):
        return item in self._data

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __repr__(self):
        return f"{self.__class__.__name__}([{', '.join(repr(x) for x in self._data)}])"

    def __eq__(self, other):
        # Order-insensitive, like a regular set. Needed for dataclass comparisons of configs.
        if isinstance(other, OrderedSet):
            return self._data.keys() == other._data.keys()
        if isinstance(other, set):
            return self._data.keys() == other
        return NotImplemented

    __hash__ = None # type: ignore | mutable, so unhashable like a regular set

    # Set Mathematics: Union (|)
    def __or__(self, other):
        if not isinstance(other, (OrderedSet, set)):
            return NotImplemented
        return OrderedSet(list(self) + list(other))

    # Set Mathematics: Intersection (&)
    def __and__(self, other):
        if not isinstance(other, (OrderedSet, set)):
            return NotImplemented
        return OrderedSet(item for item in self if item in other)
    