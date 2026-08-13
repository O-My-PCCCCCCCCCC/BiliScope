# -*- coding: utf-8 -*-
"""PyInstaller 版本信息（EXE 右键属性里显示）。"""
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)

version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=(1, 1, 0, 0),
        prodvers=(1, 1, 0, 0),
        mask=0x3f,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo([
            StringTable('080404b0', [
                StringStruct('CompanyName', 'BiliScope'),
                StringStruct('FileDescription', 'BiliScope - B站个人数据分析工具'),
                StringStruct('FileVersion', '1.1.0.0'),
                StringStruct('InternalName', 'BiliScope'),
                StringStruct('OriginalFilename', 'BiliScope.exe'),
                StringStruct('ProductName', 'BiliScope'),
                StringStruct('ProductVersion', '1.1.0.0'),
            ]),
        ]),
        VarFileInfo([VarStruct('Translation', [2052, 1200])]),
    ],
)
