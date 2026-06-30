"""Smoke test utility functions for kanban-standard-smoke-test."""

def greet() -> str:
    """Return a standard greeting."""
    return 'hello from kanban'


def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return a + b


def format_name(first: str, last: str) -> str:
    """Format a name as Last, First."""
    return f'{last}, {first}'


if __name__ == '__main__':
    print(f'greet() = {greet()}')
    print(f'add(2, 3) = {add(2, 3)}')
    print(f'format_name("Jane", "Doe") = {format_name("Jane", "Doe")}')
