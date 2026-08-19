# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.building.build_main import Analysis, PYZ, EXE
from PyInstaller.utils.hooks import collect_all, collect_submodules

# 强制全量收集 openai 及其所有子模块（包括 pydantic_core._pydantic_core 等 C 扩展）
openai_datas, openai_binaries, openai_hidden = collect_all('openai')

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=openai_binaries,
    datas=[
        ('assets', 'assets'),
        ('content', 'content'),
    ] + openai_datas,
    hiddenimports=openai_hidden + [
        'dotenv',
        'shared.config',
        'shared.state',
        'shared.prompts',
        'shared.memory_store',
        'shared.conversation_store',
        'shared.vignette',
        'shared.validators',
        'shared.world_state',
        'shared.scene_manager',     # V14.7：空间场景系统
        'shared.letter_manager',    # V14.3：主动来信
        'shared.template_registry', # V14.4：篇章模板注册表
        'llm.bridge',
        'shared',
        'llm',
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'shiboken6',
        'pydantic_core',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ReZeroTwin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app_icon.ico',
)
