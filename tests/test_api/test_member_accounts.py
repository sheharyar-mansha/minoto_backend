"""Unit tests for the member-account primitives (temp password + token type)."""

from services.security import (
    create_access_token,
    decode_token_claims,
    decode_token_subject,
)
from utils.passwords import generate_temp_password, password_policy_error


def test_temp_password_meets_policy():
    for _ in range(50):
        p = generate_temp_password()
        assert len(p) >= 8
        assert password_policy_error(p) is None  # upper + lower + digit + special


def test_temp_password_respects_minimum():
    assert len(generate_temp_password(3)) >= 8


def test_temp_password_is_random():
    assert generate_temp_password() != generate_temp_password()


def test_password_policy_rejects_weak():
    assert password_policy_error("short1!") is not None  # too short
    assert password_policy_error("alllowercase1!") is not None  # no uppercase
    assert password_policy_error("ALLUPPERCASE1!") is not None  # no lowercase
    assert password_policy_error("NoNumber!!") is not None  # no digit
    assert password_policy_error("NoSpecial12") is not None  # no special
    assert password_policy_error("GoodPass1!") is None


def test_member_token_carries_typ():
    tok = create_access_token("abc", typ="member")
    claims = decode_token_claims(tok)
    assert claims is not None
    assert claims["sub"] == "abc"
    assert claims["typ"] == "member"
    assert decode_token_subject(tok) == "abc"


def test_owner_token_has_no_typ():
    claims = decode_token_claims(create_access_token("owner1"))
    assert claims is not None
    assert claims.get("typ") is None
