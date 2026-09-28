import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.api.dependencies import DatabaseSession
from app.db.base import utc_now
from app.models.assistant import ServiceToken

READ_SCOPE = "finance:read"
SIMULATE_SCOPE = "finance:simulate"
SUGGEST_SCOPE = "finance:suggest"
WRITE_SCOPE = "finance:write"
DEFAULT_HERMES_SCOPES = [READ_SCOPE, SIMULATE_SCOPE, SUGGEST_SCOPE]
ALL_SERVICE_SCOPES = [*DEFAULT_HERMES_SCOPES, WRITE_SCOPE]
TOKEN_PREFIX_LENGTH = 16

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ServicePrincipal:
    token_id: UUID
    name: str
    scopes: frozenset[str]


def token_digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_service_token() -> str:
    return f"fst_{secrets.token_urlsafe(32)}"


def require_service_scope(required_scope: str):
    def authenticate(
        session: DatabaseSession,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> ServicePrincipal:
        if credentials is None or credentials.scheme.casefold() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "service_token_required", "message": "Service token required"},
            )
        raw_token = credentials.credentials
        if len(raw_token) < TOKEN_PREFIX_LENGTH:
            token = None
        else:
            token = session.scalar(
                select(ServiceToken).where(
                    ServiceToken.token_prefix == raw_token[:TOKEN_PREFIX_LENGTH],
                    ServiceToken.deleted_at.is_(None),
                )
            )
        now = datetime.now(UTC)
        valid = (
            token is not None
            and token.is_active
            and token.revoked_at is None
            and (token.expires_at is None or token.expires_at > now)
            and hmac.compare_digest(token.token_hash, token_digest(raw_token))
        )
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_service_token", "message": "Invalid service token"},
            )
        if required_scope not in token.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "insufficient_scope", "message": "Service token lacks scope"},
            )
        token.last_used_at = utc_now()
        session.commit()
        return ServicePrincipal(token.id, token.name, frozenset(token.scopes))

    return authenticate
