"""Tests for the owner-confirmed spoken name ("name heard" check after enrollment)."""

import pytest
from pydantic import ValidationError

from api.v1.members import resolve_manual_spoken_name
from schemas.member import MemberUpdate


# --- normalization helper ---------------------------------------------------

def test_non_empty_name_is_kept_and_marked_manual():
    assert resolve_manual_spoken_name("Ali Khan") == ("Ali Khan", "manual")


def test_name_is_trimmed():
    assert resolve_manual_spoken_name("  Ali Khan  ") == ("Ali Khan", "manual")


def test_empty_or_whitespace_clears_the_name():
    assert resolve_manual_spoken_name("") == (None, None)
    assert resolve_manual_spoken_name("   ") == (None, None)


# --- schema contract --------------------------------------------------------

def test_member_update_accepts_spoken_name():
    assert MemberUpdate(spoken_name="Ayesha").spoken_name == "Ayesha"


def test_member_update_spoken_name_is_optional():
    # Omitting it (e.g. a name/email-only edit) leaves it None -> endpoint skips it.
    assert MemberUpdate(name="Ali").spoken_name is None


def test_member_update_spoken_name_length_capped():
    with pytest.raises(ValidationError):
        MemberUpdate(spoken_name="x" * 256)
