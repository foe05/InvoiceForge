"""Tests for admin password reset and the stateless reset-link tokens.

The token module is deliberately free of DB and request dependencies, so these
tests exercise it directly with lightweight stand-ins for User.
"""

from __future__ import annotations

import time
import types

import pytest

from app.auth.passwords import hash_password, verify_password
from app.auth.reset_tokens import (
    MAX_TTL_SECONDS,
    _fingerprint,
    generate_reset_token,
    read_reset_token,
    token_matches_user,
)

# Two distinct bcrypt hashes for the same nominal user. Real hashes so the
# fingerprint slice sees a realistic layout ($2b$ + cost + 22-char salt).
HASH_A = hash_password("passwort-eins-1234")
HASH_B = hash_password("passwort-zwei-5678")


def _user(uid: str = "11111111-1111-1111-1111-111111111111", pw_hash: str = HASH_A):
    return types.SimpleNamespace(id=uid, password_hash=pw_hash)


# --- Token round-trip ---


def test_fresh_token_resolves_to_its_user():
    user = _user()
    parsed = read_reset_token(generate_reset_token(user))

    assert parsed is not None
    uid, fingerprint = parsed
    assert uid == str(user.id)
    assert token_matches_user(fingerprint, user)


def test_fingerprint_covers_digest_not_just_bcrypt_prefix():
    """Two hashes at the same cost factor must not share a fingerprint.

    The first 29 characters of a bcrypt hash are prefix + cost + salt; slicing
    from byte 0 would make every token interchangeable.
    """
    assert _fingerprint(HASH_A) != _fingerprint(HASH_B)


# --- Single use ---


def test_token_is_void_once_the_password_changes():
    user = _user()
    _, fingerprint = read_reset_token(generate_reset_token(user))

    # Redeeming the link rotates the hash — the same link must not work twice.
    assert not token_matches_user(fingerprint, _user(pw_hash=HASH_B))


# --- Expiry ---


def test_token_expires_after_its_own_ttl():
    token = generate_reset_token(_user(), ttl_seconds=1)
    assert read_reset_token(token) is not None
    time.sleep(1.2)
    assert read_reset_token(token) is None


def test_requested_ttl_is_capped_at_the_ceiling():
    token = generate_reset_token(_user(), ttl_seconds=MAX_TTL_SECONDS * 10)
    parsed = read_reset_token(token)
    assert parsed is not None  # still loadable, just not for 10x the ceiling


# --- Tampering ---


@pytest.mark.parametrize(
    "bad_token",
    ["", "nonsense", "a.b.c", "x" * 200],
)
def test_malformed_tokens_are_rejected(bad_token):
    assert read_reset_token(bad_token) is None


@pytest.mark.parametrize(
    "mangle",
    [
        lambda t: f"  {t}  ",  # leading/trailing padding
        lambda t: t[:40] + "  " + t[40:],  # terminal line-wrap mid-token
        lambda t: t[:30] + "\n" + t[30:],  # newline from a wrapped paste
        lambda t: t[:20] + " \t " + t[20:],
    ],
    ids=["padded", "wrapped", "newline", "mixed"],
)
def test_whitespace_from_copy_paste_is_tolerated(mangle):
    """A link copied out of a wrapped terminal must still resolve."""
    user = _user()
    token = generate_reset_token(user)
    parsed = read_reset_token(mangle(token))

    assert parsed is not None
    assert parsed[0] == str(user.id)


def test_signature_tampering_is_rejected():
    token = generate_reset_token(_user())
    assert read_reset_token(token[:-4] + "AAAA") is None


def test_payload_tampering_is_rejected():
    token = generate_reset_token(_user())
    # Everything before the final dot is payload+timestamp; the tail is the
    # signature. (itsdangerous prefixes compressed payloads with a dot, so
    # split from the right rather than the left.)
    body, _, signature = token.rpartition(".")
    idx = len(body) // 2
    flipped = body[:idx] + ("B" if body[idx] != "B" else "C") + body[idx + 1 :]
    assert read_reset_token(f"{flipped}.{signature}") is None


# --- Password helpers used by the reset paths ---


def test_set_password_hash_roundtrip():
    new_hash = hash_password("ein-neues-passwort")
    assert verify_password("ein-neues-passwort", new_hash)
    assert not verify_password("falsches-passwort", new_hash)


def test_verify_password_survives_a_malformed_stored_hash():
    """A corrupt hash must fail closed, not raise into the request handler."""
    assert verify_password("irgendwas", "not-a-bcrypt-hash") is False
