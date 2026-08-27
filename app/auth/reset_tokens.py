"""Stateless password-reset tokens.

Tokens are signed with `settings.app_secret_key` via itsdangerous — there is no
token table and no cleanup job. Two properties fall out of the payload design:

* **Expiry** — `URLSafeTimedSerializer` stamps the signing time; `max_age` on
  load rejects anything older.
* **Single use** — the payload carries a prefix of the user's *current* password
  hash. Redeeming the token changes the hash, so the prefix no longer matches
  and the same link cannot be replayed. Changing the password by any other route
  invalidates outstanding links too, which is what we want.

Rotating `app_secret_key` invalidates all outstanding tokens (and all sessions).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

if TYPE_CHECKING:
    from app.db.models import User

# Namespace separator so a reset token can never be confused with a session
# cookie signed by the same key.
_SALT = "invoiceforge.password-reset.v1"

# How much of the bcrypt hash goes into the token. The bcrypt prefix and salt
# occupy the first 29 characters, so slice past them to capture actual digest
# bytes — otherwise every hash for a given cost factor would share a prefix.
_HASH_FINGERPRINT_START = 29
_HASH_FINGERPRINT_LEN = 16

DEFAULT_TTL_SECONDS = 24 * 3600

# Hard ceiling applied when loading, independent of the TTL a token claims —
# a tampered payload cannot extend its own lifetime beyond this.
MAX_TTL_SECONDS = 30 * 24 * 3600


def _fingerprint(password_hash: str) -> str:
    """Return the slice of the stored hash that pins a token to one password."""
    return password_hash[_HASH_FINGERPRINT_START : _HASH_FINGERPRINT_START + _HASH_FINGERPRINT_LEN]


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.app_secret_key, salt=_SALT)


def generate_reset_token(user: User, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """Create a single-use reset token for `user`, valid for `ttl_seconds`.

    The TTL travels inside the signed payload so that the lifetime chosen when
    the link was issued is the one enforced at redemption.
    """
    ttl = max(1, min(int(ttl_seconds), MAX_TTL_SECONDS))
    return _serializer().dumps(
        {"uid": str(user.id), "fp": _fingerprint(user.password_hash), "ttl": ttl}
    )


def read_reset_token(token: str) -> tuple[str, str] | None:
    """Return `(user_id, fingerprint)` for a valid, unexpired token, else None.

    A None result means the signature is bad or the token has expired. It does
    *not* mean the token matches a user — the caller must still load the user
    and compare the fingerprint via `token_matches_user`.
    """
    try:
        # Load against the hard ceiling first, then enforce the token's own TTL.
        payload, timestamp = _serializer().loads(
            token, max_age=MAX_TTL_SECONDS, return_timestamp=True
        )
    except (SignatureExpired, BadSignature):
        return None
    if not isinstance(payload, dict):
        return None
    uid, fp, ttl = payload.get("uid"), payload.get("fp"), payload.get("ttl")
    if not isinstance(uid, str) or not isinstance(fp, str) or not isinstance(ttl, int):
        return None

    age = (datetime.now(timezone.utc) - timestamp).total_seconds()
    if age > min(ttl, MAX_TTL_SECONDS):
        return None
    return uid, fp


def token_matches_user(fingerprint: str, user: User) -> bool:
    """Check the token's hash fingerprint against the user's current password."""
    return fingerprint == _fingerprint(user.password_hash)
