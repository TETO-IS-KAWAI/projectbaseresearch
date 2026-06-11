"""
spiral_arm.py
나선팔 구조 분석 모듈

역할
  1. T_b 스펙트럼에서 속도 피크 감지
  2. 각 피크의 LSR 속도 → 운동학적 거리 환산 (은하 회전 모델)
  3. 거리 + 은하 경도 → 은하 XY 좌표 (조감도용)
  4. 문헌 나선팔 참조 좌표 제공 (오버레이용)

과학 배경
  - HI 21cm 스펙트럼의 각 피크 = 시선 방향의 HI 가스 구름
  - LSR 속도 v = v_circ(R)·sin(l) - v_circ(R☉)·sin(l)  [은하면 b≈0°]
  - 이를 역산해 R(은하 중심 거리) → 시선 거리 d 계산
  - 여러 방향의 d를 모으면 나선팔 구조가 드러남
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.signal import find_peaks, peak_prominences

from astro_processing import HI_FREQ_HZ, icrs_to_galactic

# ── 은하 모델 상수 (IAU 권고 + Brand & Blitz 1993)
R_SUN_KPC   = 8.5     # 태양~은하 중심 거리 [kpc]
V_CIRC_KMS  = 220.0   # 은하 원형 속도 [km/s]
C_KMS       = 299792.458


# ═══════════════════════════════════════════════════════════
# 데이터 클래스
# ═══════════════════════════════════════════════════════════

@dataclass
class VelocityPeak:
    """스펙트럼에서 감지된 속도 피크 하나."""
    v_lsr_kms:    float          # 피크의 LSR 속도 [km/s]
    T_b_peak:     float          # 피크 밝기온도 [K]
    freq_hz:      float          # 피크 주파수 [Hz]
    l_deg:        float          # 은하 경도 [deg]
    b_deg:        float          # 은하 위도 [deg]
    d_near_kpc:   float = np.nan # 근거리 운동학적 거리 [kpc]
    d_far_kpc:    float = np.nan # 원거리 운동학적 거리 [kpc]
    x_near_kpc:   float = np.nan # 근거리 은하 XY [kpc]  (X: 은하 중심 방향)
    y_near_kpc:   float = np.nan
    x_far_kpc:    float = np.nan
    y_far_kpc:    float = np.nan
    in_inner_galaxy: bool = False


@dataclass
class SpiralArmResult:
    """한 관측 포인트의 나선팔 분석 결과."""
    ra_deg:   float
    dec_deg:  float
    l_deg:    float
    b_deg:    float
    obs_time: str
    peaks:    list[VelocityPeak] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════
# 1. 속도 피크 감지
# ═══════════════════════════════════════════════════════════

def freq_to_vlsr(freq_hz: np.ndarray, freq_center: float = HI_FREQ_HZ) -> np.ndarray:
    """
    주파수 배열 → LSR 속도 배열 [km/s].
    v = c * (f0 - f) / f0  (적색편이 양수 = 멀어짐)
    """
    return C_KMS * (freq_center - freq_hz) / freq_center


def detect_peaks(
    T_b_spectrum: np.ndarray,
    freqs_corrected: np.ndarray,
    noise_sigma: float = 4.0,
    min_height_K: float = 3.0,
    min_distance_bins: int = 10,
    min_width_bins: int = 3,
    noise_v_kms: float = 150.0,
    smooth_bins: int = 5,
    max_peaks: int = 10,
) -> list[dict]:
    """
    T_b 스펙트럼에서 유의미한 HI 속도 피크 감지 (MAD 기반 robust 잡음 추정).

    Parameters
    ----------
    noise_sigma       : 잡음 σ 기준 임계값 배수 (기본 3σ)
    min_height_K      : 절대 최소 높이 하한 [K]
    min_distance_bins : 피크 간 최소 채널 수
    min_width_bins    : 최소 피크 폭 [채널 수]  — 단일 채널 잡음 스파이크 제거
    noise_v_kms       : (현재 미사용, 호환성 유지) 오프라인 영역 하한 [km/s]
    smooth_bins       : 사전 평활화 창 크기 [채널 수] (0이면 생략)
    max_peaks         : 반환할 최대 피크 수 (T_b 높은 순)
    """
    from scipy.ndimage import uniform_filter1d

    v_arr    = freq_to_vlsr(freqs_corrected)
    in_range = np.abs(v_arr) < 250
    if not np.any(in_range):
        return []

    T_use = T_b_spectrum[in_range]
    f_use = freqs_corrected[in_range]
    v_use = v_arr[in_range]

    # NaN → 중앙값으로 채움
    finite_mask = np.isfinite(T_use)
    T_med   = float(np.nanmedian(T_use)) if finite_mask.any() else 0.0
    T_clean = np.where(finite_mask, T_use, T_med)

    # ── Robust 잡음 추정: MAD (Median Absolute Deviation)
    # 피크나 기저선 왜곡에 영향받지 않는 전체-스펙트럼 robust σ 추정
    # σ_robust = MAD / 0.6745  (정규분포 가정 시 σ에 대한 불편 추정량)
    median_T   = float(np.median(T_clean))
    mad        = float(np.median(np.abs(T_clean - median_T)))
    noise_std  = mad / 0.6745 if mad > 0 else float(np.std(T_clean))

    # 실효 임계값: 중앙값 기준 N·σ 위
    threshold = max(min_height_K, median_T + noise_sigma * noise_std)
    prom_min  = max(min_height_K * 0.5, noise_sigma * noise_std)

    # ── 피크 탐색: 원본 T_clean 기준 (평활화 없음)
    # width 조건이 단일-채널 스파이크를 충분히 걸러냄
    peak_idx, _ = find_peaks(
        T_clean,
        height=threshold,
        distance=min_distance_bins,
        width=min_width_bins,
    )
    if len(peak_idx) == 0:
        return []

    proms, _, _ = peak_prominences(T_clean, peak_idx)
    valid    = proms >= prom_min
    peak_idx = peak_idx[valid]
    if len(peak_idx) == 0:
        return []

    # T_b 내림차순 정렬 후 상위 max_peaks 개만 반환
    results = sorted(
        [{'v_lsr_kms': float(v_use[i]),
          'T_b_peak':  float(T_clean[i]),
          'freq_hz':   float(f_use[i])}
         for i in peak_idx],
        key=lambda x: x['T_b_peak'], reverse=True,
    )
    return results[:max_peaks]


# ═══════════════════════════════════════════════════════════
# 2. 운동학적 거리 환산
# ═══════════════════════════════════════════════════════════

def velocity_to_distance(
    v_lsr_kms: float,
    l_deg: float,
    b_deg: float,
    R_sun: float = R_SUN_KPC,
    v_circ: float = V_CIRC_KMS,
) -> dict:
    """
    LSR 속도 → 운동학적 거리 (평판 은하 회전 모델).

    은하면(b≈0°) 가정. |b| > 10°이면 정확도 저하.

    Returns
    -------
    dict: d_near_kpc, d_far_kpc, R_kpc, in_inner, valid
    """
    l = np.radians(l_deg)
    b = np.radians(b_deg)
    sin_l = np.sin(l)
    cos_b = np.cos(b)

    # |b| > 60°: 은하면에서 너무 벗어나 운동학적 거리 모델 적용 불가
    if abs(cos_b) < 0.5:
        return dict(d_near_kpc=np.nan, d_far_kpc=np.nan,
                    R_kpc=np.nan, in_inner=False, valid=False)

    # l ≈ 0° 또는 180° (은하 중심/반중심 방향):
    # sin(l) ≈ 0 → v_lsr ≈ 0 이어야 정상. v≠0이면 비원형 운동이므로 거리 계산 불가.
    # 단, |v_lsr| < 20 km/s 이면 태양 근방 팔(local arm)으로 간주해 d = |v|/κ 로 추정.
    if abs(sin_l) < 0.05:
        if abs(v_lsr_kms) < 20.0:
            # 시선 방향 속도 기울기(Oort A 상수 ≈ 15 km/s/kpc) 로 거리 추정
            A_oort = 15.0
            d_local = abs(v_lsr_kms) / (2 * A_oort * abs(sin_l) + 1e-6)
            d_local = min(d_local, 3.0)   # 3 kpc 상한
            return dict(d_near_kpc=float(d_local), d_far_kpc=float(d_local),
                        R_kpc=float(R_sun), in_inner=True, valid=True)
        return dict(d_near_kpc=np.nan, d_far_kpc=np.nan,
                    R_kpc=np.nan, in_inner=False, valid=False)

    # v_lsr = v_circ*(R_sun/R - 1)*sin(l)*cos(b) → R 역산
    denom = v_circ * sin_l * cos_b
    ratio = v_lsr_kms / denom + 1.0

    if ratio <= 0:
        return dict(d_near_kpc=np.nan, d_far_kpc=np.nan,
                    R_kpc=np.nan, in_inner=False, valid=False)

    R = R_sun / ratio
    in_inner = R < R_sun

    # 시선 거리 계산 (구면삼각형)
    disc = R_sun**2 * np.cos(l)**2 + R**2 - R_sun**2
    if disc < 0:
        return dict(d_near_kpc=np.nan, d_far_kpc=np.nan,
                    R_kpc=float(R), in_inner=in_inner, valid=False)

    sqrt_d   = np.sqrt(disc)
    d_near   = max(R_sun * np.cos(l) - sqrt_d, 0.0)
    d_far    = R_sun * np.cos(l) + sqrt_d

    # 은하면 보정 (경사 보정)
    d_near /= abs(cos_b) if abs(cos_b) > 0.1 else 1.0
    d_far  /= abs(cos_b) if abs(cos_b) > 0.1 else 1.0

    return dict(d_near_kpc=float(d_near), d_far_kpc=float(d_far),
                R_kpc=float(R), in_inner=bool(in_inner), valid=True)


def distance_to_xy(d_kpc: float, l_deg: float) -> tuple:
    """
    시선 거리 + 은하 경도 → 조감도 XY 좌표 [kpc].
    원점 = 태양 위치.
    X축: 태양→은하 중심 방향.
    """
    l = np.radians(l_deg)
    x = d_kpc * np.sin(l)     # 은하 회전 방향 (시계 반대)
    y = d_kpc * np.cos(l)     # 태양→은하 중심 방향
    return float(x), float(y)


# ═══════════════════════════════════════════════════════════
# 3. 전체 분석 파이프라인
# ═══════════════════════════════════════════════════════════

def analyze_observation(result: dict) -> SpiralArmResult:
    """
    process_observation() 결과 dict → SpiralArmResult.
    스펙트럼 피크 감지 + 거리 환산 + XY 좌표 계산.
    """
    ra  = result['ra']
    dec = result['dec']
    l_deg, b_deg = icrs_to_galactic(ra, dec)

    arm_result = SpiralArmResult(
        ra_deg=ra, dec_deg=dec,
        l_deg=l_deg, b_deg=b_deg,
        obs_time=result.get('obs_time', ''),
    )

    # freqs_corrected, T_b_spectrum 없으면 스킵
    if 'freqs_corrected' not in result or 'T_b_spectrum' not in result:
        return arm_result

    mask        = result['freqs_corrected'] > 0
    T_b_spec    = result['T_b_spectrum']
    freqs_corr  = result['freqs_corrected'][mask]

    raw_peaks = detect_peaks(T_b_spec, freqs_corr)

    for p in raw_peaks:
        dist = velocity_to_distance(p['v_lsr_kms'], l_deg, b_deg)
        xn, yn = distance_to_xy(dist['d_near_kpc'], l_deg)
        xf, yf = distance_to_xy(dist['d_far_kpc'],  l_deg)

        arm_result.peaks.append(VelocityPeak(
            v_lsr_kms   = p['v_lsr_kms'],
            T_b_peak    = p['T_b_peak'],
            freq_hz     = p['freq_hz'],
            l_deg       = l_deg,
            b_deg       = b_deg,
            d_near_kpc  = dist['d_near_kpc'],
            d_far_kpc   = dist['d_far_kpc'],
            x_near_kpc  = xn,
            y_near_kpc  = yn,
            x_far_kpc   = xf,
            y_far_kpc   = yf,
            in_inner_galaxy = dist['in_inner'],
        ))

    return arm_result


# ═══════════════════════════════════════════════════════════
# 4. 문헌 나선팔 참조 데이터 (오버레이용)
# ═══════════════════════════════════════════════════════════

def get_reference_spiral_arms() -> dict:
    """
    문헌 나선팔 참조 좌표 (조감도, 태양 원점).
    출처: Hou & Han 2014 (로그 나선 모델).
    단위: kpc.

    반환: {팔 이름: {'x': array, 'y': array, 'color': str}}
    """
    def log_spiral(r0, pitch_deg, l_start, l_end, n=200):
        """로그 나선: r = r0 * exp(tan(pitch) * (θ - θ0))"""
        pitch = np.radians(pitch_deg)
        theta = np.linspace(np.radians(l_start), np.radians(l_end), n)
        r     = r0 * np.exp(np.tan(pitch) * (theta - theta[0]))
        # 조감도 XY (태양 원점, Y=은하 중심 방향)
        x = r * np.sin(theta)
        y = R_SUN_KPC - r * np.cos(theta)
        return x, y

    arms = {
        'Norma':          {'xy': log_spiral(3.1, 11.5,  20, 340), 'color': '#ff4444'},
        'Scutum-Crux':    {'xy': log_spiral(4.2, 11.5,  20, 310), 'color': '#ff8800'},
        'Sagittarius':    {'xy': log_spiral(5.6, 11.5,  10, 300), 'color': '#ffcc00'},
        'Orion (Local)':  {'xy': log_spiral(8.0,  7.5, -20, 100), 'color': '#00cc44'},
        'Perseus':        {'xy': log_spiral(9.9, 11.5,  -5, 290), 'color': '#4488ff'},
        'Outer':          {'xy': log_spiral(13.0, 11.5, -5, 260), 'color': '#aa44ff'},
    }
    return arms


# ═══════════════════════════════════════════════════════════
# 셀프 테스트
# ═══════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    sys.path.insert(0, '.')
    from astro_processing import process_observation
    from config import Config

    cfg = Config.get()
    print("=== 나선팔 분석 테스트 ===")

    # 은하 중심 방향 (l≈0°)
    result = process_observation(
        ra_deg=266.4, dec_deg=-28.9,
        obs_time='2026-05-01T12:00:00',
        obs_lat=cfg.obs_lat, obs_lon=cfg.obs_lon,
        T_sys=50.0, seed=42,
    )
    arm = analyze_observation(result)
    print(f"l={arm.l_deg:.1f}°  b={arm.b_deg:.1f}°  피크={len(arm.peaks)}개")
    for p in arm.peaks[:3]:
        print(f"  v={p.v_lsr_kms:+.1f} km/s  T={p.T_b_peak:.1f} K  "
              f"d_near={p.d_near_kpc:.2f} kpc  XY=({p.x_near_kpc:.2f},{p.y_near_kpc:.2f})")

    print("\n참조 나선팔:")
    for name in get_reference_spiral_arms():
        print(f"  {name}")