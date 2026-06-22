"""Tests for smoke_utils module."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_utils import greet, add, format_name, multiply


class TestGreet:
    def test_greet_returns_string(self):
        result = greet()
        assert isinstance(result, str)
        assert result != ''


class TestAdd:
    def test_add_positive(self):
        assert add(2, 3) == 5

    def test_add_negative(self):
        assert add(-1, -1) == -2

    def test_add_zero(self):
        assert add(0, 5) == 5


class TestFormatName:
    def test_format_name_standard(self):
        assert format_name('Jane', 'Doe') == 'Doe, Jane'

    def test_format_name_single(self):
        assert format_name('Madonna', '') == ', Madonna'


class TestMultiply:
    def test_multiply_positive(self):
        assert multiply(3, 4) == 12

    def test_multiply_zero(self):
        assert multiply(0, 5) == 0
