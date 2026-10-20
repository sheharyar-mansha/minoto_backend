"""Helpers for the one-time member temp password + the password policy."""

import secrets

# Unambiguous classes — no O/0, I/l/1 — so the owner can read the temp aloud.
_LOWER = "abcdefghijkmnpqrstuvwxyz"
_UPPER = "ABCDEFGHJKMNPQRSTUVWXYZ"
_DIGITS = "23456789"
_SPECIAL = "!@#$%&*?"
_ALL = _LOWER + _UPPER + _DIGITS + _SPECIAL

# Minimum length for any password (temp or member-chosen).
MIN_PASSWORD_LENGTH = 8


def generate_temp_password(length: int = 12) -> str:
    """A random one-time password that always satisfies the policy below:
    at least one lowercase, uppercase, digit, and special character.
    """
    length = max(MIN_PASSWORD_LENGTH, length)
    rng = secrets.SystemRandom()
    chars = [
        rng.choice(_LOWER),
        rng.choice(_UPPER),
        rng.choice(_DIGITS),
        rng.choice(_SPECIAL),
    ]
    chars += [rng.choice(_ALL) for _ in range(length - len(chars))]
    rng.shuffle(chars)
    return "".join(chars)


def password_policy_error(password: str) -> str | None:
    """Return a human-readable reason the password is too weak, or None if it's OK.

    Policy: >= 8 chars with at least one lowercase letter, one uppercase letter,
    one digit, and one special character (any non-alphanumeric).
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if not any(c.islower() for c in password):
        return "Password needs a lowercase letter."
    if not any(c.isupper() for c in password):
        return "Password needs an uppercase letter."
    if not any(c.isdigit() for c in password):
        return "Password needs a number."
    if not any(not c.isalnum() for c in password):
        return "Password needs a special character (e.g. ! @ # $ % & * ?)."
    return None
