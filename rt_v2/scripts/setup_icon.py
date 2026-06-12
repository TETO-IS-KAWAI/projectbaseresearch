#!/usr/bin/env python3
"""
setup_icon.py
run.pyw 바로가기(.lnk)를 만들고 앱 아이콘을 지정 (선택, 1회만 실행).

실행:  python scripts/setup_icon.py
필요:  pip install pywin32   (Windows 전용)

앱 실행 자체에는 필요 없습니다 — 바탕화면 아이콘이 필요할 때만 쓰세요.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # rt_v2/


def main() -> int:
    try:
        import win32com.client
    except ImportError:
        print('win32com 라이브러리 필요: pip install pywin32', file=sys.stderr)
        return 1

    pyw_path  = ROOT / 'run.pyw'
    if not pyw_path.exists():
        print('run.pyw 를 찾을 수 없습니다.', file=sys.stderr)
        return 1

    icons_dir = ROOT / 'assets' / 'icons'
    ico_path  = icons_dir / 'app.ico'
    png_path  = icons_dir / 'app.png'

    # Windows 바로가기 아이콘은 .ico 만 인식한다. (PNG 는 빈 아이콘으로 뜸)
    # app.ico 가 없으면 app.png 에서 자동 생성한다.
    if not ico_path.exists() and png_path.exists():
        try:
            from PIL import Image
            Image.open(png_path).convert('RGBA').save(
                ico_path, format='ICO',
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                       (64, 64), (128, 128), (256, 256)])
            print(f'app.ico 생성 (app.png 기반): {ico_path}')
        except Exception as e:
            print(f'app.ico 생성 실패({e}) — Pillow 설치 권장: pip install pillow',
                  file=sys.stderr)

    if not ico_path.exists():
        print('app.ico 가 없어 바로가기 아이콘을 지정할 수 없습니다.\n'
              '  assets/icons/app.png 를 넣고 Pillow 설치 후 다시 실행하세요.',
              file=sys.stderr)
        return 1
    icon_path = ico_path

    shell         = win32com.client.Dispatch('WScript.Shell')
    shortcut_path = str(ROOT / 'RT_망원경.lnk')
    shortcut      = shell.CreateShortCut(shortcut_path)
    shortcut.TargetPath       = str(pyw_path)
    shortcut.WorkingDirectory = str(ROOT)
    shortcut.IconLocation     = str(icon_path)
    shortcut.save()

    print(f'바로가기 생성: {shortcut_path}')
    print(f'아이콘: {icon_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
