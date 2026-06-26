from smoke_utils import add, format_name, greet, multiply


def test_greet_returns_string():
    result = greet()
    assert isinstance(result, str)
    assert result == "hello from kanban"


def test_add_positive():
    assert add(3, 5) == 8


def test_add_negative():
    assert add(-1, -2) == -3


def test_add_zero():
    assert add(5, 0) == 5


def test_format_name_standard():
    assert format_name("Alice", "Smith") == "Smith, Alice"


def test_format_name_single():
    assert format_name("Bob", "") == ", Bob"


def test_multiply_positive():
    assert multiply(3, 4) == 12


def test_multiply_zero():
    assert multiply(0, 5) == 0