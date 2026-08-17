"""Endpoints de cuentas: registro, login, logout y quién soy.

La sesión viaja en cookie HttpOnly: el token nunca queda al alcance de
JavaScript, así que un XSS en la UI no puede robar la sesión.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ratelimit import check_auth_rate_limit
from auth import service
from auth.db import get_db
from auth.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

# Dependencias como tipos (idioma actual de FastAPI): se declaran una vez y se
# reusan en cada firma, en vez de repetir `= Depends(...)` en los defaults.
Db = Annotated[AsyncSession, Depends(get_db)]

COOKIE_NAME = "traza_session"
SESSION_MAX_AGE = int(service.SESSION_TTL.total_seconds())

NOT_LOGGED_IN = "Necesitas iniciar sesión para investigar."
BAD_CREDENTIALS = "Correo o contraseña incorrectos."
EMAIL_TAKEN = "Ese correo ya tiene una cuenta. Inicia sesión."


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=service.MIN_PASSWORD_LENGTH, max_length=128)


class AccountOut(BaseModel):
    email: str


def _set_session_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        # Secure según el esquema REAL del request (uvicorn corre con
        # --proxy-headers, así que detrás de Render esto es https). Fijarlo en
        # True rompería el login en http://localhost durante el desarrollo.
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )


async def current_user(request: Request, db: Db) -> User | None:
    """Usuario de la sesión vigente, o None si no hay cookie válida."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return await service.user_for_token(db, token)


async def require_user(user: Annotated[User | None, Depends(current_user)]) -> User:
    """Dependency de los endpoints que cuestan tokens: sin cuenta, 401."""
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=NOT_LOGGED_IN)
    return user


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_auth_rate_limit)],
)
async def register(
    creds: Credentials, request: Request, response: Response, db: Db
) -> AccountOut:
    """Crea la cuenta y deja la sesión abierta (no obliga a loguearse aparte)."""
    try:
        user = await service.register_user(db, creds.email, creds.password)
    except service.EmailAlreadyRegistered:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=EMAIL_TAKEN) from None
    token = await service.open_session(db, user)
    _set_session_cookie(request, response, token)
    return AccountOut(email=user.email)


@router.post("/login", dependencies=[Depends(check_auth_rate_limit)])
async def login(
    creds: Credentials, request: Request, response: Response, db: Db
) -> AccountOut:
    try:
        user = await service.authenticate(db, creds.email, creds.password)
    except service.InvalidCredentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=BAD_CREDENTIALS
        ) from None
    token = await service.open_session(db, user)
    _set_session_cookie(request, response, token)
    return AccountOut(email=user.email)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: Db) -> None:
    """Cierra sesión: borra la fila y la cookie. Sin sesión también responde 204."""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        await service.close_session(db, token)
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me")
async def me(user: Annotated[User, Depends(require_user)]) -> AccountOut:
    """Sesión actual. La UI la consulta al cargar para saber qué pantalla mostrar."""
    return AccountOut(email=user.email)
