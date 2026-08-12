"""FastAPI 入口：注册 API 路由、托管前端静态文件、启动时初始化数据库。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.config import APP_DIR
from app.database import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    from app.scheduler import start_scheduler
    start_scheduler()
    yield


app = FastAPI(title="BiliScope", lifespan=lifespan)
app.include_router(api_router)
app.mount("/", StaticFiles(directory=str(APP_DIR / "web"), html=True), name="web")
