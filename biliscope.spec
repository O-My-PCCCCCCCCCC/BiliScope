# -*- mode: python ; coding: utf-8 -*-
"""BiliScope PyInstaller 打包配置（单文件 EXE）。"""
from PyInstaller.utils.hooks import collect_all

datas = [('web', 'web')]
hiddenimports = [
    'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
    'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off',
    'apscheduler.schedulers.background',
]

for pkg in ['anthropic', 'openai', 'yt_dlp', 'apscheduler', 'httpx', 'pydantic']:
    try:
        d, h, b = collect_all(pkg)
        datas += d
        hiddenimports += h
    except Exception:
        pass

a = Analysis(['run.py'], pathex=[], binaries=[], datas=datas,
             hiddenimports=hiddenimports, hookspath=[], runtime_hooks=[],
             excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name='BiliScope', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=True, console=True,
          version='version_info.py')
