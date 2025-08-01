# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['smart/recibePulsov3.py'],
    pathex=[],
    binaries=[],
    datas=[('smart/templates', 'templates')],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='monitor_cardiaco',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Cambiá a False si no querés que se vea la consola negra
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='monitor_cardiaco'
)
