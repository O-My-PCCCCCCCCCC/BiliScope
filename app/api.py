"""REST API 路由。"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/ping")
def ping() -> dict:
    return {"ok": True}
