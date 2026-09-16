from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.db.session import get_db
from supportflow.core.auth import SESSION_COOKIE_NAME, auth_settings
from supportflow.schemas.result import Success
from supportflow.schemas.login import LoginRequest, LoginResponse
from supportflow.services.login import authenticate_user, create_login_session

router = APIRouter(tags=["login"])


@router.post("/login", response_model=Success[LoginResponse])
async def login(
    request: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> Success[LoginResponse]:
    user = await authenticate_user(db, request)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="用户名或密码错误，或账号不可用",
        )
    login_result = LoginResponse(
        id=user.id,
        username=user.username,
        role=user.role,
    )
    token, expires_at = await create_login_session(
        db, user.id, auth_settings.SESSION_TTL_SECONDS
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=auth_settings.SESSION_TTL_SECONDS,
        expires=expires_at.replace(tzinfo=timezone.utc),
        path="/",
        httponly=True,
        secure=auth_settings.SESSION_COOKIE_SECURE,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return Success[LoginResponse](data=login_result)
