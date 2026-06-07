"""Kanban-Advanced dashboard plugin — backend API routes.

Mounted at /api/plugins/kanban-advanced/ by the dashboard plugin system.
"""
from fastapi import APIRouter

router = APIRouter()

@router.get("/status")
async def status():
    return {"ok": True, "config_exists": False}
