# -*- mode: python ; coding: utf-8 -*-
"""
rwa_app.spec — RWA HI 21cm 전파망원경 Windows 폴더형(.exe onedir) 빌드 설정 (v2)

v2 부터 화면은 Qt WebEngine 이 그리는 web/ (HTML·CSS·JS) 이고, 계산은 파이썬 그대로.
그래서 VTK/PyVista/pyqtgraph 가 빠졌고, 대신 Qt WebEngine 런타임이 들어간다.

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
for _pkg in ('astropy', 'astropy_healpix', 'erfa'):
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception as _exc:   # 미설치 패키지는 조용히 건너뜀
        print(f'[spec] collect_all({_pkg}) skipped: {_exc}')

hiddenimports += collect_submodules('scipy')

# api.py 가 함수 안에서 지연 import 하는 모듈 + Qt WebEngine/WebChannel
hiddenimports += [
    'api', 'foreground_processing', 'moc_manager',
    'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore', 'PySide6.QtWebChannel',
]

# 앱 에셋(아이콘·기본 config) + 화면(web/: HTML·CSS·JS·글꼴)
datas += [(str(ROOT / 'assets'), 'assets'), (str(ROOT / 'web'), 'web')]

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
        # v1 UI 스택 — v2 에서는 쓰지 않음
        'pyvista', 'pyvistaqt', 'vtk', 'vtkmodules', 'pyqtgraph', 'OpenGL',
        'matplotlib', 'pandas', 'PIL', 'sympy', 'jinja2',
        # 환경에 깔려 딸려오던 대용량/개발 패키지
        'torch', 'torchvision', 'torchaudio', 'tensorflow', 'numba',
        'jedi', 'IPython', 'notebook', 'pytest', 'sphinx', 'pythonwin',
    ],
    noarchive=False,
)

# ── Qt 다이어트 ─────────────────────────────────────────────
# PySide6 의 WebEngine 훅은 QML/Quick3D/Charts… 전체를 끌고 와서 500MB 가 넘는다.
# 실제 필요한 것은 QtWebEngineWidgets 의존 DLL 묶음(아래 _KEEP_QT, 빌드 산출물의
# 임포트 테이블로 확인)과 이미지 플러그인용 Svg/Pdf 뿐이다.
import re as _re
_KEEP_QT = {
    'Qt6Core', 'Qt6Gui', 'Qt6Widgets', 'Qt6Network', 'Qt6OpenGL', 'Qt6PrintSupport',
    'Qt6Positioning', 'Qt6Qml', 'Qt6QmlMeta', 'Qt6QmlModels', 'Qt6QmlWorkerScript',
    'Qt6Quick', 'Qt6QuickWidgets', 'Qt6WebChannel', 'Qt6WebEngineCore', 'Qt6WebEngineWidgets',
    'Qt6Svg', 'Qt6Pdf',
}
_DROP_PLUGINS = {'platforminputcontexts', 'position', 'qmltooling'}


def _keep(dest):
    p = str(dest).replace('\\', '/')
    if not p.startswith('PySide6/'):
        return True
    rel = p[len('PySide6/'):]
    if rel.startswith('qml/'):
        return False
    m = _re.fullmatch(r'(Qt6\w+)\.dll', rel)
    if m:
        return m.group(1) in _KEEP_QT
    if rel.startswith('plugins/'):
        return rel.split('/')[1] not in _DROP_PLUGINS
    if rel.startswith('resources/'):            # 디버그·개발자도구 리소스 제외
        return '.debug.' not in rel and 'devtools' not in rel
    if rel.startswith('translations/'):          # 한국어·영어만
        name = rel.rsplit('/', 1)[-1]
        if rel.startswith('translations/qtwebengine_locales/'):
            return name in ('en-US.pak', 'ko.pak')
        return name.endswith(('_ko.qm', '_en.qm'))
    return True


a.binaries = [e for e in a.binaries if _keep(e[0])]
a.datas = [e for e in a.datas if _keep(e[0])]

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
    upx=False,                 # UPX 는 Qt WebEngine DLL 을 깨뜨릴 수 있어 끔
    console=False,             # GUI 앱 (콘솔 창 없음)
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
