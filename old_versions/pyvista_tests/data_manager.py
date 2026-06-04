"""
data_manager.py
파일 입출력 + 프로젝트 관리 모듈
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from astropy.io import fits

from old_versions.pyvista_tests.config import Config
from old_versions.pyvista_tests.astro_processing import build_sky_map, update_sky_map


class ProjectManager:
    """
    관측 프로젝트 (.json) 생성 / 열기 / 저장 / 관측 추가.

    프로젝트 파일 구조
    ------------------
    {
      "meta": { nside, obs_lat, obs_lon, T_sys, G_sys, center_freq_hz, ... },
      "observations": [
        { ra, dec, obs_time, bin_file, T_brightness, T_b_raw,
          v_radial_kms, success },
        ...
      ]
    }

    sky_map 은 observations 에서 즉시 재구성 (FFT 재실행 없음).
    """

    def __init__(self):
        self._path: Optional[Path]          = None
        self._meta: dict                    = {}
        self._observations: list            = []
        self._sky_map: Optional[np.ndarray] = None
        self._hit_map: Optional[np.ndarray] = None
        self._nside: int                    = 32

    # ── 프로젝트 생성 / 열기 / 저장 ─────────────────────────

    def create(self, path, name: str = '새 프로젝트') -> None:
        cfg = Config.get()
        self._path  = Path(path)
        self._nside = cfg.nside
        self._meta  = {
            'name':           name,
            'created':        datetime.now().isoformat(),
            'nside':          cfg.nside,
            'obs_lat':        cfg.obs_lat,
            'obs_lon':        cfg.obs_lon,
            'obs_height_m':   cfg.obs_height_m,
            'T_sys':          cfg.T_sys,
            'G_sys':          cfg.G_sys,
            'center_freq_hz': cfg.center_freq_hz,
            'sample_rate':    cfg.sample_rate,
            'nfft':           cfg.nfft,
        }
        self._observations = []
        npix = 12 * self._nside ** 2
        self._sky_map = np.full(npix, np.nan, dtype=np.float32)
        self._hit_map = np.zeros(npix, dtype=np.int32)
        self.save()

    def open(self, path) -> None:
        self._path = Path(path)
        with open(self._path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self._meta         = data.get('meta', {})
        self._observations = data.get('observations', [])
        self._nside        = int(self._meta.get('nside', 32))
        self._rebuild_sky_map()

    def save(self) -> None:
        if self._path is None:
            raise RuntimeError('create() 또는 open() 을 먼저 호출하세요.')
        with open(self._path, 'w', encoding='utf-8') as f:
            json.dump(
                {'meta': self._meta, 'observations': self._observations},
                f, indent=2, ensure_ascii=False,
            )

    # ── 관측 추가 ────────────────────────────────────────────

    def add_observation(self, result: dict, bin_filepath: str = '') -> None:
        """
        process_observation() 결과를 프로젝트에 추가하고 저장.
        sky_map / hit_map 즉시 갱신.
        무거운 재계산(FFT) 없이 HEALPix 픽셀 매핑만 수행.
        """
        if not result.get('success', False):
            return

        self._observations.append({
            'ra':           result['ra'],
            'dec':          result['dec'],
            'obs_time':     result.get('obs_time', ''),
            'bin_file':     str(Path(bin_filepath).name) if bin_filepath else '',
            'T_brightness': float(result['T_brightness']),
            'T_b_raw':      float(result['T_b_raw']),
            'v_radial_kms': float(result['v_radial_kms']),
            'success':      True,
        })

        if self._sky_map is None:
            npix = 12 * self._nside ** 2
            self._sky_map = np.full(npix, np.nan, dtype=np.float32)
            self._hit_map = np.zeros(npix, dtype=np.int32)

        self._sky_map, self._hit_map = update_sky_map(
            self._sky_map, self._hit_map, result, self._nside,
        )
        self.save()

    # ── 프로퍼티 ─────────────────────────────────────────────

    @property
    def sky_map(self) -> Optional[np.ndarray]:
        return self._sky_map

    @property
    def hit_map(self) -> Optional[np.ndarray]:
        return self._hit_map

    @property
    def nside(self) -> int:
        return self._nside

    @property
    def meta(self) -> dict:
        return self._meta

    @property
    def observations(self) -> list:
        return self._observations

    @property
    def is_open(self) -> bool:
        return self._path is not None

    @property
    def name(self) -> str:
        return self._meta.get('name', '(프로젝트 없음)')

    @property
    def obs_count(self) -> int:
        return len(self._observations)

    @property
    def path(self) -> Optional[Path]:
        return self._path

    # ── FITS 내보내기 ─────────────────────────────────────────

    def export_fits(self, out_path) -> Path:
        out_path = Path(out_path)
        primary  = fits.PrimaryHDU()
        primary.header['NSIDE']  = self._nside
        primary.header['DATE']   = datetime.now().isoformat()
        primary.header['ORIGIN'] = 'radio_telescope'
        for k, v in self._meta.items():
            if isinstance(v, (int, float)):
                primary.header[k.upper()[:8]] = v
            elif isinstance(v, str) and v.isascii() and len(v) < 68:
                primary.header[k.upper()[:8]] = v
        fits.HDUList([
            primary,
            fits.ImageHDU(data=self._sky_map, name='SKY_MAP'),
            fits.ImageHDU(data=self._hit_map, name='HIT_MAP'),
        ]).writeto(out_path, overwrite=True)
        return out_path

    # ── 내부 ─────────────────────────────────────────────────

    def _rebuild_sky_map(self) -> None:
        sky_map, hit_map = build_sky_map(self._observations, nside=self._nside)
        self._sky_map = sky_map.astype(np.float32)
        self._hit_map = hit_map.astype(np.int32)


# ── 전역 싱글턴 ───────────────────────────────────────────────

_project = ProjectManager()

def get_project() -> ProjectManager:
    return _project


# ── 셀프 테스트 ───────────────────────────────────────────────

if __name__ == '__main__':
    import tempfile, shutil

    tmp = Path(tempfile.mkdtemp())
    pm  = ProjectManager()
    pm.create(tmp / 'test.json', name='테스트')
    print(f'[1] 생성  nside={pm.nside}')

    for ra, dec, T in [(266.4, -28.9, 28.6), (86.4, 28.9, 5.2), (192.9, 27.1, 12.1)]:
        pm.add_observation(
            {'ra': ra, 'dec': dec, 'T_brightness': T, 'T_b_raw': T + 50,
             'v_radial_kms': -10.0, 'success': True},
        )
    print(f'[2] 관측 추가  obs={pm.obs_count}  유효픽셀={np.isfinite(pm.sky_map).sum()}')

    pm2 = ProjectManager()
    pm2.open(tmp / 'test.json')
    print(f'[3] 재오픈  obs={pm2.obs_count}  유효픽셀={np.isfinite(pm2.sky_map).sum()}')

    pm2.export_fits(tmp / 'out.fits')
    print('[4] FITS 내보내기 완료')

    shutil.rmtree(tmp)
    print('완료!')
