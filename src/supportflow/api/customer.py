

from fastapi import APIRouter

from supportflow.schemas import result

router = APIRouter(prefix="/customer", tags=["customer"])

@router.get("/")
async def root():
    return result.success()

@router.get("/orders")
async def get_orders():
    return result.success()

@router.get("/session")
async def get_session():
    return result.success()
