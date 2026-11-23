"""
packaging/make_release.py — 배포 파일을 한 번에 만든다

    python packaging/make_release.py                 # exe 빌드 → 설치 파일 → 휴대용 zip → SHA256
    python packaging/make_release.py --skip-build    # 이미 빌드된 dist/RWA_HI21cm 사용

결과 (rt_v2/dist/release/):
    RWA_HI21cm-<버전>-setup.exe              설치 파일 (시작 메뉴·바탕화면 바로가기, 제거 지원)
    RWA_HI21cm-<버전>-portable-win64.zip     압축만 풀어 쓰는 휴대용 판
    SHA256SUMS.txt                           내려받은 파일 확인용 해시
    RELEASE_NOTES.md                         GitHub Release 본문 (CHANGELOG.md 의 해당 버전)

버전은 api.py 의 APP_VERSION 하나에서 읽는다. 설치 파일 컴파일에는 Inno Setup 6 (ISCC.exe)이
필요하다 — 없으면 휴대용 zip 만 만든다.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import zipfile
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # rt_v2/
REPO = ROOT.parent
DIST = ROOT / 'dist'
APP_DIR = DIST / 'RWA_HI21cm'
OUT = DIST / 'release'


def app_version() -> str:
    m = re.search(r"APP_VERSION\s*=\s*'([\d.]+)'", (ROOT / 'api.py').read_text(encoding='utf-8'))
    if not m:
        sys.exit('api.py 에서 APP_VERSION 을 찾지 못했습니다')
    return m.group(1)


def step(msg: str) -> None:
    print(f'\n=== {msg} ===', flush=True)


def build_exe() -> None:
    step('PyInstaller 빌드')
    if APP_DIR.exists():
        shutil.rmtree(APP_DIR)
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    str(ROOT / 'packaging' / 'rwa_app.spec')], cwd=ROOT, check=True)


def _dist_licenses(pkg: str) -> list[tuple[Path, Path]]:
    """설치된 패키지의 라이선스 파일들 → (원본 경로, dist-info 기준 상대 경로).
    numpy 처럼 포함한 하위 라이브러리 라이선스가 여러 개인 경우 원래 폴더 구조를 유지한다."""
    try:
        files = metadata.files(pkg) or []
    except metadata.PackageNotFoundError:
        return []
    out = []
    for f in files:
        parts = Path(str(f)).parts
        if not parts or not parts[0].endswith('.dist-info'):
            continue
        if f.name.upper().startswith(('LICENSE', 'COPYING')) or (len(parts) > 2 and parts[1] == 'licenses'):
            rel = Path(*parts[2:]) if len(parts) > 2 and parts[1] == 'licenses' else Path(*parts[1:])
            out.append((Path(f.locate()), rel))
    return out


def gather_licenses() -> None:
    """설치 폴더 맨 위 licenses/ 에 모든 라이선스·고지를 모은다 (휴대용 zip 에도 그대로 들어감)."""
    step('라이선스 고지 모으기')
    dst = APP_DIR / 'licenses'
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / 'LICENSE', dst / 'LICENSE.txt')
    src = ROOT / 'licenses'
    for f in src.iterdir():
        shutil.copy2(f, dst / f.name)
    # 바로가기에서 메모장으로 열리도록 .txt 사본도
    shutil.copy2(src / 'THIRD_PARTY_NOTICES.md', dst / 'THIRD_PARTY_NOTICES.txt')
    (dst / 'fonts').mkdir(exist_ok=True)
    for f in (ROOT / 'web' / 'fonts').glob('*.txt'):
        shutil.copy2(f, dst / 'fonts' / f.name)
    py_lic = Path(sys.base_prefix) / 'LICENSE.txt'
    if py_lic.is_file():
        shutil.copy2(py_lic, dst / 'Python-LICENSE.txt')
    for pkg, label in (('numpy', 'numpy'), ('scipy', 'scipy'), ('astropy', 'astropy'),
                       ('astropy-healpix', 'astropy_healpix'), ('pyerfa', 'pyerfa'), ('mocpy', 'mocpy')):
        if not (APP_DIR / '_internal' / label.replace('pyerfa', 'erfa')).exists():
            continue                                    # 번들에 안 들어간 패키지는 건너뜀
        for src_f, rel in _dist_licenses(pkg):
            if src_f.is_file():
                out_f = dst / label / rel
                out_f.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_f, out_f)
    (APP_DIR / '읽어보기.txt').write_text(
        f'HI 21cm 전파망원경 {app_version()}\n'
        '=================================\n\n'
        '실행: RWA_HI21cm.exe\n'
        '설정·프로젝트 저장 위치: %APPDATA%\\RWA_HI21cm\\\n'
        '화면이 깨지면: 앱의 설정 → 하드웨어 → 그래픽 가속 끄기\n\n'
        '© 2026 Team RWA (SASA 10th) · MIT License\n'
        '오픈소스 고지: licenses\\THIRD_PARTY_NOTICES.txt\n'
        'https://github.com/TETO-IS-KAWAI/projectbaseresearch\n',
        encoding='utf-8-sig')
    print('  ' + ', '.join(sorted(p.name + ('/' if p.is_dir() else '') for p in dst.iterdir())))


def find_iscc() -> Path | None:
    cands = [os.environ.get('ISCC', ''), shutil.which('ISCC') or '', shutil.which('iscc') or '',
             os.path.expandvars(r'%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe'),
             os.path.expandvars(r'%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe'),
             os.path.expandvars(r'%ProgramFiles%\Inno Setup 6\ISCC.exe')]
    for c in cands:
        if c and Path(c).is_file():
            return Path(c)
    return None


def build_installer(ver: str) -> Path | None:
    step('설치 파일 (Inno Setup)')
    iscc = find_iscc()
    if not iscc:
        print('  ISCC.exe 가 없어 설치 파일은 건너뜁니다 (Inno Setup 6 설치 필요)')
        return None
    iss = ROOT / 'packaging' / 'installer.iss'
    raw = iss.read_bytes()
    if not raw.startswith(b'\xef\xbb\xbf'):                  # 한글이 깨지지 않게 UTF-8 BOM 보장
        iss.write_bytes(b'\xef\xbb\xbf' + raw)
    subprocess.run([str(iscc), '/Q', f'/DAppVersion={ver}', f'/DSourceDir={APP_DIR}',
                    f'/DOutputDir={OUT}', str(iss)], check=True)
    out = OUT / f'RWA_HI21cm-{ver}-setup.exe'
    return out if out.is_file() else None


def build_zip(ver: str) -> Path:
    step('휴대용 zip')
    out = OUT / f'RWA_HI21cm-{ver}-portable-win64.zip'
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(APP_DIR.rglob('*')):
            if f.is_file() and '__pycache__' not in f.parts:
                z.write(f, Path('RWA_HI21cm') / f.relative_to(APP_DIR))
    return out


def release_notes(ver: str) -> Path:
    text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    m = re.search(rf'^## \[?v?{re.escape(ver)}\]?.*?$(.*?)(?=^## |\Z)', text, re.M | re.S)
    body = m.group(1).strip() if m else f'HI 21cm 전파망원경 {ver}'
    out = OUT / 'RELEASE_NOTES.md'
    out.write_text(body + '\n', encoding='utf-8')
    return out


def sha256sums(files: list[Path]) -> Path:
    out = OUT / 'SHA256SUMS.txt'
    lines = []
    for f in files:
        h = hashlib.sha256()
        with open(f, 'rb') as fp:
            for chunk in iter(lambda: fp.read(1 << 20), b''):
                h.update(chunk)
        lines.append(f'{h.hexdigest()}  {f.name}')
    out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip-build', action='store_true', help='이미 빌드된 dist/RWA_HI21cm 사용')
    a = ap.parse_args()
    ver = app_version()
    print(f'HI 21cm 전파망원경 {ver} 배포 파일 만들기')
    if not a.skip_build:
        build_exe()
    if not (APP_DIR / 'RWA_HI21cm.exe').is_file():
        sys.exit(f'{APP_DIR} 에 빌드된 exe 가 없습니다')
    OUT.mkdir(parents=True, exist_ok=True)
    gather_licenses()
    setup = build_installer(ver)
    zpath = build_zip(ver)
    notes = release_notes(ver)
    files = [p for p in (setup, zpath) if p]
    sums = sha256sums(files)
    step('완료')
    for p in files + [sums, notes]:
        print(f'  {p.relative_to(ROOT)}  ({p.stat().st_size / 1e6:,.1f} MB)')


if __name__ == '__main__':
    main()
