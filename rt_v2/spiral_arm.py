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

from astro_processing import (
    HI_FREQ_HZ, icrs_to_galactic, R_SUN_KPC, V_CIRC_KMS,
)

# ── 은하 모델 상수: R₀=8.15 kpc, Θ₀=236 km/s (Reid+2019, astro_processing 에서 정의)
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

    sqrt_d = np.sqrt(disc)
    d1 = R_sun * np.cos(l) - sqrt_d
    d2 = R_sun * np.cos(l) + sqrt_d

    # 물리적인 해는 d > 0 뿐이다.
    #   · 내부 은하(R<R₀) + 1·4사분면  → 두 해 모두 양수 → 근/원거리 모호성
    #   · 외부 은하(R>R₀)              → d2 하나만 양수 → 유일해
    #   · 내부 은하인데 2·3사분면(cos l<0) → 두 해 모두 음수 → '금지 속도', 거리 없음
    sols = [d for d in (d1, d2) if d > 1e-3]
    if not sols:
        return dict(d_near_kpc=np.nan, d_far_kpc=np.nan, R_kpc=float(R),
                    in_inner=bool(in_inner), valid=False, ambiguous=False)
    ambiguous = len(sols) == 2 and (d2 - d1) > 0.05
    d_near, d_far = (d1, d2) if ambiguous else (sols[-1], sols[-1])

    # 위 해는 은하면 투영 거리 → 시선 거리로 환산 (경사 보정)
    d_near /= abs(cos_b) if abs(cos_b) > 0.1 else 1.0
    d_far  /= abs(cos_b) if abs(cos_b) > 0.1 else 1.0

    return dict(d_near_kpc=float(d_near), d_far_kpc=float(d_far),
                R_kpc=float(R), in_inner=bool(in_inner), valid=True,
                ambiguous=bool(ambiguous))


def distance_to_xy(d_kpc: float, l_deg: float, b_deg: float = 0.0) -> tuple:
    """
    시선 거리 + 은하 경도(+위도) → 조감도 XY 좌표 [kpc].
    원점 = 태양 위치.  +Y: 태양→은하 중심,  +X: 은하 회전 방향(l=90°).
    시선 거리를 은하면에 투영(d·cos b)해서 찍는다.
    """
    l = np.radians(l_deg)
    d = d_kpc * np.cos(np.radians(b_deg))
    x = d * np.sin(l)     # 은하 회전 방향 (시계 반대)
    y = d * np.cos(l)     # 태양→은하 중심 방향
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
        xn, yn = distance_to_xy(dist['d_near_kpc'], l_deg, b_deg)
        xf, yf = distance_to_xy(dist['d_far_kpc'],  l_deg, b_deg)

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
        """로그 나선 (후행팔 trailing): r = r0 * exp(-tan(pitch) * (θ - θ0)).

        θ 는 '회전 방향(반시계)으로 증가하는 은하중심 방위각'.
        우리 은하 나선팔은 후행팔이므로, 회전 방향(θ 증가)으로 갈수록 반경이
        '감소'해야 한다. 지수 부호를 +로 두면 선행팔(leading)이 되어 실제와
        반대로 감긴다 (Hou & Han 2014).
        """
        pitch = np.radians(pitch_deg)
        theta = np.linspace(np.radians(l_start), np.radians(l_end), n)
        r     = r0 * np.exp(-np.tan(pitch) * (theta - theta[0]))
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
# 5. 데이터 기반 나선팔 추론  (관측 점 → 로그 나선, 허프 변환)
# ═══════════════════════════════════════════════════════════
#
# 아이디어
#   후행 로그 나선  r = r₀·exp(−k(θ−θ₀)),  k = tan ψ (피치각)
#   로그를 취하면  ln r + k·θ = 상수.  이 값을 '나선 위상' ξ 라 하면
#   같은 팔 위의 점은 (ψ 만 맞으면) 모두 같은 ξ 를 갖는다.
#   → 각 점이 (ψ, ξ) 평면에 '투표'하면 팔 하나가 봉우리 하나로 모인다.
#     직선을 찾는 허프 변환을 로그 나선에 적용한 것.
#
# 절차 (순차 허프 / RANSAC 방식)
#   1) 각 HI 피크 → 운동학적 거리 후보(근/원) → 은하중심 극좌표 (r, θ)
#      모호한 점은 두 후보가 0.5표씩 나눠 투표한다.
#   2) 투표 수(가우스 가중)가 가장 큰 (ψ, ξ) 를 고르고, 허용 폭 τ 안의
#      점들로 최소제곱 재맞춤(ln r = ξ − kθ) → 팔 하나 확정
#   3) 그 점들을 빼고 2) 반복. 점이 부족하거나 θ 로 충분히 길게
#      이어지지 않으면(덩어리) 멈춘다.  → 팔 개수·팔별 피치각이 저절로 결정.
#
# θ 규약: 은하중심에서 본 방위각, 0 = 태양 방향, 은하 회전 방향(+X)으로 증가
#         x = r·sinθ,  y = R₀ − r·cosθ   (get_reference_spiral_arms 와 동일)


def galactocentric_polar(x, y, R0: float = R_SUN_KPC):
    """조감도 XY(태양 원점) → 은하중심 극좌표 (r [kpc], θ [rad])."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    return np.hypot(x, R0 - y), np.arctan2(x, R0 - y)


def spiral_xy(xi: float, pitch_deg: float, theta_min: float, theta_max: float,
              n: int = 160, R0: float = R_SUN_KPC):
    """나선 위상 ξ, 피치각 ψ 의 후행 로그 나선을 θ 구간에서 샘플링 → (x, y)."""
    k = np.tan(np.radians(pitch_deg))
    th = np.linspace(theta_min, theta_max, n)
    r = np.exp(xi - k * th)
    return r * np.sin(th), R0 - r * np.cos(th)


def peak_candidates(l_deg: float, b_deg: float, v_lsr_kms: float,
                    R0: float = R_SUN_KPC) -> dict:
    """HI 피크 하나 → 운동학적 거리 후보들 (조감도 XY + 은하중심 극좌표)."""
    dist = velocity_to_distance(v_lsr_kms, l_deg, b_deg)
    out = dict(valid=bool(dist['valid']), ambiguous=bool(dist.get('ambiguous', False)),
               in_inner=bool(dist['in_inner']), R_kpc=dist['R_kpc'], cands=[])
    if not dist['valid']:
        return out
    kinds = [('near', dist['d_near_kpc']), ('far', dist['d_far_kpc'])] \
        if out['ambiguous'] else [('unique', dist['d_far_kpc'])]
    for kind, d in kinds:
        if not np.isfinite(d) or d <= 0.05:
            continue
        x, y = distance_to_xy(d, l_deg, b_deg)
        r, th = galactocentric_polar(x, y, R0)
        out['cands'].append(dict(kind=kind, d=float(d), x=x, y=y,
                                 r=float(r), th=float(th)))
    if len(out['cands']) < 2:
        out['ambiguous'] = False
    out['valid'] = bool(out['cands'])
    return out


def _hough_votes(lnr, th, w, pitches, xi_edges, sigma):
    """(ψ, ξ) 허프 누적 배열 — 각 후보가 가우스 커널로 투표."""
    xc = 0.5 * (xi_edges[1:] + xi_edges[:-1])
    acc = np.zeros((len(pitches), len(xc)))
    if len(lnr) == 0:
        return acc
    for a, psi in enumerate(pitches):
        xi = lnr + np.tan(np.radians(psi)) * th
        acc[a] = (w[:, None] * np.exp(-0.5 * ((xc[None, :] - xi[:, None]) / sigma) ** 2)).sum(0)
    return acc


def infer_spiral_arms(
    peaks: list[dict],
    *,
    b_max_deg: float = 30.0,
    pitch_range: tuple = (5.0, 25.0),
    pitch_step: float = 0.5,
    tol_lnr: float = 0.08,
    max_arms: int = 6,
    ambiguity: str = 'auto',
    min_points_per_arm: int = 4,
    min_span_deg: float = 20.0,
    max_gap_deg: float = 60.0,
    r_range: tuple = (3.0, 20.0),
    R0: float = R_SUN_KPC,
) -> dict:
    """
    관측된 HI 피크들만으로 나선팔(로그 나선)을 추론한다.

    Parameters
    ----------
    peaks        : [{'l_deg', 'b_deg', 'v_lsr_kms', 'T_b_peak', ...}, ...]
    b_max_deg    : |b| 가 이보다 크면 은하면 투영 거리를 믿을 수 없어 제외
    pitch_range  : 탐색 피치각 범위 [deg]  (우리 은하 팔은 대략 10~14°)
    tol_lnr      : 팔 소속 허용 폭 (ln r 단위, 0.08 ≈ 8 kpc 에서 ±0.65 kpc)
    ambiguity    : 'auto'(두 후보 모두 투표) | 'near' | 'far'
    min_span_deg : 팔로 인정할 최소 방위각 길이 (덩어리 배제)
    max_gap_deg  : 팔 위 이웃한 점 사이 최대 방위각 간격 — 이보다 벌어지면 끊는다
    r_range      : 맞춤에 쓰는 은하중심 반경 범위 [kpc] (막대 영역 제외)

    Returns
    -------
    dict(ok, reason, arms[], points[], hough{}, n_used, ...)
    """
    pts = []
    for idx, p in enumerate(peaks):
        l, b, v = float(p['l_deg']), float(p['b_deg']), float(p['v_lsr_kms'])
        c = peak_candidates(l, b, v, R0)
        cands = c['cands']
        if ambiguity in ('near', 'far') and len(cands) == 2:
            cands = [cands[0] if ambiguity == 'near' else cands[1]]
        reason = ''
        if not c['valid']:
            reason = '거리 해 없음'
        elif abs(b) > b_max_deg:
            reason = f'|b|>{b_max_deg:g}°'
        else:
            cands_in = [q for q in cands if r_range[0] <= q['r'] <= r_range[1]]
            if not cands_in:
                reason = f'R∉[{r_range[0]:g},{r_range[1]:g}] kpc'
        pts.append(dict(id=idx, l=l, b=b, v=v, T=float(p.get('T_b_peak', np.nan)),
                        src=p.get('src', 'obs'), obs=p.get('obs', -1),
                        cands=cands, all_cands=c['cands'], ambiguous=len(cands) == 2,
                        R=c['R_kpc'], excluded=reason, arm=-1, sel=0 if cands else -1))

    used = [p for p in pts if not p['excluded']]
    pitches = np.arange(pitch_range[0], pitch_range[1] + 1e-9, pitch_step)
    sigma = tol_lnr / 2.0

    # 누적 배열 (UI 시각화용, 전체 점 기준)
    flat = [(np.log(q['r']), q['th'], 1.0 / len(p['cands']))
            for p in used for q in p['cands'] if r_range[0] <= q['r'] <= r_range[1]]
    lnr_all = np.array([f[0] for f in flat]); th_all = np.array([f[1] for f in flat])
    w_all = np.array([f[2] for f in flat])
    if len(flat):
        lo = (lnr_all + np.tan(np.radians(pitches.min())) * th_all).min()
        lo = min(lo, (lnr_all + np.tan(np.radians(pitches.max())) * th_all).min())
        hi = (lnr_all + np.tan(np.radians(pitches.min())) * th_all).max()
        hi = max(hi, (lnr_all + np.tan(np.radians(pitches.max())) * th_all).max())
        xi_edges = np.arange(lo - 3 * sigma, hi + 3 * sigma + 0.02, 0.02)
    else:
        xi_edges = np.arange(0.5, 3.5, 0.02)
    acc_all = _hough_votes(lnr_all, th_all, w_all, pitches, xi_edges, sigma)

    result = dict(ok=False, reason='', R0=R0, n_total=len(pts), n_used=len(used),
                  b_max_deg=b_max_deg, ambiguity=ambiguity, tol_lnr=tol_lnr,
                  arms=[], n_arms=0, pitch_deg=None,
                  hough=dict(pitches=pitches.round(3).tolist(),
                             xi=[float(xi_edges[0]), float(xi_edges[-1])],
                             acc=np.round(acc_all / max(acc_all.max(), 1e-9), 3).tolist(),
                             peaks=[]))

    min_needed = 2 * min_points_per_arm
    if len(used) < min_needed:
        result['reason'] = (f'추론에 쓸 수 있는 피크가 {len(used)}개뿐입니다 '
                            f'(최소 {min_needed}개 필요).')
        result['points'] = _export_points(pts)
        return result

    ref = get_reference_spiral_arms()
    remaining = list(used)
    arms = []
    xc = 0.5 * (xi_edges[1:] + xi_edges[:-1])
    rejected = 0
    suppress = np.zeros(acc_all.shape, dtype=bool)   # '팔 아님' 판정된 봉우리 주변
    while len(remaining) >= min_points_per_arm and len(arms) < max_arms and rejected < 8:
        lnr = np.array([np.log(q['r']) for p in remaining for q in p['cands']])
        th = np.array([q['th'] for p in remaining for q in p['cands']])
        w = np.array([1.0 / len(p['cands']) for p in remaining for q in p['cands']])
        acc = _hough_votes(lnr, th, w, pitches, xi_edges, sigma)
        acc[suppress] = 0.0
        if acc.max() <= 0:
            break
        a, j = np.unravel_index(np.argmax(acc), acc.shape)
        psi, xi0 = float(pitches[a]), float(xc[j])

        # 최소제곱 재맞춤 (ln r = ξ − kθ), 소속점 재선정 2회
        for _ in range(3):
            k = np.tan(np.radians(psi))
            members, sel = [], []
            for p in remaining:
                res = [abs(np.log(q['r']) + k * q['th'] - xi0) for q in p['cands']]
                i = int(np.argmin(res))
                if res[i] <= tol_lnr:
                    members.append(p); sel.append(i)
            members, sel = _longest_run(members, sel, np.radians(max_gap_deg))
            if len(members) < 3:
                break
            T = np.array([p['cands'][i]['th'] for p, i in zip(members, sel)])
            L = np.array([np.log(p['cands'][i]['r']) for p, i in zip(members, sel)])
            if np.ptp(T) > np.radians(10):
                slope, icpt = np.polyfit(T, L, 1)              # L = icpt + slope·θ
                k_new = float(np.clip(-slope, np.tan(np.radians(pitch_range[0])),
                                      np.tan(np.radians(pitch_range[1]))))
                psi = float(np.degrees(np.arctan(k_new)))
                xi0 = float(np.mean(L + k_new * T))
            else:
                xi0 = float(np.mean(L + k * T))

        span = float(np.degrees(np.ptp(T))) if len(members) >= 2 else 0.0
        if len(members) < min_points_per_arm or span < min_span_deg:
            # 이 봉우리는 팔이 아님(점 몇 개의 덩어리) → 그 주변을 지우고 다음 봉우리
            rejected += 1
            suppress |= ((np.abs(pitches - pitches[a])[:, None] <= 3.0)
                         & (np.abs(xc - xc[j])[None, :] <= tol_lnr))
            continue

        k = np.tan(np.radians(psi))
        rs = np.array([p['cands'][i]['r'] for p, i in zip(members, sel)])
        rms = float(np.sqrt(np.mean((rs - np.exp(xi0 - k * T)) ** 2)))
        pad = np.radians(15.0)
        t0, t1 = float(T.min() - pad), float(T.max() + pad)
        x, y = spiral_xy(xi0, psi, t0, t1, R0=R0)
        arm_id = len(arms)
        clamped = (abs(psi - pitch_range[0]) < 0.3 or abs(psi - pitch_range[1]) < 0.3)
        arms.append(dict(
            id=arm_id, xi=xi0, pitch_deg=psi, pitch_clamped=bool(clamped),
            theta_min=t0, theta_max=t1,
            n=len(members), span_deg=float(span), rms_kpc=rms,
            r_sun_dir=float(np.exp(xi0)),
            match=_closest_reference_arm(x, y, ref),
            xy=np.column_stack([x, y]).round(4).tolist(),
        ))
        result['hough']['peaks'].append([psi, xi0])
        for p, i in zip(members, sel):
            p['arm'], p['sel'] = arm_id, i
        mem_ids = {id(p) for p in members}
        remaining = [p for p in remaining if id(p) not in mem_ids]

    if not arms:
        result['reason'] = ('점들이 나선 모양으로 이어지지 않습니다 — 관측 방향을 더 넓게, '
                            '더 많이 모아 보세요.')
        result['points'] = _export_points(pts)
        return result

    # 바깥 → 안쪽 순서로 정렬하지 않고, 태양 방향 반경 순(안→밖)으로 id 재부여
    order = np.argsort([arm['r_sun_dir'] for arm in arms])
    remap = {int(old): new for new, old in enumerate(order)}
    arms = [arms[i] for i in order]
    for new, arm in enumerate(arms):
        arm['id'] = new
    for p in pts:
        if p['arm'] >= 0:
            p['arm'] = remap[p['arm']]

    n_in = sum(a['n'] for a in arms)
    result.update(
        ok=True, arms=arms, n_arms=len(arms), n_assigned=n_in,
        pitch_deg=float(np.average([a['pitch_deg'] for a in arms],
                                   weights=[a['n'] for a in arms])),
        points=_export_points(pts, arms),
    )
    return result


def _longest_run(members, sel, max_gap):
    """θ 순으로 늘어놓았을 때 간격이 max_gap 이하로 이어지는 가장 긴 구간만 남긴다."""
    if len(members) < 2:
        return members, sel
    th = np.array([p['cands'][i]['th'] for p, i in zip(members, sel)])
    order = np.argsort(th)
    breaks = np.where(np.diff(th[order]) > max_gap)[0]
    runs = np.split(order, breaks + 1)
    best = max(runs, key=len)
    return [members[i] for i in best], [sel[i] for i in best]


def _closest_reference_arm(x, y, ref: dict, tol_kpc: float = 1.0):
    """맞춘 팔과 가장 가까운 문헌 팔 이름 (최근접 거리 중앙값 < tol 일 때)."""
    best_name, best_d = None, np.inf
    P = np.column_stack([x, y])
    for name, info in ref.items():
        rx, ry = info['xy']
        Q = np.column_stack([rx, ry])
        d = np.sqrt(((P[:, None, :] - Q[None, :, :]) ** 2).sum(-1)).min(axis=1)
        md = float(np.median(d))
        if md < best_d:
            best_name, best_d = name, md
    return dict(name=best_name if best_d < tol_kpc else None, dist_kpc=float(best_d))


def _export_points(pts, arms=None):
    out = []
    for p in pts:
        sel = p.get('sel', -1)
        c = p['cands'][sel] if sel >= 0 and p['cands'] else None
        alt = [q for q in p['all_cands'] if c is None or q['kind'] != c['kind']]
        res_kpc = None
        if c is not None and arms is not None and p['arm'] >= 0:
            arm = arms[p['arm']]
            k = np.tan(np.radians(arm['pitch_deg']))
            res_kpc = float(abs(np.log(c['r']) + k * c['th'] - arm['xi']) * c['r'])
        out.append(dict(
            id=p['id'], obs=p['obs'], src=p['src'],
            l=p['l'], b=p['b'], v=p['v'],
            T=None if not np.isfinite(p['T']) else p['T'],
            R=None if not np.isfinite(p['R']) else float(p['R']),
            x=c['x'] if c else None, y=c['y'] if c else None,
            d=c['d'] if c else None, kind=c['kind'] if c else None,
            alt=[dict(x=q['x'], y=q['y'], d=q['d'], kind=q['kind']) for q in alt],
            ambiguous=len(p['all_cands']) == 2, arm=p['arm'],
            excluded=p['excluded'] or None, residual_kpc=res_kpc,
        ))
    return out


# ═══════════════════════════════════════════════════════════
# 6. 문헌 모델 예측 — 시선 방향별 예상 교차점 / 합성 관측
# ═══════════════════════════════════════════════════════════

def predict_sightline_crossings(l_deg: float, b_deg: float = 0.0,
                                d_max: float = 20.0, R0: float = R_SUN_KPC,
                                v0: float = V_CIRC_KMS) -> list[dict]:
    """
    문헌 나선팔 모델에서, 은하 경도 l 시선이 팔을 가로지르는 지점과
    그곳 가스가 보일 '예상 LSR 속도'(평탄 회전 곡선)를 계산.
    """
    ux, uy = np.sin(np.radians(l_deg)), np.cos(np.radians(l_deg))
    cos_b = np.cos(np.radians(b_deg))
    out = []
    for name, info in get_reference_spiral_arms().items():
        x, y = (np.asarray(a) for a in info['xy'])
        # 선분 P_i→P_{i+1} 과 반직선 t·u (t>0) 의 교점
        px, py = x[:-1], y[:-1]
        qx, qy = x[1:] - px, y[1:] - py
        den = ux * qy - uy * qx
        with np.errstate(divide='ignore', invalid='ignore'):
            t = (px * qy - py * qx) / den
            s = (px * uy - py * ux) / den
        hit = np.isfinite(t) & (t > 0.05) & (t < d_max) & (s >= 0) & (s <= 1)
        for d in np.sort(t[hit]):
            cx, cy = d * ux, d * uy
            R = float(np.hypot(cx, R0 - cy))
            v = v0 * (R0 / R - 1.0) * np.sin(np.radians(l_deg)) * cos_b
            out.append(dict(arm=name, d=float(d), x=float(cx), y=float(cy),
                            R=R, v_lsr_pred=float(v)))
    out.sort(key=lambda c: c['d'])
    return out


def synthetic_arm_peaks(n_dirs: int = 40, v_noise_kms: float = 7.0,
                        b_sigma_deg: float = 2.5, seed: Optional[int] = None,
                        d_max: float = 16.0) -> list[dict]:
    """
    문헌 팔 모델로부터 '가상의 관측 피크'를 만든다 (데모/교육용 합성 데이터).

    무작위 경도 방향의 시선이 팔과 만나는 곳마다 HI 구름을 두고,
    회전 곡선으로 v_LSR 을 계산한 뒤 속도 잡음을 더한다.
    → 이 v_LSR 을 다시 거리로 환산하면 실제처럼 근/원 모호성과
      운동학적 거리 오차가 그대로 재현된다.
    """
    rng = np.random.default_rng(seed)
    out = []
    ls = np.sort(rng.uniform(0, 360, n_dirs))
    for l in ls:
        if min(abs(np.sin(np.radians(l))), 1) < 0.08:      # 중심/반중심 방향은 거리 불능
            continue
        b = float(rng.normal(0, b_sigma_deg))
        for c in predict_sightline_crossings(l, b, d_max=d_max):
            v = c['v_lsr_pred'] + rng.normal(0, v_noise_kms)
            T = float(12 + 55 * np.exp(-c['d'] / 7.0) * rng.uniform(0.5, 1.0))
            out.append(dict(l_deg=float(l), b_deg=b, v_lsr_kms=float(v),
                            T_b_peak=T, src='synthetic', truth_arm=c['arm']))
    return out


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