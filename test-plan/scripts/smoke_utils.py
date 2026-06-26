"""Kanban smoke test utility functions."""


def greet() -> str:
    """Return the kanban greeting."""
    return "hello from kanban"


def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return a + b


def format_name(first: str, last: str) -> str:
    """Return name in 'Last, First' format."""
    return f"{last}, {first}"


def multiply(a: int, b: int) -> int:
    return a * b


if __name__ == "__main__":
    print(greet())
    print(add(2, 3))
    print(format_name("Jane", "Doe"))
