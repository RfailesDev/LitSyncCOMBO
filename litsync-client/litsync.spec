# -*- mode: python ; coding: utf-8 -*-

# Этот файл является сердцем процесса сборки PyInstaller.
# Он обеспечивает надежность и воспроизводимость.

a = Analysis(
    ['client.py'],
    pathex=[],
    binaries=[],
    datas=[('icon.png', '.')], # <-- Упаковываем иконку для трея в корень сборки
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='litsync-client',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # <-- True = есть консоль для логов
    icon='icon.ico', # <-- Иконка для самого .exe файла
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='litsync-client',
)