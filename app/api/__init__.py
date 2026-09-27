from fastapi import APIRouter

from app.api import approvals, health, incidents

api_router = APIRouter()
api_router.include_router(incidents.router)
api_router.include_router(approvals.router)
api_router.include_router(health.router)
