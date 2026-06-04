"""
foreground_processing.py
은하 연속체 전경 보정 (healpy / pygdsm 미사용)

1. FITS  : assets/foreground_gsm_1420.fits 등 (astropy + astropy-healpix)
2. 해석식: 은하 위도 |b| 기반 동기전파 근사 (항상 사용 가능)
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import numpy as np
from astropy.io import fits
from astropy_healpix import HEALPix
import astropy.units as u

from old_versions.at_april_second.config import Config, _ASSETS_DIR
from old_versions.at_april_second.astro_processing import HI_FREQ_HZ

# ── FITS 후보 경로 (우선순위) ─────────────────────────────────
FG_FITS_CANDIDATES = (
    _ASSETS_DIR / 'foreground_gsm_1420.fits',
    _ASSETS_DIR / 'gsm_1420.fits',
)

# 해석식 기본값 (1420 MHz 동기전파 근사, 교육용)
_DEFAULT_T0_K      = 2.0    # |b|≈90° 기준 온도 [K]
_DEFAULT_BETA      = 2.7    # |b| 의존 지수
_DEFAULT_B_MIN_DEG = 3.0    # 은하면 특이점 완화 [deg]


def find_foreground_fits() -> Optional[Path]:
    """사용 가능한 전경 FITS 경로. 없으면 None."""
    for p in FG_FITS_CANDIDATES:
        if p.is_file():
            return p
    return None


def _infer_nside(npix: int) -> int:
    return int(np.round(np.sqrt(npix / 12)))


def _read_healpix_fits(path: Path) -> tuple[np.ndarray, int, str, str]:
    """
    HEALPix FITS → (values, nside, ordering, frame).
    frame: 'icrs' | 'galactic'
    """
    with fits.open(path, memmap=False) as hdul:
        for hdu in hdul:
            if hdu.data is None:
                continue

            hdr = hdu.header
            ordering = (hdr.get('ORDERING') or hdr.get('ORDER') or 'RING').upper()
            if ordering not in ('RING', 'NESTED', 'NEST'):
                ordering = 'RING'
            if ordering == 'NEST':
                ordering = 'NESTED'

            coord = (hdr.get('COORDSYS') or hdr.get('COORD') or '').upper()
            frame = 'galactic' if 'GAL' in coord else 'icrs'

            nside_hdr = hdr.get('NSIDE')
            values: Optional[np.ndarray] = None

            if hasattr(hdu.data, 'names') and hdu.data.names:
                names = list(hdu.data.names)
                for col in ('I', 'TEMPERATURE', 'T', 'T_B', 'DATA', 'MAP'):
                    if col in names:
                        values = np.asarray(hdu.data[col], dtype=np.float64).ravel()
                        break
                if values is None:
                    for name in names:
                        arr = np.asarray(hdu.data[name])
                        if np.issubdtype(arr.dtype, np.floating) or np.issubdtype(
                                arr.dtype, np.integer):
                            values = arr.astype(np.float64).ravel()
                            break
            elif isinstance(hdu.data, np.ndarray):
                values = np.asarray(hdu.data, dtype=np.float64).ravel()

            if values is None or values.size == 0:
                continue

            nside = int(nside_hdr) if nside_hdr else _infer_nside(values.size)
            if 12 * nside ** 2 != values.size:
                nside = _infer_nside(values.size)
            return values.astype(np.float32), nside, ordering, frame

    raise ValueError(f'HEALPix 맵을 읽을 수 없습니다: {path}')


def _reproject_healpix(
    values: np.ndarray,
    nside_in: int,
    ordering_in: str,
    frame_in: str,
    nside_out: int,
    frame_out: str = 'icrs',
) -> np.ndarray:
    """입력 HEALPix 맵을 출력 nside/frame 으로 재매핑."""
    order_in = 'nested' if ordering_in.startswith('NEST') else 'ring'
    hp_in  = HEALPix(nside=nside_in, order=order_in, frame=frame_in)
    hp_out = HEALPix(nside=nside_out, order='ring', frame=frame_out)

    if (nside_in, frame_in, order_in) == (nside_out, frame_out, 'ring'):
        return values.astype(np.float32)

    pix_out = np.arange(hp_out.npix)
    coords  = hp_out.healpix_to_skycoord(pix_out)
    if frame_in == 'galactic':
        coords = coords.galactic
    pix_in = hp_in.lonlat_to_healpix(coords.l, coords.b)
    return values[pix_in].astype(np.float32)


def get_analytic_foreground_map(
    nside: int,
    T0_k: Optional[float] = None,
    beta: Optional[float] = None,
    b_min_deg: Optional[float] = None,
) -> np.ndarray:
    """
    은하 위도 |b| 기반 연속체 전경 근사 [K], ICRS RING.

    T(b) = T0 * max(|sin b|, sin(b_min))^(-beta)
    """
    cfg = Config.get()
    T0  = T0_k if T0_k is not None else getattr(cfg, 'fg_T0_k', _DEFAULT_T0_K)
    bta = beta if beta is not None else getattr(cfg, 'fg_beta', _DEFAULT_BETA)
    bmn = np.radians(
        b_min_deg if b_min_deg is not None
        else getattr(cfg, 'fg_b_min_deg', _DEFAULT_B_MIN_DEG)
    )

    hp = HEALPix(nside=nside, order='ring', frame='icrs')
    coords = hp.healpix_to_skycoord(np.arange(hp.npix)).galactic
    sin_b = np.abs(np.sin(coords.b.rad))
    sin_b = np.maximum(sin_b, np.sin(bmn))
    return (T0 * sin_b ** (-bta)).astype(np.float32)


def get_fits_foreground_map(
    nside: int,
    fits_path: Optional[Path] = None,
) -> np.ndarray:
    """FITS HEALPix 전경 맵 → ICRS RING nside."""
    path = fits_path or find_foreground_fits()
    if path is None:
        raise FileNotFoundError(
            '전경 FITS가 없습니다. assets/foreground_gsm_1420.fits 를 추가하거나 '
            'scripts/generate_foreground_fits.py 로 생성하세요.'
        )
    values, nside_in, ordering, frame = _read_healpix_fits(path)
    return _reproject_healpix(values, nside_in, ordering, frame, nside, 'icrs')


def get_foreground_map(
    nside: int,
    prefer: Literal['auto', 'fits', 'analytic'] = 'auto',
) -> tuple[np.ndarray, str]:
    """
    전경 지도 반환.

    Returns
    -------
    fg_map : float32, shape (12*nside²,)
    method : 'fits' | 'analytic'
    """
    if prefer in ('auto', 'fits') and find_foreground_fits() is not None:
        try:
            return get_fits_foreground_map(nside), 'fits'
        except Exception:
            if prefer == 'fits':
                raise

    return get_analytic_foreground_map(nside), 'analytic'


def subtract_foreground(
    sky_map: np.ndarray,
    nside: int,
    scale: Optional[float] = None,
    prefer: Literal['auto', 'fits', 'analytic'] = 'auto',
) -> tuple[np.ndarray, np.ndarray, str]:
    """
    sky_map 에서 전경 차감.

    Returns
    -------
    corrected, fg_map, method
    """
    cfg = Config.get()
    s   = scale if scale is not None else getattr(cfg, 'fg_scale', 1.0)
    fg, method = get_foreground_map(nside, prefer=prefer)
    out = sky_map.copy()
    valid = np.isfinite(sky_map)
    out[valid] = sky_map[valid] - s * fg[valid]
    return out, fg, method
