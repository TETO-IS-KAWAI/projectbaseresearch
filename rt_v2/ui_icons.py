"""
ui_icons.py
assets/icons/ 폴더의 PNG(또는 SVG) 아이콘 로드

파일이 없으면 빈 QIcon 반환 → 텍스트만 표시 (오류 없음).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QIcon

from config import assets_dir

# frozen(빌드) 환경에서도 번들 에셋을 가리키도록 config 기준 경로 사용
_ICONS_DIR = assets_dir() / 'icons'

# 버튼·메뉴 권장 크기 [px]
ICON_SIZE_TOOLBAR = 20
ICON_SIZE_WINDOW  = 32


@lru_cache(maxsize=128)
def icon(name: str) -> QIcon:
    """
    assets/icons/{name}.png 또는 .svg 를 QIcon 으로 반환.

    예: icon('app'), icon('reset')
    """
    for ext in ('.png', '.svg'):
        path = _ICONS_DIR / f'{name}{ext}'
        if path.is_file():
            return QIcon(str(path))
    return QIcon()


def icons_dir() -> Path:
    """아이콘 폴더 경로 (PNG 넣는 위치)."""
    return _ICONS_DIR


def has_icon(name: str) -> bool:
    return any((_ICONS_DIR / f'{name}{ext}').is_file() for ext in ('.png', '.svg'))
