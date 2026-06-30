"""Pytest tests for smoke_utils module — kanban-standard-smoke-test Card 2."""

from smoke_utils import greet, add, format_name


def test_greet_returns_string():
    """greet() returns a non-empty string."""
    result = greet()
    assert isinstance(result, str)
    assert result != ""


def test_add_positive():
    """add() works with positive integers."""
    assert add(2, 3) == 5


def test_add_negative():
    """add() works with negative integers."""
    assert add(-1, -1) == -2


def test_add_zero():
    """add() works with zero."""
    assert add(0, 5) == 5


def test_format_name_standard():
    """format_name() returns 'Last, First' format."""
    assert format_name("Jane", "Doe") == "Doe, Jane"


def test_format_name_single():
    """format_name() handles single-name input."""
    assert format_name("Madonna", "") == ", Madonna"
