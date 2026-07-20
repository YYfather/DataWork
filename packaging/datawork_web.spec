# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
STATIC = ROOT / "datawork" / "web" / "static"
TEMPLATES = ROOT / "datawork" / "report" / "templates"

a = Analysis(
    [str(ROOT / "scripts" / "desktop_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(STATIC), "datawork/web/static"),
        (str(TEMPLATES), "datawork/report/templates"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "statsmodels.formula.api",
        "statsmodels.multivariate.manova",
        "openpyxl",
        *collect_submodules("keyring.backends"),
    ],
    hookspath=[],
    hooksconfig={"matplotlib": {"backends": ["Agg"]}},
    runtime_hooks=[],
    excludes=[
        "streamlit", "IPython", "pytest", "py", "jedi", "parso",
        "jupyter", "jupyter_client", "jupyter_core", "nbformat", "notebook",
        "tkinter", "_tkinter", "torch", "tensorflow", "zmq",
        "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="datawork-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
