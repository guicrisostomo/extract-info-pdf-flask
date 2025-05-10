# -*- mode: python ; coding: utf-8 -*-

import os
import sys

# Caminho dinâmico para o ambiente virtual
project_dir = os.path.abspath(os.path.dirname(sys.argv[0]))
venv_site_packages = os.path.join(project_dir, ".venv", "Lib", "site-packages")

a = Analysis(
    ['iniciar_gui.py'],
    pathex=[venv_site_packages],  # Adiciona o caminho dinâmico do venv
    binaries=[],
    datas=[('main.py', '.')],  # Inclui o arquivo main.py
    hiddenimports=['uvicorn'],  # Inclui o uvicorn explicitamente
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
    name='iniciar_gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Oculta o terminal
    disable_windowed_traceback=False,
    argv_emulation=False,
    windowed=True,
    onefile=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)