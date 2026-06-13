# -*- mode: python ; coding: utf-8 -*-
"""
rwa_app_lite.spec — 경량(Lite) 빌드: 3D 뷰어(VTK/pyvista) 제거

3D 전천 히트맵 탭이 빠지고 '은하 조감도 / 나선팔'(pyqtgraph) 탭만 남습니다.
VTK·matplotlib·pandas 미포함으로 용량이 크게 줄어듭니다(전체판 대비 ~수백 MB↓).
main_app.py 는 pyvista import 가 실패하면 3D 탭을 자동으로 건너뜁니다.

빌드:
    packaging\\build_lite.bat
  또는
    python -m PyInstaller --noconfirm --clean packaging\\rwa_app_lite.spec

결과:
    dist/RWA_HI21cm_Lite/RWA_HI21cm_Lite.exe
"""

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT  = Path(globals().get('SPECPATH', os.getcwd())).resolve().parent
ENTRY = str(ROOT / 'run.pyw')

datas, binaries, hiddenimports = [], [], []

# 경량판: pyvista/VTK 는 수집하지 않는다.
for _pkg in ('astropy', 'astropy_healpix', 'erfa'):
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception as _exc:
        print(f'[spec] collect_all({_pkg}) skipped: {_exc}')

hiddenimports += collect_submodules('scipy')

# 앱 에셋(아이콘·기본 config) 번들
datas += [(str(ROOT / 'assets'), 'assets')]

a = Analysis(
    [ENTRY],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'PyQt5', 'PyQt6', 'PySide2',
        # ★ 경량판 핵심: 3D 스택 통째 제외
        'pyvista', 'pyvistaqt', 'vtk', 'vtkmodules',
        'matplotlib',                 # pyvista 없으면 GUI 에 불필요
        'mocpy', 'pandas',            # 커버리지/MOC 는 3D 탭 기능 → 함께 제거
        # 환경에 깔려 딸려오던 대용량/개발 패키지
        'torch', 'torchvision', 'torchaudio', 'tensorflow', 'numba',
        'jedi', 'IPython', 'notebook', 'pytest', 'sphinx', 'pythonwin',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RWA_HI21cm_Lite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / 'assets' / 'icons' / 'app.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='RWA_HI21cm_Lite',
)
