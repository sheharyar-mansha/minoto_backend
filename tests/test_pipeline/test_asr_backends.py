from __future__ import annotations

from pipeline.asr.backends import _is_degenerate


def test_flags_runaway_repetition():
    assert _is_degenerate("you you you you") is True
    assert _is_degenerate("no no no no no") is True


def test_keeps_real_speech():
    assert _is_degenerate("hey guys how are you") is False
    assert _is_degenerate("we need to optimize the application") is False


def test_short_repeats_are_not_flagged():
    # Fewer than 4 tokens is never treated as a hallucination loop.
    assert _is_degenerate("no no no") is False
    assert _is_degenerate("yeah") is False
    assert _is_degenerate("") is False
