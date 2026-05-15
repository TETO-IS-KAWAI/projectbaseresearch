import warnings
import numpy as np

from astropy.time import Time
from astropy.coordinates import EarthLocation, SkyCoord
import astropy.units as u
import astropy.constants as const
from astropy_healpix import HEALPix
from astropy.utils import iers

import matplotlib.pyplot as plt

iers.conf.auto_download = False

_C_MS  = const.c.to(u.m / u.s).value
_C_KMS = const.c.to(u.km / u.s).value
_K_B   = const.k_B.value

HI_FREQ_HZ = 1.42040575177e9

UNSEEN = np.nan

def load_iq_bin(filepath: str) -> np.ndarray:
    raw = np.fromfile(filepath, dtype=np.float32)
    if raw.size % 2 != 0:
        raw = raw[:-1]
    return (raw[0::2] + 1j * raw[1::2]).astype(np.complex64)

def compute_power_spectrum(
    iq: np.ndarray,
    sample_rate: float,
    nfft: int = 2048,
) -> tuple:
    n_chunks = len(iq) // nfft
    if n_chunks == 0:
        raise ValueError(
            f"IQ 길이({len(iq)})가 nfft({nfft})보다 짧음"
        )
    iq_chunks = iq[: n_chunks * nfft].reshape(n_chunks, nfft)
    window    = np.blackman(nfft)
    fft_out   = np.fft.fftshift(
        np.fft.fft(iq_chunks * window, axis=1), axes=1
    )
    power = np.mean(np.abs(fft_out) ** 2, axis=0)
    freqs = np.fft.fftshift(np.fft.fftfreq(nfft, d=1.0 / sample_rate))
    return freqs, power


_LSR_V_KMS  = 20.0
_LSR_RA_DEG = 270.0
_LSR_DE_DEG =  30.0


def radial_velocity_correction(
    ra_deg: float,
    dec_deg: float,
    obs_time: str,
    obs_lat: float,
    obs_lon: float,
    obs_height_m: float = 0.0,
) -> float:
    coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame='icrs')
    loc   = EarthLocation(
        lat=obs_lat * u.deg,
        lon=obs_lon * u.deg,
        height=obs_height_m * u.m,
    )
    t = Time(obs_time, format='isot', scale='utc')

    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        vcorr_helio = coord.radial_velocity_correction(
            kind='heliocentric', obstime=t, location=loc,
        ).to(u.km / u.s).value

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
    return -(vcorr_helio + v_lsr)


def doppler_correct_freqs(
    freqs_offset: np.ndarray,
    center_freq_hz: float,
    v_radial_kms: float,
) -> np.ndarray:
    beta  = v_radial_kms / _C_KMS
    f_abs = center_freq_hz + freqs_offset
    return f_abs * (1.0 + beta)

def fft_gain_factor(nfft: int) -> float:
    window = np.blackman(nfft)
    return float(nfft * np.mean(window ** 2))


def rayleigh_jeans_temperature(
    power_spectral_density: np.ndarray,
    freq_hz: np.ndarray,
    G_sys: float = 1.0,
    nfft: int = 2048,
) -> np.ndarray:
    G_fft = fft_gain_factor(nfft)
    P_cal = power_spectral_density / (G_fft * G_sys)
    return P_cal * _C_MS ** 2 / (2.0 * freq_hz ** 2 * _K_B)


def representative_brightness_temp(
    T_b_spectrum: np.ndarray,
    method: str = 'median',
) -> float:
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
            f"method는 'median', 'mean', 'peak' 중 하나여야 (입력: {method!r})"
        )


def _hi_temperature_model(ra_deg: float, dec_deg: float) -> float:
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
    rng    = np.random.default_rng(seed)
    T_sky  = _hi_temperature_model(ra_deg, dec_deg)
    T_obs  = T_sky + T_sys
    nu     = center_freq_hz
    P_mean = G_sys * 2.0 * nu ** 2 * _K_B * T_obs / _C_MS ** 2
    sigma  = np.sqrt(max(P_mean, 1e-30) / 2.0)
    I = rng.normal(0, sigma, n_samples).astype(np.float32)
    Q = rng.normal(0, sigma, n_samples).astype(np.float32)
    return (I + 1j * Q).astype(np.complex64)


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

    freq_offsets, power = compute_power_spectrum(iq, sample_rate, nfft)

    v_kms           = radial_velocity_correction(
        ra_deg, dec_deg, obs_time,
        obs_lat, obs_lon, obs_height_m,
    )
    freqs_corrected = doppler_correct_freqs(freq_offsets, center_freq_hz, v_kms)

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

def build_sky_map(
    observations: list,
    nside: int = 32,
) -> tuple:
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

    ahp    = HEALPix(nside=nside, order='ring', frame='icrs')
    coords = ahp.healpix_to_skycoord(np.arange(ahp.npix))
    return coords.ra.deg, coords.dec.deg

def _healpix_to_mollweide_image(
    sky_map: np.ndarray,
    nside: int,
    img_width: int = 800,
    img_height: int = 400,
) -> np.ndarray:
    ahp = HEALPix(nside=nside, order='ring', frame='icrs')

    xs = np.linspace(-2 * np.sqrt(2),  2 * np.sqrt(2), img_width)
    ys = np.linspace( np.sqrt(2),     -np.sqrt(2),      img_height)
    xg, yg = np.meshgrid(xs, ys)

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

    outside          = (xg ** 2 / 8 + yg ** 2 / 2) > 1.0
    ra_rad[outside]  = np.nan
    dec_rad[outside] = np.nan

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
            print(f"저장 완료: {save_path}")
        plt.show()
        plt.close()

    return pcm


def plot_spectrum_sample(result: dict, save_path: str = None):
    fig, axes = plt.subplots(2, 1, figsize=(10, 7))

    mask     = result['freqs_corrected'] > 0
    freqs_gh = result['freqs_corrected'][mask] / 1e9

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
    ax2.set_title('레일리—진스 밝기온도 스펙트럼')
    ax2.legend()
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"저장 완료: {save_path}")
    plt.show()
    plt.close()

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

    print("\n(1) 도플러 LSR 보정 테스트")
    for name, ra, dec in [
        ("은하 중심",    266.4, -28.9),
        ("은하 반중심",   86.4,  28.9),
        ("은하 북극",    192.9,  27.1),
    ]:
        v = radial_velocity_correction(ra, dec, OBS_TIME, OBS_LAT, OBS_LON)
        print(f"  {name:10s} (RA={ra:5.1f}, Dec={dec:+5.1f}): {v:+8.3f} km/s")

    print("\n(2) 단일 관측 포인트 처리")
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

    print("\n(3) 스펙트럼 저장")
    plot_spectrum_sample(result, save_path='test_spectrum.png')

    print("\n(4) HEALPix 지도 생성 (nside=8, 빠른 테스트)")
    nside = 8
    ra_all, dec_all = get_pixel_coords(nside)
    print(f"총 {len(ra_all)}개 픽셀 처리 중", flush=True)

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
    print(f"관측된 픽셀 : {(hit_map > 0).sum()} / {len(sky_map)}")
    print(f"T_sky 평균  : {filled.mean():.2f} K")
    print(f"T_sky 범위  : {filled.min():.2f} ~ {filled.max():.2f} K")

    plot_sky_map(sky_map, nside=nside, save_path='test_sky_map.png')
    print("\n완료!")
