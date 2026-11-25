"""Read-only Bearer tokens (see models.ApiToken)."""

import hashlib
import secrets

from django.utils import timezone

from ..models import ApiToken


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_token(name: str) -> str:
    """Store a new token and return it. This is the only time it is available."""
    token = secrets.token_urlsafe(32)
    ApiToken.objects.create(name=name, sha256=hash_token(token))
    return token


def find_token(token: str) -> ApiToken | None:
    """The live ApiToken for this Bearer value, stamping its last use."""
    found = ApiToken.objects.filter(sha256=hash_token(token), revoked=False).first()
    if found:
        ApiToken.objects.filter(pk=found.pk).update(last_used=timezone.now())
    return found
