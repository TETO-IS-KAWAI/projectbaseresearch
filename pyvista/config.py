"""
config.py
앱 전체 설정 관리 모듈

역할
  - 관측 / SDR / 지도 / 경로 관련 설정값을 한 곳에서 관리
  - assets/config.json 에서 불러오고 저장
  - 다른 모듈은 Config.get() 으로 전역 인스턴스에 접근

사용 예
  from config import Config

  cfg = Config.get()
  print(cfg.obs_lat, cfg.center_freq_hz)

  cfg.T_sys = 55.0
  cfg.save()
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ───────────────────────────────────────────────────────────
# 경로
# ───────────────────────────────────────────────────────────

_HERE       = Path(__file__).parent          # radio_telescope/
_ASSETS_DIR = _HERE / 'assets'
_CONFIG_FILE = _ASSETS_DIR / 'config.json'


# ───────────────────────────────────────────────────────────
# Config 데이터클래스
# ───────────────────────────────────────────────────────────

@dataclass
class Config:
    """
    앱 전체 설정.
    모든 필드는 JSON 직렬화 가능한 기본 타입.
    """

    # ── 관측 위치 ──────────────────────────────────────────
    obs_name:      str   = '학교'
    obs_lat:       float = 36.522764    # 위도  [deg]
    obs_lon:       float = 127.248878   # 경도  [deg]
    obs_height_m:  float = 0.0          # 고도  [m]

    # ── SDR 수신 파라미터 ───────────────────────────────────
    center_freq_hz: float = 1_420_405_751.77   # HI 21cm 정지 주파수 [Hz]
    sample_rate:    float = 2_500_000.0         # Airspy 샘플링 레이트 [Hz]
    nfft:           int   = 2048                # FFT 크기

    # ── 복사측정 파라미터 ───────────────────────────────────
    T_sys:   float = 50.0   # 시스템 잡음 온도 [K]  (보정 전 추정치)
    G_sys:   float = 1.0    # 시스템 이득 [선형]    (보정 전 = 1)

    # ── HEALPix 하늘 지도 ───────────────────────────────────
    nside:    int = 32       # HEALPix 해상도  (npix = 12 * nside²)
                             # nside=32  → 12288 픽셀, ~1.8° 해상도
                             # nside=64  → 49152 픽셀, ~0.9° 해상도

    # ── 파일 경로 ────────────────────────────────────────────
    data_dir:   str = ''    # .bin 파일이 있는 폴더  (빈 문자열 = 미설정)
    output_dir: str = ''    # 결과 저장 폴더         (빈 문자열 = 앱 폴더)

    # ── 표시 설정 ────────────────────────────────────────────
    temp_method:   str  = 'median'   # 밝기온도 대푯값 방식: median / mean / peak
    dark_mode:     bool = True       # 다크 테마

    # ── 싱글턴 (런타임 전용, JSON 저장 안 함) ─────────────────
    _instance: Optional[Config] = field(default=None, init=False, repr=False, compare=False)

    # ───────────────────────────────────────────────────────
    # 싱글턴 접근
    # ───────────────────────────────────────────────────────

    _global: Optional[Config] = field(default=None, init=False, repr=False, compare=False)

    @classmethod
    def get(cls) -> Config:
        """전역 인스턴스 반환. 없으면 config.json 에서 로드."""
        if not hasattr(cls, '_singleton') or cls._singleton is None:
            cls._singleton = cls.load()
        return cls._singleton

    @classmethod
    def reset(cls) -> None:
        """싱글턴 초기화 (테스트용)."""
        cls._singleton = None

    # ───────────────────────────────────────────────────────
    # 저장 / 불러오기
    # ───────────────────────────────────────────────────────

    def save(self) -> None:
        """현재 설정을 assets/config.json 에 저장."""
        _ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        data = self._to_json_dict()
        with open(_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls) -> Config:
        """
        assets/config.json 이 있으면 불러오고, 없으면 기본값 반환.
        파일에 없는 키는 기본값으로 채움 (버전 업 시 하위 호환).
        """
        cfg = cls()
        if _CONFIG_FILE.exists():
            try:
                with open(_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                cfg._from_json_dict(data)
            except (json.JSONDecodeError, KeyError):
                pass   # 파일 깨진 경우 기본값 유지
        return cfg

    # ───────────────────────────────────────────────────────
    # 직렬화 헬퍼 (내부용)
    # ───────────────────────────────────────────────────────

    _SKIP_FIELDS = {'_instance', '_global'}   # JSON 저장 제외 필드

    def _to_json_dict(self) -> dict:
        d = {}
        for f in self.__dataclass_fields__:
            if f.startswith('_'):
                continue
            d[f] = getattr(self, f)
        return d

    def _from_json_dict(self, data: dict) -> None:
        for f in self.__dataclass_fields__:
            if f.startswith('_'):
                continue
            if f in data:
                expected_type = type(getattr(self, f))
                try:
                    setattr(self, f, expected_type(data[f]))
                except (TypeError, ValueError):
                    pass   # 타입 불일치 시 기본값 유지

    # ───────────────────────────────────────────────────────
    # 편의 프로퍼티
    # ───────────────────────────────────────────────────────

    @property
    def data_dir_path(self) -> Path:
        """data_dir 문자열을 Path 로 반환. 미설정이면 앱 폴더."""
        return Path(self.data_dir) if self.data_dir else _HERE

    @property
    def output_dir_path(self) -> Path:
        """output_dir 문자열을 Path 로 반환. 미설정이면 앱 폴더."""
        return Path(self.output_dir) if self.output_dir else _HERE

    @property
    def npix(self) -> int:
        """HEALPix 총 픽셀 수 (= 12 * nside²)."""
        return 12 * self.nside ** 2

    @property
    def freq_resolution_hz(self) -> float:
        """FFT 주파수 분해능 [Hz] = sample_rate / nfft."""
        return self.sample_rate / self.nfft

    @property
    def velocity_resolution_kms(self) -> float:
        """주파수 분해능을 속도로 환산 [km/s]."""
        from astropy.constants import c as C
        return float(
            (self.freq_resolution_hz / self.center_freq_hz)
            * C.to('km/s').value
        )

    def __repr__(self) -> str:
        lines = [
            'Config(',
            f'  obs      : {self.obs_name}  ({self.obs_lat:.4f}°N, {self.obs_lon:.4f}°E)',
            f'  freq     : {self.center_freq_hz/1e9:.6f} GHz',
            f'  srate    : {self.sample_rate/1e6:.1f} MHz',
            f'  nfft     : {self.nfft}  →  Δf = {self.freq_resolution_hz:.0f} Hz'
            f'  ({self.velocity_resolution_kms:.2f} km/s)',
            f'  T_sys    : {self.T_sys} K   G_sys : {self.G_sys}',
            f'  nside    : {self.nside}  →  {self.npix} pixels',
            f'  data_dir : {self.data_dir or "(미설정)"}',
            ')',
        ]
        return '\n'.join(lines)


# ───────────────────────────────────────────────────────────
# 셀프 테스트
# ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    import shutil

    print("=" * 50)
    print("Config 모듈 테스트")
    print("=" * 50)

    # 1. 기본값 생성
    Config.reset()
    cfg = Config.get()
    print("\n[1] 기본값 로드")
    print(cfg)

    # 2. 값 변경 후 저장
    cfg.T_sys    = 55.0
    cfg.obs_name = '테스트 관측소'
    cfg.save()
    print("\n[2] 변경 후 저장")
    print(f"  저장 위치: {_CONFIG_FILE}")
    print(f"  T_sys  = {cfg.T_sys}")
    print(f"  obs    = {cfg.obs_name}")

    # 3. 다시 로드해서 확인
    Config.reset()
    cfg2 = Config.get()
    print("\n[3] 재로드 확인")
    print(f"  T_sys  = {cfg2.T_sys}   (기대값: 55.0)")
    print(f"  obs    = {cfg2.obs_name}")

    # 4. 편의 프로퍼티
    print("\n[4] 편의 프로퍼티")
    print(f"  npix               = {cfg2.npix}")
    print(f"  freq_resolution_hz = {cfg2.freq_resolution_hz:.0f} Hz")
    print(f"  velocity_res       = {cfg2.velocity_resolution_kms:.2f} km/s")

    # 5. 테스트 파일 정리
    shutil.rmtree(_ASSETS_DIR, ignore_errors=True)
    Config.reset()
    print("\n완료!")
