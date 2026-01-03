from fastapi import APIRouter
from .risk_control import router as risk_control_router
from .market import router as market_router
from .auth import router as auth_router
from .dashboard import router as dashboard_router

router = APIRouter()

router.include_router(risk_control_router)
router.include_router(market_router)
router.include_router(auth_router)
router.include_router(dashboard_router)

# Add other routers here as the application grows
# router.include_router(some_other_router)
