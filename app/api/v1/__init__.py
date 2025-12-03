from fastapi import APIRouter
from .risk_control import router as risk_control_router

router = APIRouter()

router.include_router(risk_control_router)

# Add other routers here as the application grows
# router.include_router(some_other_router)
