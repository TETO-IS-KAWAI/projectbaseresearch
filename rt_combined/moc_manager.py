"""
moc_manager.py  [pymoc 버전]
MOC (Multi-Order Coverage) 관측 커버리지 관리 모듈

역할
  - 관측 완료된 (RA, Dec) 목록 → MOC 생성
  - MOC 저장 / 불러오기 (FITS)
  - MOC 를 HEALPix 마스크로 변환 (뷰어 오버레이용)
  - 목표 영역 MOC 불러와 미관측 영역 하이라이트

사용 예
  from moc_manager import MocManager

  mm = MocManager(nside=32)
  mm.add_observation(ra_deg=266.4, dec_deg=-28.9)
  mask = mm.coverage_mask()   # 관측된 픽셀 = True
  mm.save('coverage.fits')
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from astropy_healpix import HEALPix
import astropy.units as u
class MocManager:
    """
    MOC 기반 관측 커버리지 관리.
    mocpy 가 없으면 HEALPix 픽셀 집합으로 fallback.
    """

    def __init__(self, nside: int = 32):
        self._nside   = nside
        self._hp      = HEALPix(nside=nside, order='ring', frame='icrs')
        self._obs_pix : set = set()   # 관측된 HEALPix 픽셀 인덱스
        self._moc             = None  # mocpy MOC 객체 (선택)
        self._has_mocpy       = self._check_mocpy()

    def _check_mocpy(self) -> bool:
        try:
            import mocpy; return True
        except ImportError:
            return False

    # ── 관측 추가 ────────────────────────────────────────────

    def add_observation(self, ra_deg: float, dec_deg: float) -> int:
        """관측 포인트 추가. 해당 HEALPix 픽셀 인덱스 반환."""
        pix = int(self._hp.lonlat_to_healpix(ra_deg * u.deg, dec_deg * u.deg))
        self._obs_pix.add(pix)
        self._moc = None   # 캐시 무효화
        return pix

    def add_from_project(self, observations: list) -> None:
        """ProjectManager.observations 리스트에서 일괄 추가."""
        for obs in observations:
            self.add_observation(obs['ra'], obs['dec'])

    # ── MOC 생성 ─────────────────────────────────────────────

    def get_moc(self):
        """
        mocpy MOC 객체 반환.
        mocpy 없으면 None.
        """
        if not self._has_mocpy or not self._obs_pix:
            return None
        if self._moc is not None:
            return self._moc
        try:
            from mocpy import MOC
            order  = int(np.log2(self._nside))
            ipixes = np.array(list(self._obs_pix))
            self._moc = MOC.from_healpix_cells(
                ipix=ipixes,
                depth=np.full(len(ipixes), order, dtype=int),
                max_depth=order,
            )
        except Exception as e:
            print(f'MOC 생성 실패: {e}')
            self._moc = None
        return self._moc

    # ── 마스크 / 커버리지 ─────────────────────────────────────

    def coverage_mask(self) -> np.ndarray:
        """관측된 픽셀 = True 인 bool 배열 (12*nside²)."""
        mask = np.zeros(self._hp.npix, dtype=bool)
        mask[list(self._obs_pix)] = True
        return mask

    def uncovered_mask(self) -> np.ndarray:
        """미관측 픽셀 = True."""
        return ~self.coverage_mask()

    def coverage_fraction(self) -> float:
        """관측 커버리지 비율 (0~1)."""
        return len(self._obs_pix) / self._hp.npix

    # ── 저장 / 불러오기 ───────────────────────────────────────

    def save(self, path) -> Path:
        """MOC 를 FITS 로 저장. mocpy 필요."""
        moc = self.get_moc()
        if moc is None:
            raise RuntimeError('mocpy 가 설치되어 있지 않거나 관측 데이터가 없습니다.')
        out = Path(path)
        moc.save(str(out), overwrite=True)
        return out

    def load(self, path) -> None:
        """저장된 MOC FITS 불러오기."""
        if not self._has_mocpy:
            raise RuntimeError('mocpy 가 설치되어 있지 않습니다.')
        from mocpy import MOC
        self._moc = MOC.from_fits(str(path))
        # MOC → 픽셀 집합 복원
        order = int(np.log2(self._nside))
        ipix  = self._moc.flatten_at_order(order)
        self._obs_pix = set(ipix.tolist())

    # ── 오버레이 색상 배열 ────────────────────────────────────

    def overlay_colors(
        self,
        covered_color:   tuple = (0.0, 1.0, 0.0, 0.3),   # 연두, 반투명
        uncovered_color: tuple = (1.0, 0.0, 0.0, 0.15),  # 빨강, 연하게
    ) -> np.ndarray:
        """
        sky_viewer 오버레이용 RGBA 배열 (npix, 4).
        observed    → covered_color
        unobserved  → uncovered_color
        """
        npix   = self._hp.npix
        colors = np.tile(uncovered_color, (npix, 1)).astype(np.float32)
        for pix in self._obs_pix:
            colors[pix] = covered_color
        return colors


# ── 전역 싱글턴 ────────────────────────────────────────────

_moc_manager: Optional[MocManager] = None

def get_moc_manager(nside: int = 32) -> MocManager:
    global _moc_manager
    if _moc_manager is None or _moc_manager._nside != nside:
        _moc_manager = MocManager(nside=nside)
    return _moc_manager
