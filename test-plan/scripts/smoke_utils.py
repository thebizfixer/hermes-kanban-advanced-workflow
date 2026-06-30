"""Kanban smoke test utility functions."""


def greet() -> str:
    """Return a standard greeting string."""
    return 'hello from kanban'


def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return a + b


def multiply(a: int, b: int) -> int:
    """Return the product of two integers."""
    return a * b


def format_name(first: str, last: str) -> str:
    """Format a name as 'Last, First'."""
    return f'{last}, {first}'


if __name__ == '__main__':
    print(greet())
    print(f'2 + 3 = {add(2, 3)}')
    print(format_name('Jane', 'Doe'))
