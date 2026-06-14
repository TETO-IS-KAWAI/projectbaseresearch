# -*- mode: python ; coding: utf-8 -*-
"""
rwa_app.spec — RWA HI 21cm 전파망원경 Windows 폴더형(.exe onedir) 빌드 설정

빌드:
    packaging\\build.bat
  또는
    python -m PyInstaller --noconfirm --clean packaging\\rwa_app.spec

결과:
    dist/RWA_HI21cm/RWA_HI21cm.exe   (이 폴더 통째로 배포)

사용자 설정·프로젝트는 실행 시 %APPDATA%\\RWA_HI21cm 에 저장됩니다
(config.py 의 frozen 분기 참고). 번들 안 파일은 읽기 전용입니다.
"""

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

# 이 spec 은 rt_v2/packaging/ 에 위치 → ROOT = rt_v2/
ROOT  = Path(globals().get('SPECPATH', os.getcwd())).resolve().parent
ENTRY = str(ROOT / 'run.pyw')

datas, binaries, hiddenimports = [], [], []

# 번들이 까다로운 패키지(데이터 파일·네이티브 DLL 포함)는 통째로 수집
for _pkg in ('pyvista', 'pyvistaqt', 'vtk', 'vtkmodules', 'astropy', 'astropy_healpix', 'erfa'):
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception as _exc:   # 미설치 패키지는 조용히 건너뜀
        print(f'[spec] collect_all({_pkg}) skipped: {_exc}')

hiddenimports += collect_submodules('scipy')

# sky_viewer 가 함수 내부에서 지연 import 하는 선택 모듈
hiddenimports += ['foreground_processing', 'moc_manager']

# 앱 에셋(아이콘·기본 config) 번들 → 런타임에 assets/ 로 접근
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
    # matplotlib 은 제외하면 안 됨 — pyvista 가 colormaps 용으로 필수 import 함
    excludes=[
        'tkinter', 'PyQt5', 'PyQt6', 'PySide2',
        # 앱이 쓰지 않는데 환경에 깔려 딸려온 대용량/개발 패키지 → 용량 절감
        'torch', 'torchvision', 'torchaudio',   # ★ ~365MB, 미사용
        'tensorflow', 'numba',                  # 미설치면 무시됨
        'jedi', 'IPython', 'notebook',          # jupyter/자동완성 (데스크톱 뷰어라 불필요)
        'pytest', 'sphinx', 'pythonwin',        # 개발/문서/IDE 도구
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RWA_HI21cm',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                       # GUI 앱 → 콘솔 창 없음
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
    name='RWA_HI21cm',
)
