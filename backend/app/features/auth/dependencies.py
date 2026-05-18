"""FastAPI dependencies for JWT-based authentication."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .service import AuthError, PublicUser, decode_token, get_user_by_id


bearer_scheme = HTTPBearer(auto_error=False)


def _extract_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    if credentials and credentials.scheme.lower() == "bearer" and credentials.credentials:
        return credentials.credentials
    # Fallback: read raw Authorization header (covers cases where the credential
    # uses non-standard casing, e.g. "JWT").
    raw = request.headers.get("Authorization") or ""
    parts = raw.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() in {"bearer", "token", "jwt"}:
        return parts[1].strip() or None
    return None


def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> PublicUser | None:
    token = _extract_token(request, credentials)
    if not token:
        return None
    try:
        payload = decode_token(token, expected_type="access")
        user = get_user_by_id(int(payload.get("sub")))
        return user
    except Exception:
        return None


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> PublicUser:
    token = _extract_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_token",
            headers={"WWW-Authenticate": 'Bearer realm="kb"'},
        )
    try:
        payload = decode_token(token, expected_type="access")
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.code,
            headers={"WWW-Authenticate": 'Bearer realm="kb"'},
        ) from exc
    user_id_raw = payload.get("sub")
    try:
        user_id = int(user_id_raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_subject") from exc
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_not_found")
    return user
