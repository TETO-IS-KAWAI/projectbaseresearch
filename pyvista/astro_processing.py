"""
astro_processing.py
전파망원경 데이터 처리 모듈

기능
  - .bin 파일 (Airspy IQ float32 인터리브) 읽기
  - 도플러 효과 보정 (지구 자전 / 지구 공전 / 은하 LSR)
  - 레일리-진스 공식으로 밝기온도 환산
  - HEALPix 하늘 지도 생성 및 시각화

의존 라이브러리: numpy, astropy, astropy_healpix, matplotlib

healpy(GPL) 대체 목록
  hp.nside_to_npix(n)       -> HEALPix(nside=n).npix
  hp.ang2pix(n, theta, phi) -> HEALPix.lonlat_to_healpix()
  hp.pix2ang()              -> HEALPix.healpix_to_skycoord()
  hp.UNSEEN                 -> numpy.nan
  hp.mollview()             -> matplotlib Mollweide 직접 구현
  hp.graticule()            -> matplotlib 위선/경선 수동 그리기
"""

import warnings
import numpy as np

from astropy.time import Time
from astropy.coordinates import EarthLocation, SkyCoord
import astropy.units as u
import astropy.constants as const
from astropy_healpix import HEALPix
from astropy.utils import iers

import matplotlib.pyplot as plt

# 오프라인 환경에서 IERS 자동 다운로드 경고 억제
iers.conf.auto_download = False
iers.conf.auto_max_age  = None


# ───────────────────────────────────────────────────────────
# 상수
# ───────────────────────────────────────────────────────────

_C_MS  = const.c.to(u.m / u.s).value    # 299_792_458   m/s
_C_KMS = const.c.to(u.km / u.s).value   # 299_792.458   km/s
_K_B   = const.k_B.value                # 1.381e-23     J/K

HI_FREQ_HZ = 1.42040575177e9            # 21cm 수소선 정지 주파수 [Hz]

UNSEEN = np.nan                         # healpy.UNSEEN 대체


# ───────────────────────────────────────────────────────────
# 1. IQ 데이터 읽기
# ───────────────────────────────────────────────────────────

def load_iq_bin(filepath: str) -> np.ndarray:
    """
    Airspy SDR# .bin 파일 → complex64 배열 반환.
    포맷: float32 인터리브 [I0, Q0, I1, Q1, ...]
    """
    raw = np.fromfile(filepath, dtype=np.float32)
    if raw.size % 2 != 0:
        raw = raw[:-1]
    return (raw[0::2] + 1j * raw[1::2]).astype(np.complex64)


# ───────────────────────────────────────────────────────────
# 2. FFT 평균 파워 스펙트럼
# ───────────────────────────────────────────────────────────

def compute_power_spectrum(
    iq: np.ndarray,
    sample_rate: float,
    nfft: int = 2048,
) -> tuple:
    """
    FFT 후 시간 평균 파워 스펙트럼 계산.

    반환
    ----
    freqs : 주파수 오프셋 배열 [Hz]  (중심 = 0)
    power : 선형 파워 |FFT|²
    """
    n_chunks = len(iq) // nfft
    if n_chunks == 0:
        raise ValueError(
            f"IQ 길이({len(iq)})가 nfft({nfft})보다 짧습니다."
        )
    iq_chunks = iq[: n_chunks * nfft].reshape(n_chunks, nfft)
    window    = np.blackman(nfft)
    fft_out   = np.fft.fftshift(
        np.fft.fft(iq_chunks * window, axis=1), axes=1
    )
    power = np.mean(np.abs(fft_out) ** 2, axis=0)
    freqs = np.fft.fftshift(np.fft.fftfreq(nfft, d=1.0 / sample_rate))
    return freqs, power


# ───────────────────────────────────────────────────────────
# 3. 도플러 보정
# ───────────────────────────────────────────────────────────

_LSR_V_KMS  = 20.0    # 태양의 LSR 대비 속도 [km/s]  (IAU 1985)
_LSR_RA_DEG = 270.0   # LSR 기준 태양 운동 방향 (apex) RA  [deg]
_LSR_DE_DEG =  30.0   # LSR 기준 태양 운동 방향 (apex) Dec [deg]


def radial_velocity_correction(
    ra_deg: float,
    dec_deg: float,
    obs_time: str,
    obs_lat: float,
    obs_lon: float,
    obs_height_m: float = 0.0,
) -> float:
    """
    관측 방향에 대한 LSR 도플러 속도 보정값 [km/s] 반환.

    지구 자전 + 지구 공전 + 태양-LSR 상대운동 모두 포함.

    반환 부호 convention (doppler_correct_freqs 와 일치):
      양수 = 관측자가 천체에서 멀어지는 방향 (적색편이)
      f_rest = f_obs * (1 + v/c) 에 그대로 대입하면 됨.

    구현 방식:
      1) astropy heliocentric 보정 (지구 자전 + 지구 공전)
         → astropy는 '관측자가 천체 쪽으로 이동 = 양수'이므로 부호 반전
      2) LSR 보정: 태양이 apex 방향으로 20 km/s 이동하므로
         target 방향으로의 성분을 빼줌
    """
    coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame='icrs')
    loc   = EarthLocation(
        lat=obs_lat * u.deg,
        lon=obs_lon * u.deg,
        height=obs_height_m * u.m,
    )
    t = Time(obs_time, format='isot', scale='utc')

    # 지구 자전 + 공전 보정 (astropy 부호: 접근 = 양수 → 우리 convention과 반대)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        vcorr_helio = coord.radial_velocity_correction(
            kind='heliocentric', obstime=t, location=loc,
        ).to(u.km / u.s).value

    # LSR 보정: 태양이 apex 쪽으로 _LSR_V_KMS km/s 이동
    apex_uv = np.array([
        np.cos(np.radians(_LSR_DE_DEG)) * np.cos(np.radians(_LSR_RA_DEG)),
        np.cos(np.radians(_LSR_DE_DEG)) * np.sin(np.radians(_LSR_RA_DEG)),
        np.sin(np.radians(_LSR_DE_DEG)),
    ])
    target_uv = np.array([
        np.cos(np.radians(dec_deg)) * np.cos(np.radians(ra_deg)),
        np.cos(np.radians(dec_deg)) * np.sin(np.radians(ra_deg)),
        np.sin(np.radians(dec_deg)),
    ])
    v_lsr = _LSR_V_KMS * float(np.dot(apex_uv, target_uv))

    # 최종: 부호 반전 후 LSR 성분 추가
    # (astropy 접근=양수 → 우리 멀어짐=양수로 반전, LSR도 동일 부호)
    return -(vcorr_helio + v_lsr)


def doppler_correct_freqs(
    freqs_offset: np.ndarray,
    center_freq_hz: float,
    v_radial_kms: float,
) -> np.ndarray:
    """
    주파수 오프셋 배열을 도플러 보정된 절대 주파수로 변환.
    f_rest = f_obs * (1 + v/c)   [v > 0 → 적색편이]
    """
    beta  = v_radial_kms / _C_KMS
    f_abs = center_freq_hz + freqs_offset
    return f_abs * (1.0 + beta)


# ───────────────────────────────────────────────────────────
# 4. 레일리-진스 밝기온도 환산
# ───────────────────────────────────────────────────────────

def fft_gain_factor(nfft: int) -> float:
    """Blackman 윈도우 FFT의 파워 스케일 보정 인수."""
    window = np.blackman(nfft)
    return float(nfft * np.mean(window ** 2))


def rayleigh_jeans_temperature(
    power_spectral_density: np.ndarray,
    freq_hz: np.ndarray,
    G_sys: float = 1.0,
    nfft: int = 2048,
) -> np.ndarray:
    """
    레일리-진스 역산으로 각 채널의 밝기온도 계산.
    T_b(ν) = P(ν) / (G_fft · G_sys) · c² / (2 · ν² · k_B)

    1.42 GHz는 플랑크 극대(~160 GHz)보다 훨씬 낮아
    레일리-진스 근사 오차 0.01% 미만으로 매우 정확.
    """
    G_fft = fft_gain_factor(nfft)
    P_cal = power_spectral_density / (G_fft * G_sys)
    return P_cal * _C_MS ** 2 / (2.0 * freq_hz ** 2 * _K_B)


def representative_brightness_temp(
    T_b_spectrum: np.ndarray,
    method: str = 'median',
) -> float:
    """
    스펙트럼에서 대푯값 추출.

    method
    ------
    'median' : 아웃라이어에 강건 (기본값)
    'mean'   : SNR이 높을 때 유리
    'peak'   : 가장 밝은 채널 (수소선 피크 추출 시)
    """
    finite = T_b_spectrum[np.isfinite(T_b_spectrum) & (T_b_spectrum > 0)]
    if len(finite) == 0:
        return float('nan')
    if method == 'median':
        return float(np.median(finite))
    elif method == 'mean':
        return float(np.mean(finite))
    elif method == 'peak':
        return float(np.max(finite))
    else:
        raise ValueError(
            f"method는 'median', 'mean', 'peak' 중 하나여야 합니다. (입력: {method!r})"
        )


# ───────────────────────────────────────────────────────────
# 5. 더미 IQ 생성 (실 데이터 없을 때 테스트용)
# ───────────────────────────────────────────────────────────

def _hi_temperature_model(ra_deg: float, dec_deg: float) -> float:
    """
    HI 21cm 밝기온도 근사 모델 [K].
    은하 중심면 방향(RA=266.4°, Dec=-28.9°) 근처에서 가장 밝음.
    """
    ra_r  = np.radians(ra_deg)
    dec_r = np.radians(dec_deg)
    l_r   = np.radians(266.4)
    b_r   = np.radians(-28.9)
    cos_angle = (
        np.cos(dec_r) * np.cos(b_r) * np.cos(ra_r - l_r)
        + np.sin(dec_r) * np.sin(b_r)
    )
    T_galactic = 20.0 * np.exp(0.5 * (cos_angle - 0.3))
    return max(float(T_galactic), 2.0)


def generate_dummy_iq(
    ra_deg: float,
    dec_deg: float,
    center_freq_hz: float = HI_FREQ_HZ,
    sample_rate: float = 2.5e6,
    n_samples: int = 262144,
    T_sys: float = 50.0,
    G_sys: float = 1.0,
    seed: int = None,
) -> np.ndarray:
    """
    HI 관측 시뮬레이션용 더미 IQ 데이터 생성.
    bin_filepath=None 이면 process_observation 에서 자동 호출됨.
    """
    rng    = np.random.default_rng(seed)
    T_sky  = _hi_temperature_model(ra_deg, dec_deg)
    T_obs  = T_sky + T_sys
    nu     = center_freq_hz
    P_mean = G_sys * 2.0 * nu ** 2 * _K_B * T_obs / _C_MS ** 2
    sigma  = np.sqrt(max(P_mean, 1e-30) / 2.0)
    I = rng.normal(0, sigma, n_samples).astype(np.float32)
    Q = rng.normal(0, sigma, n_samples).astype(np.float32)
    return (I + 1j * Q).astype(np.complex64)


# ───────────────────────────────────────────────────────────
# 6. 전체 파이프라인: 관측 1포인트 처리
# ───────────────────────────────────────────────────────────

def process_observation(
    ra_deg: float,
    dec_deg: float,
    obs_time: str,
    obs_lat: float,
    obs_lon: float,
    bin_filepath: str = None,
    center_freq_hz: float = HI_FREQ_HZ,
    sample_rate: float = 2.5e6,
    nfft: int = 2048,
    obs_height_m: float = 0.0,
    T_sys: float = 50.0,
    G_sys: float = 1.0,
    temp_method: str = 'median',
    seed: int = None,
) -> dict:
    """
    관측 1포인트 처리:
    IQ 읽기(또는 생성) → FFT → 도플러 보정 → T_b 환산 → 대푯값

    bin_filepath=None 이면 더미 IQ 자동 생성.

    반환 dict 키
    ------------
    ra, dec           : 관측 방향 [deg]
    v_radial_kms      : LSR 보정 속도 [km/s]
    T_brightness      : 하늘 밝기온도 (T_sys 제거 후) [K]
    T_b_raw           : T_sys 포함 밝기온도 [K]
    success           : 유효한 결과 여부
    freqs_corrected   : 도플러 보정된 절대 주파수 배열 [Hz]
    freq_offsets      : 보정 전 주파수 오프셋 배열 [Hz]
    T_b_spectrum      : 밝기온도 스펙트럼 배열 [K]
    power             : FFT 파워 배열 (전체 채널)
    """
    # IQ 읽기 or 더미 생성
    if bin_filepath is not None:
        iq = load_iq_bin(bin_filepath)
    else:
        iq = generate_dummy_iq(
            ra_deg, dec_deg,
            center_freq_hz=center_freq_hz,
            sample_rate=sample_rate,
            T_sys=T_sys, G_sys=G_sys,
            seed=seed,
        )

    # FFT
    freq_offsets, power = compute_power_spectrum(iq, sample_rate, nfft)

    # 도플러 보정
    v_kms           = radial_velocity_correction(
        ra_deg, dec_deg, obs_time,
        obs_lat, obs_lon, obs_height_m,
    )
    freqs_corrected = doppler_correct_freqs(freq_offsets, center_freq_hz, v_kms)

    # 양수 주파수만 사용해 T_b 환산
    mask         = freqs_corrected > 0
    T_b_spectrum = rayleigh_jeans_temperature(
        power[mask], freqs_corrected[mask],
        G_sys=G_sys, nfft=nfft,
    )

    T_b_raw = representative_brightness_temp(T_b_spectrum, method=temp_method)
    T_sky   = T_b_raw - T_sys

    return {
        'ra':              ra_deg,
        'dec':             dec_deg,
        'v_radial_kms':    v_kms,
        'T_brightness':    T_sky,
        'T_b_raw':         T_b_raw,
        'success':         np.isfinite(T_sky),
        'freqs_corrected': freqs_corrected,
        'freq_offsets':    freq_offsets,
        'T_b_spectrum':    T_b_spectrum,
        'power':           power,
    }


# ───────────────────────────────────────────────────────────
# 7. HEALPix 하늘 지도
# ───────────────────────────────────────────────────────────

def build_sky_map(
    observations: list,
    nside: int = 32,
) -> tuple:
    """
    관측 결과 리스트 → HEALPix 밝기온도 지도.
    같은 픽셀에 여러 관측이 있으면 hit-map 가중 평균.

    반환
    ----
    sky_map : 밝기온도 지도 [K],  빈 픽셀 = NaN
    hit_map : 픽셀별 관측 횟수
    """
    ahp     = HEALPix(nside=nside, order='ring', frame='icrs')
    npix    = ahp.npix
    sky_sum = np.zeros(npix)
    hit_map = np.zeros(npix, dtype=int)

    for obs in observations:
        if not obs['success']:
            continue
        pix = int(ahp.lonlat_to_healpix(
            obs['ra']  * u.deg,
            obs['dec'] * u.deg,
        ))
        sky_sum[pix] += obs['T_brightness']
        hit_map[pix] += 1

    sky_map         = np.full(npix, UNSEEN)
    filled          = hit_map > 0
    sky_map[filled] = sky_sum[filled] / hit_map[filled]
    return sky_map, hit_map


def update_sky_map(
    sky_map: np.ndarray,
    hit_map: np.ndarray,
    new_obs: dict,
    nside: int,
) -> tuple:
    """
    기존 sky_map에 새 관측 1개를 추가하여 갱신.
    실시간 관측 루프에서 사용.

    반환
    ----
    sky_map, hit_map : 갱신된 배열 (in-place 수정 후 반환)
    """
    if not new_obs['success']:
        return sky_map, hit_map

    ahp = HEALPix(nside=nside, order='ring', frame='icrs')
    pix = int(ahp.lonlat_to_healpix(
        new_obs['ra']  * u.deg,
        new_obs['dec'] * u.deg,
    ))
    prev_sum      = sky_map[pix] * hit_map[pix] if np.isfinite(sky_map[pix]) else 0.0
    hit_map[pix] += 1
    sky_map[pix]  = (prev_sum + new_obs['T_brightness']) / hit_map[pix]
    return sky_map, hit_map


def get_pixel_coords(nside: int) -> tuple:
    """
    모든 HEALPix 픽셀의 중심 좌표 반환.

    반환
    ----
    ra_deg, dec_deg : float 배열
    """
    ahp    = HEALPix(nside=nside, order='ring', frame='icrs')
    coords = ahp.healpix_to_skycoord(np.arange(ahp.npix))
    return coords.ra.deg, coords.dec.deg


# ───────────────────────────────────────────────────────────
# 8. 시각화  (healpy.mollview / graticule 대체)
# ───────────────────────────────────────────────────────────

def _healpix_to_mollweide_image(
    sky_map: np.ndarray,
    nside: int,
    img_width: int = 800,
    img_height: int = 400,
) -> np.ndarray:
    """
    HEALPix 지도를 Mollweide 투영 이미지(float 배열)로 변환.
    빈 영역 = NaN.
    """
    ahp = HEALPix(nside=nside, order='ring', frame='icrs')

    xs = np.linspace(-2 * np.sqrt(2),  2 * np.sqrt(2), img_width)
    ys = np.linspace( np.sqrt(2),     -np.sqrt(2),      img_height)
    xg, yg = np.meshgrid(xs, ys)

    # Mollweide 역투영: 화면 좌표 → (ra, dec)
    arg     = np.clip(yg / np.sqrt(2), -1.0, 1.0)
    theta_m = np.arcsin(arg)
    dec_rad = np.arcsin(
        np.clip((2 * theta_m + np.sin(2 * theta_m)) / np.pi, -1.0, 1.0)
    )
    cos_tm = np.cos(theta_m)
    ra_rad = np.full_like(xg, np.nan)
    valid  = cos_tm > 1e-10
    ra_rad[valid] = np.pi - (np.pi * xg[valid]) / (
        2 * np.sqrt(2) * cos_tm[valid]
    )

    # 타원 바깥 마스킹
    outside          = (xg ** 2 / 8 + yg ** 2 / 2) > 1.0
    ra_rad[outside]  = np.nan
    dec_rad[outside] = np.nan

    # 이미지 픽셀 → HEALPix 픽셀 → 값  (ra/dec 둘 다 유효한 픽셀만)
    img      = np.full((img_height, img_width), np.nan)
    valid_px = np.isfinite(ra_rad) & np.isfinite(dec_rad)
    if valid_px.any():
        pix_flat      = ahp.lonlat_to_healpix(
            ra_rad[valid_px]  * u.rad,
            dec_rad[valid_px] * u.rad,
        )
        vals          = sky_map[pix_flat]
        img[valid_px] = np.where(np.isfinite(vals), vals, np.nan)
    return img


def plot_sky_map(
    sky_map: np.ndarray,
    nside: int = None,
    title: str = "HI 21cm 하늘 밝기온도 지도",
    save_path: str = None,
    ax=None,
):
    """
    HEALPix 지도를 Mollweide 투영으로 시각화.
    ax 를 넘기면 기존 Axes에 그림 (GUI 임베드용).

    반환
    ----
    pcm : pcolormesh 객체 (colorbar 연결용)
    """
    if nside is None:
        nside = int(np.round(np.sqrt(len(sky_map) / 12)))

    img         = _healpix_to_mollweide_image(sky_map, nside)
    finite_vals = sky_map[np.isfinite(sky_map)]
    vmin = float(np.percentile(finite_vals,  2)) if len(finite_vals) else -1
    vmax = float(np.percentile(finite_vals, 98)) if len(finite_vals) else  1

    standalone = ax is None
    if standalone:
        fig = plt.figure(figsize=(12, 6))
        ax  = fig.add_subplot(111, projection='mollweide')

    img_h, img_w = img.shape
    xg, yg = np.meshgrid(
        np.linspace(-np.pi, np.pi, img_w),
        np.linspace(np.pi / 2, -np.pi / 2, img_h),
    )
    pcm = ax.pcolormesh(
        xg, yg, img,
        cmap='RdYlBu_r', vmin=vmin, vmax=vmax,
        shading='auto', rasterized=True,
    )

    # 위선/경선
    gc = (0.5, 0.5, 0.5, 0.4)
    for dec_line in range(-60, 61, 30):
        dr   = np.radians(dec_line)
        ra_r = np.linspace(-np.pi, np.pi, 500)
        ax.plot(ra_r, np.full_like(ra_r, dr), '-', color=gc, lw=0.7)
        ax.text(0, dr + np.radians(3), f'{dec_line:+d}°',
                ha='center', va='bottom', fontsize=7, color='gray')
    for ra_off in range(-150, 151, 60):
        if abs(ra_off) == 180:
            continue
        rr   = np.radians(ra_off)
        dr   = np.linspace(-np.pi / 2, np.pi / 2, 200)
        ax.plot(np.full_like(dr, rr), dr, '-', color=gc, lw=0.7)

    plt.colorbar(pcm, ax=ax, label='밝기온도 [K]', fraction=0.03, pad=0.04)
    ax.set_title(title, fontsize=13, pad=12)

    if standalone:
        plt.tight_layout()
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"  저장 완료: {save_path}")
        plt.show()
        plt.close()

    return pcm


def plot_spectrum_sample(result: dict, save_path: str = None):
    """
    단일 관측의 보정된 스펙트럼과 밝기온도를 시각화.
    """
    fig, axes = plt.subplots(2, 1, figsize=(10, 7))

    mask     = result['freqs_corrected'] > 0
    freqs_gh = result['freqs_corrected'][mask] / 1e9

    # 파워 스펙트럼
    ax = axes[0]
    ax.plot(
        freqs_gh,
        10 * np.log10(result['power'][mask] + 1e-30),
        color='steelblue', lw=0.9,
    )
    ax.axvline(
        HI_FREQ_HZ / 1e9, color='red', ls='--', lw=0.8,
        label=f'HI 중심 ({HI_FREQ_HZ / 1e9:.5f} GHz)',
    )
    ax.set_xlabel('주파수 [GHz]')
    ax.set_ylabel('파워 [dB]')
    ax.set_title(
        f'도플러 보정 후 파워 스펙트럼'
        f'  (v_LSR = {result["v_radial_kms"]:+.2f} km/s)'
    )
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # 밝기온도 스펙트럼
    ax2 = axes[1]
    ax2.plot(freqs_gh, result['T_b_spectrum'], color='tomato', lw=0.8)
    ax2.axhline(
        result['T_b_raw'], color='navy', ls='--',
        label=f"T_b_raw = {result['T_b_raw']:.2f} K",
    )
    ax2.axhline(
        result['T_brightness'], color='green', ls='--',
        label=f"T_sky   = {result['T_brightness']:.4f} K",
    )
    ax2.set_xlabel('주파수 [GHz]')
    ax2.set_ylabel('밝기온도 [K]')
    ax2.set_title('레일리-진스 밝기온도 스펙트럼')
    ax2.legend()
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  저장 완료: {save_path}")
    plt.show()
    plt.close()


# ───────────────────────────────────────────────────────────
# 셀프 테스트
# ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    import matplotlib
    matplotlib.use('Agg')   # 디스플레이 없는 환경에서도 동작

    print("=" * 60)
    print("HI 21cm 밝기온도 파이프라인 테스트")
    print("=" * 60)

    OBS_TIME = '2026-05-01T12:00:00'
    OBS_LAT  = 36.522764   # 학교 위도
    OBS_LON  = 127.248878  # 학교 경도
    T_SYS    = 50.0

    # 1. 도플러 보정
    print("\n[1] 도플러 LSR 보정 테스트")
    for name, ra, dec in [
        ("은하 중심",    266.4, -28.9),
        ("은하 반중심",   86.4,  28.9),
        ("은하 북극",    192.9,  27.1),
    ]:
        v = radial_velocity_correction(ra, dec, OBS_TIME, OBS_LAT, OBS_LON)
        print(f"  {name:10s} (RA={ra:5.1f}, Dec={dec:+5.1f}): {v:+8.3f} km/s")

    # 2. 단일 포인트 처리
    print("\n[2] 단일 관측 포인트 처리")
    result = process_observation(
        ra_deg=266.4, dec_deg=-28.9,
        obs_time=OBS_TIME,
        obs_lat=OBS_LAT, obs_lon=OBS_LON,
        T_sys=T_SYS, seed=42,
    )
    print(f"  T_b_raw   : {result['T_b_raw']:.4f} K")
    print(f"  T_sky     : {result['T_brightness']:.4f} K")
    print(f"  v_radial  : {result['v_radial_kms']:+.3f} km/s")
    print(f"  성공 여부 : {result['success']}")

    # 3. 스펙트럼 시각화
    print("\n[3] 스펙트럼 저장")
    plot_spectrum_sample(result, save_path='test_spectrum.png')

    # 4. HEALPix 지도 생성
    print("\n[4] HEALPix 하늘 지도 생성 (nside=8, 빠른 테스트)")
    nside           = 8
    ra_all, dec_all = get_pixel_coords(nside)
    print(f"  총 {len(ra_all)}개 픽셀 처리 중...", flush=True)

    observations = []
    for i, (ra, dec) in enumerate(zip(ra_all, dec_all)):
        obs = process_observation(
            ra_deg=float(ra), dec_deg=float(dec),
            obs_time=OBS_TIME,
            obs_lat=OBS_LAT, obs_lon=OBS_LON,
            T_sys=T_SYS, seed=i,
        )
        observations.append(obs)

    sky_map, hit_map = build_sky_map(observations, nside=nside)
    filled = sky_map[np.isfinite(sky_map)]
    print(f"  관측된 픽셀 : {(hit_map > 0).sum()} / {len(sky_map)}")
    print(f"  T_sky 평균  : {filled.mean():.2f} K")
    print(f"  T_sky 범위  : {filled.min():.2f} ~ {filled.max():.2f} K")

    plot_sky_map(sky_map, nside=nside, save_path='test_sky_map.png')
    print("\n완료!")
