# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification file for PULSE Desktop Application."""
import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
PROJECT_ROOT = Path(os.path.abspath(SPECPATH))

# Collect dynamic data files and submodules for heavy ML frameworks
mediapipe_datas = collect_data_files("mediapipe")
mediapipe_submodules = collect_submodules("mediapipe")

sklearn_datas = collect_data_files("sklearn")
sklearn_submodules = collect_submodules("sklearn")

matplotlib_datas = collect_data_files("matplotlib")
matplotlib_submodules = [m for m in collect_submodules("matplotlib") if not m.startswith("matplotlib.tests")]

# Model and resource data files (placed in dedicated folders to avoid package name collision)
app_datas = [
    (str(PROJECT_ROOT / "ml" / "models" / "pose_landmarker_lite.task"), "models"),
    (str(PROJECT_ROOT / "ml" / "models" / "pulse_model.joblib"), "models"),
    (str(PROJECT_ROOT / "ml" / "models" / "model_metadata.json"), "models"),
    (str(PROJECT_ROOT / "desktop_app" / "resources" / "pulse.ico"), "resources"),
    (str(PROJECT_ROOT / "desktop_app" / "resources" / "pulse.png"), "resources"),
]

all_datas = app_datas + mediapipe_datas + sklearn_datas + matplotlib_datas

hidden_imports = list(set([
    "cv2",
    "joblib",
    "numpy",
    "requests",
    "sqlite3",
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtNetwork",
    "matplotlib",
    "matplotlib.pyplot",
    "matplotlib.figure",
    "matplotlib.backends",
    "ml.pulse_features",
    "monitor.temporal",
    "desktop_app.config",
    "desktop_app.core.audio",
    "desktop_app.core.client",
    "desktop_app.core.storage",
    "desktop_app.core.sync_service",
    "desktop_app.core.worker",
    "desktop_app.ui.main_window",
    "desktop_app.ui.theme",
    "desktop_app.ui.views.connection_view",
    "desktop_app.ui.views.history_view",
    "desktop_app.ui.views.live_view",
    "desktop_app.ui.views.settings_view",
] + mediapipe_submodules + sklearn_submodules + matplotlib_submodules))

# Exclude unnecessary large packages to optimize build size
excluded_modules = [
    "torch",
    "torchvision",
    "torchaudio",
    "tensorflow",
    "tensorboard",
    "keras",
    "IPython",
    "jupyter",
    "notebook",
    "pandas",
]

a = Analysis(
    [str(PROJECT_ROOT / "desktop_app" / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=all_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PULSE",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "desktop_app" / "resources" / "pulse.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PULSE",
)
