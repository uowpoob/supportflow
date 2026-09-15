from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.db.session import get_db
from supportflow.schemas import result
from supportflow.schemas.login import LoginRequest, LoginResponse
from supportflow.services.login import authenticate_user

router = APIRouter(tags=["login"])


@router.post("/login")
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, request)


    if user is None:
        raise HTTPException(
            status_code=401,
            detail="用户名或密码错误，或账号不可用",
        )
    login_result=LoginResponse(
        id=user.id,
        username=user.username,
        role=user.role,
    )


    return result.success(
        data=login_result.model_dump(mode="json")
    )