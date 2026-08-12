"""一键启动 BiliScope。PyInstaller 打包时 reload 关闭。"""
import sys

import app.main  # noqa: F401  确保打包时 app.main 被收集
import uvicorn

if __name__ == "__main__":
    reload = not getattr(sys, "frozen", False)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=reload)
