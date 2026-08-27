"""Password hashing and verification using bcrypt directly.

We use the `bcrypt` library directly rather than passlib: the passlib bcrypt
adapter has had ongoing version-detection issues with bcrypt 4.x that produce
spurious '72-byte limit' errors even on short inputs.

bcrypt itself imposes a real 72-byte input limit; we validate that explicitly
and reject longer inputs at the API surface. Users in practice never hit it.
"""

from __future__ import annotations

import logging
import secrets

import bcrypt

logger = logging.getLogger(__name__)

# Cost factor: 12 rounds ≈ 250 ms on modern x86. Bumping this in the future
# does not invalidate existing hashes — they keep working at their old cost.
_BCRYPT_ROUNDS = 12

# bcrypt's hard input limit (everything beyond byte 72 is silently ignored,
# which is a security issue if we permit longer passwords).
PASSWORD_MAX_BYTES = 72


class PasswordTooLongError(ValueError):
    """Password exceeds bcrypt's 72-byte input limit."""


def _check_length(plaintext: str) -> bytes:
    encoded = plaintext.encode("utf-8")
    if len(encoded) > PASSWORD_MAX_BYTES:
        raise PasswordTooLongError(
            f"Passwort zu lang: {len(encoded)} bytes, maximal {PASSWORD_MAX_BYTES}"
        )
    return encoded


def hash_password(plaintext: str) -> str:
    """Return a bcrypt hash for the given password."""
    encoded = _check_length(plaintext)
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("ascii")


def verify_password(plaintext: str, hashed: str) -> bool:
    """Constant-time check of plaintext against a stored bcrypt hash."""
    try:
        encoded = _check_length(plaintext)
    except PasswordTooLongError:
        return False
    try:
        return bcrypt.checkpw(encoded, hashed.encode("ascii"))
    except Exception:
        # Malformed hash, encoding error — never propagate as auth success.
        # Log it: silently returning False here is indistinguishable from a
        # wrong password and has cost real debugging time before.
        logger.warning("bcrypt verification raised; treating as failed login", exc_info=True)
        return False


def generate_initial_password(length: int = 16) -> str:
    """Generate a URL-safe random password for admin-created users.

    The user is forced to change this on first login (must_change_password=True).
    """
    return secrets.token_urlsafe(length)
