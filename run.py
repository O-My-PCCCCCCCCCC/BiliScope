"""一键启动 BiliScope。PyInstaller 打包时 reload 关闭。"""
import socket
import sys

import app.main  # noqa: F401  确保打包时 app.main 被收集
import uvicorn

PORT = 8000


def port_in_use(port: int) -> bool:
    try:
        with socket.socket() as s:
            s.bind(("127.0.0.1", port))
            return False
    except OSError:
        return True


def _halt(msg: str) -> None:
    """提示后退出；冻结模式下保持窗口可见让用户看清原因。"""
    if getattr(sys, "frozen", False):
        input(f"\n{msg}\n按回车退出...")
    else:
        print(msg)
    sys.exit(1)


if __name__ == "__main__":
    if port_in_use(PORT):
        _halt(
            f"端口 {PORT} 已被占用（可能已有 BiliScope 在运行，或该端口被其他程序使用）。\n"
            f"请先关闭正在运行的 BiliScope 或其他占用 8000 端口的程序，再重新启动。"
        )
    reload = not getattr(sys, "frozen", False)
    try:
        uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=reload)
    except SystemExit:
        raise
    except Exception as e:
        _halt(f"启动失败：{e}")
