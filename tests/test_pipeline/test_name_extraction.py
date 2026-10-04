"""Pure-logic tests for spoken-name extraction (no audio, no models)."""

from __future__ import annotations

import pytest

from pipeline.enroll import extract_spoken_name


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Hi, my name is Sara Ahmed and I lead design.", "Sara Ahmed"),
        ("my name is john", "John"),
        ("Hello everyone, I'm Bilal.", "Bilal"),
        ("I am Bilal", "Bilal"),
        ("I am Fatima Khan, the project manager.", "Fatima Khan"),
        ("Hey, this is Omar from marketing.", "Omar"),
        ("Good morning, my name is  Zara   Malik , nice to meet you.", "Zara Malik"),
    ],
)
def test_extracts_name_with_regex(text, expected):
    name, source = extract_spoken_name(text)
    assert name == expected
    assert source == "intro_regex"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "Let's get started with the quarterly review.",
        "I am going to present the roadmap today.",  # stop-word first token
        "I'm really happy to be here.",  # stop-word first token
    ],
)
def test_no_name_returns_none(text):
    name, source = extract_spoken_name(text)
    assert name is None
    assert source is None


def test_only_first_two_tokens_kept():
    name, _ = extract_spoken_name("My name is Mary Jane Watson from accounting.")
    assert name == "Mary Jane"


def test_first_matching_pattern_wins():
    # "my name is" is higher priority than "this is".
    name, _ = extract_spoken_name("This is a test. My name is Alice.")
    assert name == "Alice"
