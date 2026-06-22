def greet():
    """Return a greeting string."""
    return 'hello from kanban'


def add(a, b):
    """Return the sum of a and b."""
    return a + b


def format_name(first, last):
    """Return the name formatted as 'last, first'."""
    return f'{last}, {first}'


def multiply(a: int, b: int) -> int:
    """Return the product of a and b."""
    return a * b


if __name__ == '__main__':
    # Quick smoke test when run directly
    print(greet())
    print(add(2, 3))
    print(format_name('John', 'Doe'))
    print(multiply(3, 4))
