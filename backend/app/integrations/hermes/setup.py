import argparse

from sqlalchemy import select

from app.core.service_auth import (
    DEFAULT_HERMES_SCOPES,
    TOKEN_PREFIX_LENGTH,
    WRITE_SCOPE,
    issue_service_token,
    token_digest,
)
from app.db.session import SessionLocal
from app.models.assistant import ServiceToken


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or rotate a scoped Hermes service token")
    parser.add_argument("--name", default="hermes-local")
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="Allow confirmed transaction/category writes (disabled by default)",
    )
    args = parser.parse_args()
    raw_token = issue_service_token()
    scopes = [*DEFAULT_HERMES_SCOPES]
    if args.allow_write:
        scopes.append(WRITE_SCOPE)
    with SessionLocal() as session:
        token = session.scalar(select(ServiceToken).where(ServiceToken.name == args.name))
        if token is None:
            token = ServiceToken(
                name=args.name,
                token_prefix=raw_token[:TOKEN_PREFIX_LENGTH],
                token_hash=token_digest(raw_token),
                scopes=scopes,
                is_active=True,
            )
            session.add(token)
        else:
            token.token_prefix = raw_token[:TOKEN_PREFIX_LENGTH]
            token.token_hash = token_digest(raw_token)
            token.scopes = scopes
            token.is_active = True
            token.revoked_at = None
            token.deleted_at = None
        session.commit()
    print("Token created. Store it in the Hermes-only environment file; it is shown once:")
    print(raw_token)
    print(f"Scopes: {', '.join(scopes)}")


if __name__ == "__main__":
    main()
