"""Auth endpoints: register, login, refresh, me, logout."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.features.auth.dependencies import get_current_user
from app.features.auth.service import (
    AuthError,
    PublicUser,
    authenticate_user,
    issue_tokens,
    refresh_tokens,
    register_user,
)


router = APIRouter(tags=["Auth"], prefix="/v1/auth")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=2, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=8)


def _serialize_bundle(bundle: Any) -> dict[str, Any]:
    data = asdict(bundle)
    if data.get("user") is None:
        data.pop("user", None)
    return data


def _serialize_user(user: PublicUser) -> dict[str, Any]:
    return asdict(user)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> dict[str, Any]:
    try:
        user = register_user(email=str(payload.email), password=payload.password, name=payload.name)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.code) from exc
    bundle = issue_tokens(user)
    return _serialize_bundle(bundle)


@router.post("/login")
async def login(payload: LoginRequest) -> dict[str, Any]:
    try:
        user = authenticate_user(email=str(payload.email), password=payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.code) from exc
    bundle = issue_tokens(user)
    return _serialize_bundle(bundle)


@router.post("/refresh")
async def refresh(payload: RefreshRequest) -> dict[str, Any]:
    try:
        bundle = refresh_tokens(payload.refresh_token)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.code) from exc
    return _serialize_bundle(bundle)


@router.get("/me")
async def me(current_user: PublicUser = Depends(get_current_user)) -> dict[str, Any]:
    return _serialize_user(current_user)


@router.post("/logout")
async def logout(current_user: PublicUser = Depends(get_current_user)) -> dict[str, str]:
    # JWT — stateless. На клиенте достаточно удалить токены.
    # Если в будущем понадобится denylist, здесь будет вызов сервиса.
    return {"status": "ok"}
