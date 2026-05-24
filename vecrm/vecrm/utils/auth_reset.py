# Copyright (c) 2026, Vinay Enterprises and contributors
# For license information, please see license.txt

"""Auth reset token primitives -- pure crypto, no Frappe context.

Used by vecrm.api.{request,complete}_{password,pin}_reset.
Sibling of vecrm.vecrm.utils.roles (S25); zero Frappe imports keeps these
trivially unit-testable.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Final


# Token format: 32 random bytes, base64url-encoded -> ~43 chars URL-safe.
# 256 bits of entropy; well above brute-force tractability.
TOKEN_BYTES: Final[int] = 32

# Default lifetime: 30 minutes (matches the lockout-minutes shape from
# vecrm.api._LOCKOUT_MINUTES = 15; doubled because reset emails may sit in
# inbox queues for several minutes before delivery).
DEFAULT_TOKEN_TTL_MINUTES: Final[int] = 30

# Rate limit: 3 reset requests per employee per 15-min window.
# Window mirrors vecrm.api._LOCKOUT_MINUTES.
RATE_LIMIT_WINDOW_MINUTES: Final[int] = 15
RATE_LIMIT_MAX_REQUESTS: Final[int] = 3


def generate_token() -> tuple[str, str]:
    """Generate a fresh reset token.

    Returns:
        (raw_token, token_hash):
          - raw_token: the URL-safe token to embed in the emailed link.
          - token_hash: the sha256 hex digest to store in the DB. The raw
            token MUST NEVER be persisted; only the hash.
    """
    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    token_hash = hash_token(raw_token)
    return raw_token, token_hash


def hash_token(raw_token: str) -> str:
    """sha256 hex digest of the raw token.

    Used at both storage time (after generate_token) and lookup time (after
    receiving a candidate token in complete_*_reset). Deterministic: identical
    output for identical input across processes/machines.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    """Constant-time string comparison via hmac.compare_digest.

    Prevents timing-oracle attacks for any future flow that needs to compare
    raw strings (not hashes). The current reset flow compares sha256 hashes
    via SQL equality, which is timing-safe in this context because the
    attacker already knows the candidate hash (they computed it from their
    own input); but this helper is banked for any later flow that compares
    sensitive raw material directly.
    """
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
