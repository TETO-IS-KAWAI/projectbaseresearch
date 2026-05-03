#주의!! 이 코드 에러 있음 일단 저장용으로 올려둠

"""
astro_processing.py
(CMB 하늘 밝기온도 2D 버전)

전파망원경 데이터 처리 모듈 내용
  - bin 파일(Airspy IQ float32 인터리브) 읽기
  - 도플러 효과 보정 (지구 자전 / 지구 공전 / 은하 LSR)
  - 레일리-진스 공식으로 밝기온도 직접 환산
  - HEALPix 하늘 지도 생성 및 시각화
  - healpy 대체해야 함
  - 그리고 파일 경로 수정하기

numpy, scipy, astropy, astropy_healpix, matplotlib

healpy(GPL) 제거사항
  healpy 함수              -> 대체
  hp.nside_to_npix(n)      -> HEALPix(nside=n).npix
  hp.ang2pix(n, theta, phi)-> HEALPix.lonlat_to_healpix()
  hp.UNSEEN                -> numpy.nan
  hp.mollview()            -> matplotlib Mollweide 직접 구현
  hp.graticule()           -> matplotlib 위선/경선 수동 그리기
  hp.pix2ang()             -> HEALPix.healpix_to_skycoord()

수정한 내용
  - fit_planck_and_peak 제거
    1.42 GHz(레일리-진스 영역)에서 플랑크 극대(160 GHz)까지
    113배 떨어져 있어 2.8 MHz 대역 내 곡선 변화율 0.39% 미만.
    curve_fit이 T를 노이즈 수준에서 구분하지 못해 ~50% 오차 발생한다고
  - 대체 사항: 레일리-진스 역산하기  T_b = P_cal * c^2 / (2 * nu^2 * k)
"""

import numpy as np
from scipy.signal import find_peaks

from astropy.time import Time
from astropy.coordinates import (
    EarthLocation,
    solar_system_ephemeris,
    get_body_barycentric_posvel,
)
import astropy.units as u
import astropy.constants as const
from astropy_healpix import HEALPix

import matplotlib.pyplot as plt


# 상수

_C_MS   = const.c.to(u.m / u.s).value        # 299792458 m/s
_C_KMS  = const.c.to(u.km / u.s).value       # 299792.458 km/s
_H      = const.h.value                       # 6.626e-34 J·s
_K_B    = const.k_B.value                     # 1.381e-23 J/K

# LSR 기준값 — IAU 1985라고 한다는데 이거 업데이트 해야 하나 찾아보는 걸로 나중에
_V_LSR_KMS   = 20.0
_LSR_RA_DEG  = 270.0
_LSR_DEC_DEG = 30.0

# HEALPix 빈 픽셀 표시값 (healpy.UNSEEN 대체 사항)
UNSEEN = np.nan


# BIN 파일 읽기 Airspy SDR float32
def load_iq_bin(filepath: str) -> np.ndarray:
    """
    Airspy SDR# .bin 파일 -> complex64 배열 반환.
    포맷: float32 인터리브 [I0, Q0, I1, Q1, ...]
    """
    raw = np.fromfile(filepath, dtype=np.float32)
    if raw.size % 2 != 0:
        raw = raw[:-1]
    return (raw[0::2] + 1j * raw[1::2]).astype(np.complex64)

# FFT로 평균 파워 스펙트럼
def compute_power_spectrum(
    iq: np.ndarray,
    sample_rate: float,
    nfft: int = 2048,
) -> tuple:
    """
    FFT 후 시간 평균 파워 스펙트럼 계산

    return은 아래와 같음
    freqs_offset : 주파수 오프셋 배열 [Hz]  (중심 = 0)
    power        : 선형 파워 |FFT|^2  (정규화 전)
    """
    n_chunks = len(iq) // nfft
    if n_chunks == 0:
        raise ValueError(f"IQ 길이({len(iq)})가 nfft({nfft})보다 짧습니다.")

    iq_chunks = iq[: n_chunks * nfft].reshape(n_chunks, nfft)
    window    = np.blackman(nfft)
    fft_out   = np.fft.fftshift(np.fft.fft(iq_chunks * window, axis=1), axes=1)
    power     = np.mean(np.abs(fft_out) ** 2, axis=0)
    freqs     = np.fft.fftshift(np.fft.fftfreq(nfft, d=1.0 / sample_rate))
    return freqs, power


# 여기서 도플러 보정
def radial_velocity_correction(
    ra_deg: float,
    dec_deg: float,
    obs_time: str,
    obs_lat: float,
    obs_lon: float,
    obs_height_m: float = 0.0,
    include_rotation: bool = True,
    include_orbit: bool = True,
    include_lsr: bool = True,
) -> float:
    """
    관측 방향에 대한 총 시선 도플러 속도 [km/s] 반환
    양수는 관측자가 천체에서 멀어지는 방향 (적색편이)
    """
    target_uv = np.array([
        np.cos(np.radians(dec_deg)) * np.cos(np.radians(ra_deg)),
        np.cos(np.radians(dec_deg)) * np.sin(np.radians(ra_deg)),
        np.sin(np.radians(dec_deg)),
    ])

    t   = Time(obs_time, format='isot', scale='utc')
    loc = EarthLocation(lat=obs_lat * u.deg, lon=obs_lon * u.deg,
                        height=obs_height_m * u.m)
    v_total = 0.0

    if include_rotation:
        gcrs_vel = loc.get_gcrs_posvel(t)[1]
        v_total += float(np.dot(gcrs_vel.xyz.to(u.km / u.s).value, target_uv))

    if include_orbit:
        with solar_system_ephemeris.set('builtin'):
            _, earth_vel = get_body_barycentric_posvel('earth', t)
        v_total += float(np.dot(earth_vel.xyz.to(u.km / u.s).value, target_uv))

    if include_lsr:
        lsr_dir = np.array([
            np.cos(np.radians(_LSR_DEC_DEG)) * np.cos(np.radians(_LSR_RA_DEG)),
            np.cos(np.radians(_LSR_DEC_DEG)) * np.sin(np.radians(_LSR_RA_DEG)),
            np.sin(np.radians(_LSR_DEC_DEG)),
        ])
        v_total += _V_LSR_KMS * float(np.dot(lsr_dir, target_uv))

    return v_total


def doppler_correct_freqs(
    freqs_offset: np.ndarray,
    center_freq_hz: float,
    v_radial_kms: float,
) -> np.ndarray:
    """
    주파수 오프셋 배열을 도플러 보정된 절대 주파수로 변환
    f_rest = f_obs * (1 + v/c)   [v > 0 -> 적색편이]
    """
    beta  = v_radial_kms / _C_KMS
    f_abs = center_freq_hz + freqs_offset
    return f_abs * (1.0 + beta)


# 여기서 레일리 진스인데 아직 제대로 이해 못함
def fft_gain_factor(nfft: int) -> float:
    """
    Blackman 윈도우 FFT의 파워 스케일 보정 인수.
    G_fft = nfft * mean(blackman^2)
    """
    window = np.blackman(nfft)
    return float(nfft * np.mean(window ** 2))


def rayleigh_jeans_temperature(
    power_spectral_density: np.ndarray,
    freq_hz: np.ndarray,
    G_sys: float = 1.0,
    nfft: int = 2048,
) -> np.ndarray:
    """
    레일리-진스 역산으로 각 주파수 채널의 밝기온도 계산
    T_b(nu) = P(nu) / (G_fft * G_sys) * c^2 / (2 * nu^2 * k)
    """
    G_fft = fft_gain_factor(nfft)
    P_cal = power_spectral_density / (G_fft * G_sys)
    T_b   = P_cal * _C_MS**2 / (2.0 * freq_hz**2 * _K_B)
    return T_b


def representative_brightness_temp(
    T_b_spectrum: np.ndarray,
    method: str = 'median',
) -> float:
    """
    스펙트럼에서 대푯값 하나를 추출
    method : 'median' (기본, 아웃라이어 강건)
             'mean'   (SNR 높을 때)
             'peak'   (가장 밝은 채널)
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
        raise ValueError(f"method는 'median', 'mean', 'peak' 중 하나여야 합니다.")


# 일단 테스트용 더미 만들자
def _cmb_temperature_model(ra_deg: float, dec_deg: float) -> float:
    """
    하늘 위치에 따른 CMB 관측 온도 모델 (K)
    쌍극자 이방성 + 은하 전경 방출 포함
    """
    T_cmb     = 2.725
    ra_r      = np.radians(ra_deg)
    dec_r     = np.radians(dec_deg)
    dip_ra    = np.radians(168.0)
    dip_dec   = np.radians(-7.0)
    cos_angle = (np.cos(dec_r) * np.cos(dip_dec) * np.cos(ra_r - dip_ra)
                 + np.sin(dec_r) * np.sin(dip_dec))
    T_dipole     = 3.36e-3 * cos_angle
    T_foreground = 0.5 * np.exp(-0.5 * (dec_deg / 15.0) ** 2)
    return T_cmb + T_dipole + T_foreground


def generate_dummy_iq(
    ra_deg: float,
    dec_deg: float,
    center_freq_hz: float = 1.42040575e9,
    sample_rate: float = 2.5e6,
    n_samples: int = 262144,
    T_sys: float = 50.0,
    G_sys: float = 1.0,
    seed: int = None,
) -> np.ndarray:
    """
    CMB 관측 시뮬레이션 더미 IQ 데이터 생성
    bin_filepath=None 일 때 process_observation에서 자동 호출됨!!
    """
    rng    = np.random.default_rng(seed)
    T_sky  = _cmb_temperature_model(ra_deg, dec_deg)
    T_obs  = T_sky + T_sys
    nu     = center_freq_hz
    P_mean = G_sys * 2.0 * nu**2 * _K_B * T_obs / _C_MS**2
    sigma  = np.sqrt(P_mean / 2.0)
    I = rng.normal(0, sigma, n_samples).astype(np.float32)
    Q = rng.normal(0, sigma, n_samples).astype(np.float32)
    return (I + 1j * Q).astype(np.complex64)



# 전체 파이프라인  bin 1개 -> 밝기온도 대푯값 1개
def process_observation(
    ra_deg: float,
    dec_deg: float,
    obs_time: str,
    obs_lat: float,
    obs_lon: float,
    bin_filepath: str = None,
    center_freq_hz: float = 1.42040575e9,
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
      IQ 읽기(또는 생성) to FFT to 도플러 보정 to T_b 환산 to 대푯값

    bin_filepath=None 이면 더미 IQ를 자동 생성하기
    """
    if bin_filepath is not None:
        iq = load_iq_bin(bin_filepath)
    else:
        iq = generate_dummy_iq(
            ra_deg, dec_deg,
            center_freq_hz=center_freq_hz,
            sample_rate=sample_rate,
            T_sys=T_sys,
            G_sys=G_sys,
            seed=seed,
        )

    freq_offsets, power = compute_power_spectrum(iq, sample_rate, nfft)

    v_kms = radial_velocity_correction(
        ra_deg, dec_deg, obs_time,
        obs_lat, obs_lon, obs_height_m,
    )

    freqs_corrected = doppler_correct_freqs(freq_offsets, center_freq_hz, v_kms)

    mask = freqs_corrected > 0
    T_b_spectrum = rayleigh_jeans_temperature(
        power[mask], freqs_corrected[mask], G_sys=G_sys, nfft=nfft
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
        'T_b_spectrum':    T_b_spectrum,
    }


# ═══════════════════════════════════════════════════════════
# 7. HEALPix 하늘 지도 생성
#    healpy.UNSEEN  -> numpy.nan
#    healpy.ang2pix -> HEALPix.lonlat_to_healpix  (astropy_healpix)
#    healpy.pix2ang -> HEALPix.healpix_to_skycoord (astropy_healpix)
# ═══════════════════════════════════════════════════════════

def build_sky_map(
    observations: list,
    nside: int = 32,
) -> tuple:
    """
    관측 결과 리스트 to HEALPix 하늘 밝기온도 지도
    같은 픽셀에 여러 관측이 있으면 평균(hit-map 가중)

    return 내용
    sky_map : 밝기온도 지도 [K],  빈 픽셀 = NaN  (healpy.UNSEEN 대체)
    hit_map : 픽셀별 관측 횟수
    """
    # HEALPix 객체 (healpy.nside2npix 대체 사항)
    ahp     = HEALPix(nside=nside, order='ring', frame='icrs')
    npix    = ahp.npix
    sky_sum = np.zeros(npix)
    hit_map = np.zeros(npix, dtype=int)

    for obs in observations:
        if not obs['success']:
            continue

        # lonlat_to_healpix: 경도(ra), 위도(dec) — 단위 필요?
        # healpy.ang2pix(nside, theta, phi) 대체?
        #   healpy theta = 공위각 = pi/2 - dec??
        #   astropy_healpix는 위도(latitude) 직접 입력
        pix = int(ahp.lonlat_to_healpix(
            obs['ra']  * u.deg,
            obs['dec'] * u.deg,
        ))

        sky_sum[pix] += obs['T_brightness']
        hit_map[pix] += 1

    # 빈 픽셀 = NaN  (healpy.UNSEEN=-1.6375e30 대체 사항)
    sky_map        = np.full(npix, UNSEEN)
    filled         = hit_map > 0
    sky_map[filled] = sky_sum[filled] / hit_map[filled]

    return sky_map, hit_map


def get_pixel_coords(nside: int) -> tuple:
    """
    모든 HEALPix 픽셀의 중심 (ra_deg, dec_deg) 배열 반환.

    healpy.pix2ang 대체:
      healpy  : theta(공위각), phi(경도) 반환
      여기서는: ra_deg, dec_deg 직접 반환
    """
    ahp    = HEALPix(nside=nside, order='ring', frame='icrs')
    pixels = np.arange(ahp.npix)
    coords  = ahp.healpix_to_skycoord(pixels)
    return coords.ra.deg, coords.dec.deg


# 시각화  (healpy.mollview / healpy.graticule 대체 사항)
# healpy.mollview to matplotlib Mollweide 투영 직접 구현
# healpy.graticule to matplotlib 위선이랑 경선 수동 그리기
def _healpix_to_mollweide_image(
    sky_map: np.ndarray,
    nside: int,
    img_width: int = 800,
    img_height: int = 400,
) -> np.ndarray:
    """
    HEALPix 지도를 Mollweide 투영 이미지로 변환.
    healpy.mollview의 픽셀 투영을 순수 numpy + astropy_healpix로 구현.

    Returns
    -------
    img : (img_height, img_width) float 배열, 빈 영역 = NaN
    """
    ahp = HEALPix(nside=nside, order='ring', frame='icrs')

    # Mollweide 역투영: 화면 좌표 to (ra, dec)
    xs = np.linspace(-2 * np.sqrt(2), 2 * np.sqrt(2), img_width)
    ys = np.linspace( np.sqrt(2), -np.sqrt(2), img_height)
    xg, yg = np.meshgrid(xs, ys)

    arg     = np.clip(yg / np.sqrt(2), -1.0, 1.0)
    theta_m = np.arcsin(arg)
    dec_rad = np.arcsin(
        np.clip((2 * theta_m + np.sin(2 * theta_m)) / np.pi, -1.0, 1.0)
    )

    cos_tm = np.cos(theta_m)
    valid  = cos_tm > 1e-10
    ra_rad = np.full_like(xg, np.nan)
    ra_rad[valid] = np.pi - (np.pi * xg[valid]) / (2 * np.sqrt(2) * cos_tm[valid])

    # 타원 바깥 마스킹한다는데 제대로 되지 않은 것 같음
    outside = (xg**2 / 8 + yg**2 / 2) > 1.0
    ra_rad[outside]  = np.nan
    dec_rad[outside] = np.nan

    # 이미지 픽셀 to HEALPix 픽셀 to 값
    img      = np.full((img_height, img_width), np.nan)
    valid_px = ~np.isnan(ra_rad)
    if valid_px.any():
        pix_flat = ahp.lonlat_to_healpix(
            ra_rad[valid_px]  * u.rad,
            dec_rad[valid_px] * u.rad,
        )
        vals = sky_map[pix_flat]
        vals = np.where(np.isfinite(vals), vals, np.nan)
        img[valid_px] = vals

    return img


def plot_sky_map(
    sky_map: np.ndarray,
    nside: int = None,
    title: str = "하늘 밝기온도 지도 (CMB + 전경)",
    save_path: str = None,
):
    """
    HEALPix 지도를 Mollweide 투영으로 시각화
    healpy.mollview + healpy.graticule 완전 대체한 사항
    """
    if nside is None:
        nside = int(np.round(np.sqrt(len(sky_map) / 12)))

    img = _healpix_to_mollweide_image(sky_map, nside)

    finite_vals = sky_map[np.isfinite(sky_map)]
    vmin = float(np.percentile(finite_vals,  2)) if len(finite_vals) else -1
    vmax = float(np.percentile(finite_vals, 98)) if len(finite_vals) else  1

    fig = plt.figure(figsize=(12, 6))
    ax  = fig.add_subplot(111, projection='mollweide')

    img_h, img_w = img.shape
    xs = np.linspace(-np.pi, np.pi, img_w)
    ys = np.linspace(np.pi / 2, -np.pi / 2, img_h)
    xg, yg = np.meshgrid(xs, ys)

    pcm = ax.pcolormesh(
        xg, yg, img,
        cmap='RdYlBu_r', vmin=vmin, vmax=vmax,
        shading='auto', rasterized=True,
    )

    # 위선/경선 그리기 (healpy.graticule 대체사항임)
    gc = (0.5, 0.5, 0.5, 0.4)
    for dec_deg in range(-60, 61, 30):
        dec_r = np.radians(dec_deg)
        ra_r  = np.linspace(-np.pi, np.pi, 500)
        ax.plot(ra_r, np.full_like(ra_r, dec_r), '-', color=gc, lw=0.7)
        ax.text(0, dec_r + np.radians(3), f'{dec_deg:+d}deg',
                ha='center', va='bottom', fontsize=7, color='gray')

    for ra_offset in range(-150, 151, 60):
        if abs(ra_offset) == 180:
            continue
        ra_r  = np.radians(ra_offset)
        dec_r = np.linspace(-np.pi / 2, np.pi / 2, 200)
        ax.plot(np.full_like(dec_r, ra_r), dec_r, '-', color=gc, lw=0.7)

    plt.colorbar(pcm, ax=ax, label='밝기온도 [K]', fraction=0.03, pad=0.04)
    ax.set_title(title, fontsize=13, pad=12)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  저장 완료: {save_path}")
    plt.show()
    plt.close()


def plot_spectrum_sample(result: dict, save_path: str = None):
    """
    단일 관측의 보정된 스펙트럼과 밝기온도를 plot
    """
    fig, axes = plt.subplots(2, 1, figsize=(10, 7))

    mask     = result['freqs_corrected'] > 0
    freqs_gh = result['freqs_corrected'][mask] / 1e9

    ax = axes[0]
    ax.set_xlabel('주파수 [GHz]')
    ax.set_ylabel('파워 (임의 단위)')
    ax.set_title('도플러 보정 후 파워 스펙트럼')
    ax.grid(alpha=0.3)

    ax2 = axes[1]
    ax2.plot(freqs_gh, result['T_b_spectrum'], color='tomato', lw=0.8)
    ax2.axhline(result['T_b_raw'],
                color='navy',  ls='--',
                label=f"T_b_raw = {result['T_b_raw']:.2f} K")
    ax2.axhline(result['T_brightness'],
                color='green', ls='--',
                label=f"T_sky   = {result['T_brightness']:.4f} K")
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



# 셀프 테스트를 진행해 보자
if __name__ == '__main__':
    print("=" * 60)
    print("CMB 밝기온도 지도 파이프라인 테스트")
    print("=" * 60)

    OBS_TIME = '2026-04-09T12:00:00'
    OBS_LAT  = 37.5
    OBS_LON  = 126.9
    T_SYS    = 50.0

    # 테스트 1: 도플러 보정
    print("\n[1] 도플러 보정 테스트")
    for name, ra, dec in [
        ("은하 중심",    266.4, -28.9),
        ("은하 반중심",   86.4,  28.9),
        ("은하 북극",    192.9,  27.1),
    ]:
        v = radial_velocity_correction(ra, dec, OBS_TIME, OBS_LAT, OBS_LON)
        print(f"  {name:10s} (ra={ra:5.1f}, dec={dec:+5.1f}): {v:+8.3f} km/s")

    # 테스트 2: 단일 포인트 처리
    print("\n[2] 단일 관측 포인트 처리")
    result = process_observation(
        ra_deg=168.0, dec_deg=-7.0,
        obs_time=OBS_TIME,
        obs_lat=OBS_LAT, obs_lon=OBS_LON,
        T_sys=T_SYS,
        seed=42,
    )
    print(f"  T_b_raw : {result['T_b_raw']:.4f} K")
    print(f"  T_sky   : {result['T_brightness']:.4f} K")
    print(f"  이론값  : {_cmb_temperature_model(168.0, -7.0):.4f} K")

    result2 = process_observation(
        ra_deg=348.0, dec_deg=7.0,
        obs_time=OBS_TIME,
        obs_lat=OBS_LAT, obs_lon=OBS_LON,
        T_sys=T_SYS,
        seed=42,
    )
    dT = result['T_brightness'] - result2['T_brightness']
    print(f"  쌍극자 dT: {dT*1000:.2f} mK  (이론 ~6.72 mK)")

    # 테스트 3: HEALPix 2D 그래프(?)
    print("\n[3] HEALPix 하늘 지도 생성 (nside=16)")
    nside           = 16
    ra_all, dec_all = get_pixel_coords(nside)
    print(f"  총 {len(ra_all)}개 픽셀 처리 중...", flush=True)

    observations = []
    for i, (ra, dec) in enumerate(zip(ra_all, dec_all)):
        obs = process_observation(
            ra_deg=float(ra), dec_deg=float(dec),
            obs_time=OBS_TIME,
            obs_lat=OBS_LAT, obs_lon=OBS_LON,
            T_sys=T_SYS,
            seed=i,
        )
        observations.append(obs)
        if (i + 1) % 500 == 0:
            print(f"    {i+1}/{len(ra_all)} 완료")

    sky_map, hit_map = build_sky_map(observations, nside=nside)

    filled = sky_map[np.isfinite(sky_map)]
    print(f"\n  지도 통계:")
    print(f"    관측된 픽셀 : {(hit_map > 0).sum()} / {len(sky_map)}")
    print(f"    T_sky 평균  : {filled.mean():.4f} K")
    print(f"    T_sky 최소  : {filled.min():.4f} K")
    print(f"    T_sky 최대  : {filled.max():.4f} K")
    print(f"    T_sky 편차  : {filled.std()*1000:.2f} mK")

    print("\n 지도 출력 중")
    plot_sky_map(sky_map, nside=nside, save_path='cmb_sky_map.png')
    print("\n완료!")
