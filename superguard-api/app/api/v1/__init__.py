"""app.api.v1 package"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    sites,
    cameras,
    detectors,
    actuators,
    alarms,
    notifiers,
    system,
    websocket,
    detection,
    rules,
)

api_router = APIRouter()

# Auth (no prefix, top-level under /api/v1)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# Sites
api_router.include_router(sites.router, prefix="/sites", tags=["sites"])

# Nested resources (routers already have /sites/{site_id} prefix)
api_router.include_router(cameras.router, tags=["cameras"])
api_router.include_router(detectors.router, tags=["detectors"])
api_router.include_router(actuators.router, tags=["actuators"])
api_router.include_router(alarms.router, tags=["alarms"])
api_router.include_router(notifiers.router, tags=["notifiers"])
api_router.include_router(rules.router, tags=["rules"])

# System (health, metrics, logs)
api_router.include_router(system.router, prefix="/system", tags=["system"])

# Detection control
api_router.include_router(detection.router, prefix="/detection", tags=["detection"])

# WebSocket
api_router.include_router(websocket.router, tags=["websocket"])