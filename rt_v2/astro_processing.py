"""
astro_processing.py
전파망원경 데이터 처리 모듈

기능
  - .bin 파일 (Airspy IQ float32 인터리브) 읽기
  - 도플러 효과 보정 (지구 자전 / 지구 공전 / 은하 LSR)
  - 레일리-진스 공식으로 밝기온도 환산
  - HEALPix 하늘 지도 생성 및 시각화

의존 라이브러리: numpy, astropy, astropy-healpix, matplotlib
HEALPix 연산은 astropy-healpix (BSD) 만 사용합니다.
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

UNSEEN = np.nan                         # 미관측/무효 픽셀 표시


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
    with np.errstate(invalid='ignore'):
        result = (raw[0::2] + 1j * raw[1::2]).astype(np.complex64)
    return result




def load_iq_wav(
    filepath: str,
    max_seconds: float = None,
) -> tuple:
    """
    WAV (RIFF/RF64) IQ 파일 → (complex64 배열, sample_rate) 반환.

    지원 포맷
    ---------
    - RIFF WAV  : 표준 WAV (< 4 GB)
    - RF64 WAV  : 확장 WAV (≥ 4 GB 또는 SDR 소프트웨어 기본값)

    지원 샘플 포맷
    -------------
    - int16 PCM  (audio_format=1, bits=16) : SDR#, GQRX 기본
    - int8  PCM  (audio_format=1, bits=8)
    - int32 PCM  (audio_format=1, bits=32)
    - float32    (audio_format=3, bits=32) : Airspy HF+ 등
    - WAVE_FORMAT_EXTENSIBLE (audio_format=0xFFFE) : SubFormat 자동 판별

    데이터 구조
    -----------
    2채널 인터리브:  ch1 = I,  ch2 = Q

    Parameters
    ----------
    max_seconds : 최대 읽을 길이 [초]. None 이면 전체.
                  대용량 파일에서 메모리를 절약할 때 사용.

    수정 이력
    ---------
    - [BUG-1] RIFF fmt_offset 고정(=12): junk/LIST 등 선행 청크 있을 때 오파싱
              → WAVE 서명 이후 청크를 순회하여 fmt 위치를 탐색하도록 수정
    - [BUG-2] data_start = fmt_offset+8+fmt_size+8 고정:
              fmt 뒤에 fact/LIST 등 중간 청크가 있을 때 오프셋 오계산
              → fmt 이후도 청크 순회하여 'data' 청크를 직접 탐색
    - [BUG-3] audio_format 미검증: float32 PCM(format=3) 파일을 int16으로
              읽어 완전히 잘못된 IQ값 생성
              → audio_format / SubFormat GUID 판별 후 dtype 분기
    - [BUG-4] bits != 16 일 때 np.frombuffer dtype=int16 고정:
              bits=8/24/32 에서 샘플 수와 값 모두 틀림
              → bits에 맞는 dtype 선택 (int8/int16/int32/float32)
    - [BUG-5] RF64 ds64 파싱: fmt_offset = 12+8+ds64_size 는 올바르나
              ds64_size를 header[16:20]에서 읽으므로 header 버퍼가
              128바이트로 충분한지 확인 필요 → 필요 시 재읽기로 보완
    """
    import struct

    # ── 헤더를 넉넉히 읽기 (청크 순회를 위해 512 바이트)
    with open(filepath, 'rb') as f:
        header = f.read(512)

    magic = header[:4]
    if magic not in (b'RIFF', b'RF64'):
        raise ValueError(
            f'지원하지 않는 WAV 포맷입니다: {magic!r}\n'
            f'RIFF 또는 RF64 WAV 파일이어야 합니다.'
        )

    is_rf64 = (magic == b'RF64')

    # ── [BUG-1 수정] 청크 순회로 fmt 위치 탐색
    # RF64: WAVE(offset=8) 뒤 첫 청크는 반드시 ds64
    # RIFF: WAVE(offset=8) 뒤 청크 순회 (junk/LIST/bext 등 건너뜀)
    wave_pos = 12   # 'WAVE' 4바이트 직후

    fmt_offset   = None
    data_offset  = None   # data body 시작 위치 (청크 순회 1차 패스로 기록)

    pos = wave_pos
    while pos + 8 <= len(header):
        chunk_id   = header[pos:pos+4]
        chunk_size = struct.unpack_from('<I', header, pos+4)[0]

        if chunk_id == b'fmt ':
            fmt_offset = pos
        elif chunk_id == b'data':
            data_offset = pos + 8   # data body
            break

        pos += 8 + chunk_size
        # 홀수 바이트 패딩 (RIFF 스펙)
        if chunk_size % 2 != 0:
            pos += 1

    if fmt_offset is None:
        raise ValueError('WAV 파일에서 fmt 청크를 찾을 수 없습니다.')

    # ── fmt 청크 파싱
    audio_format = struct.unpack_from('<H', header, fmt_offset + 8)[0]
    channels     = struct.unpack_from('<H', header, fmt_offset + 10)[0]
    sample_rate  = struct.unpack_from('<I', header, fmt_offset + 12)[0]
    bits         = struct.unpack_from('<H', header, fmt_offset + 22)[0]
    fmt_size     = struct.unpack_from('<I', header, fmt_offset +  4)[0]

    if channels != 2:
        raise ValueError(
            f'IQ WAV는 2채널(I+Q)이어야 합니다. 현재: {channels}채널'
        )

    # ── [BUG-3 수정] audio_format 판별
    # WAVE_FORMAT_EXTENSIBLE(0xFFFE): SubFormat GUID에서 실제 포맷 읽기
    is_float = False
    if audio_format == 0xFFFE:
        # SubFormat GUID: fmt body offset 24 (cbSize=2, valid_bits=2, mask=4, GUID=16)
        subformat_offset = fmt_offset + 8 + 24
        if subformat_offset + 2 <= len(header):
            subformat_tag = struct.unpack_from('<H', header, subformat_offset)[0]
            if subformat_tag == 3:
                is_float = True
            elif subformat_tag != 1:
                raise ValueError(
                    f'WAVEFORMATEXTENSIBLE SubFormat {subformat_tag:#06x} 미지원\n'
                    f'PCM(0x0001) 또는 IEEE_FLOAT(0x0003)만 지원합니다.'
                )
    elif audio_format == 3:
        is_float = True
    elif audio_format != 1:
        raise ValueError(
            f'지원하지 않는 audio_format: {audio_format:#06x}\n'
            f'PCM(1), IEEE_FLOAT(3), EXTENSIBLE(0xFFFE)만 지원합니다.'
        )

    # ── [BUG-4 수정] bits → numpy dtype 선택
    if is_float:
        if bits == 32:
            sample_dtype = np.float32
        elif bits == 64:
            sample_dtype = np.float64
        else:
            raise ValueError(f'float WAV의 bits={bits} 미지원 (32 또는 64만 가능)')
    else:
        pcm_dtype_map = {8: np.int8, 16: np.int16, 32: np.int32}
        if bits not in pcm_dtype_map:
            raise ValueError(
                f'PCM bits={bits} 미지원. 지원: 8, 16, 32\n'
                f'(24-bit PCM은 현재 미지원)'
            )
        sample_dtype = pcm_dtype_map[bits]

    # ── [BUG-2 수정] data 청크를 청크 순회로 탐색
    # 512바이트 버퍼에서 못 찾은 경우 파일을 더 읽어 탐색
    if data_offset is None:
        with open(filepath, 'rb') as f:
            # fmt 이후부터 탐색 (대용량 헤더 대비 4KB)
            f.seek(fmt_offset + 8 + fmt_size)
            extra = f.read(4096)
        epos = 0
        while epos + 8 <= len(extra):
            cid   = extra[epos:epos+4]
            csz   = struct.unpack_from('<I', extra, epos+4)[0]
            if cid == b'data':
                data_offset = (fmt_offset + 8 + fmt_size) + epos + 8
                break
            epos += 8 + csz
            if csz % 2 != 0:
                epos += 1
        if data_offset is None:
            raise ValueError('WAV 파일에서 data 청크를 찾을 수 없습니다.')

    # ── 읽을 바이트 수 계산
    bytes_per_sample = bits // 8
    bytes_per_frame  = channels * bytes_per_sample
    if max_seconds is not None:
        max_frames = int(max_seconds * sample_rate)
        read_bytes = max_frames * bytes_per_frame
    else:
        read_bytes = None   # 전체

    # ── 데이터 읽기
    with open(filepath, 'rb') as f:
        f.seek(data_offset)
        raw_bytes = f.read(read_bytes)

    raw = np.frombuffer(raw_bytes, dtype=sample_dtype)

    # 홀수 샘플 제거
    if raw.size % 2 != 0:
        raw = raw[:-1]

    # ── float / int → complex64 변환
    if is_float:
        I = raw[0::2].astype(np.float32)
        Q = raw[1::2].astype(np.float32)
    else:
        scale = 1.0 / (2 ** (bits - 1))
        I = raw[0::2].astype(np.float32) * scale
        Q = raw[1::2].astype(np.float32) * scale

    iq = (I + 1j * Q).astype(np.complex64)
    return iq, int(sample_rate)



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



def icrs_to_galactic(ra_deg: float, dec_deg: float) -> tuple:
    """
    ICRS (RA, Dec) → 은하 좌표 (l, b) 변환.

    반환
    ----
    l_deg : 은하 경도 [deg]
    b_deg : 은하 위도  [deg]
    """
    coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame='icrs')
    gal   = coord.galactic
    return float(gal.l.deg), float(gal.b.deg)


def galactocentric_velocity(
    ra_deg: float,
    dec_deg: float,
    v_lsr_kms: float,
    R_sun_kpc: float = 8.5,
    v_circ_kms: float = 220.0,
) -> dict:
    """
    LSR 시선 속도 → 은하 좌표계 해석.

    주어진 방향의 LSR 시선 속도와 은하 회전 모델(고체 회전 근사)로
    HI 가스 구름의 은하 회전 성분을 계산.

    Parameters
    ----------
    v_lsr_kms   : 관측된 LSR 시선 속도 [km/s]
    R_sun_kpc   : 태양~은하 중심 거리 [kpc]  (기본: IAU 권고값 8.5 kpc)
    v_circ_kms  : 은하 원반 원형 속도 [km/s]  (기본: 220 km/s)

    Returns
    -------
    dict with keys:
        l_deg, b_deg         : 은하 좌표
        v_lsr_kms            : 입력 LSR 속도
        v_tangent_kms        : 접선 속도 (은하 회전 기준 최대 속도)
        kinematic_distance_near_kpc  : 근거리 운동학적 거리 추정 [kpc]
        kinematic_distance_far_kpc   : 원거리 운동학적 거리 추정 [kpc]
        in_inner_galaxy      : 내부 은하 (R < R_sun) 여부
    """
    l_deg, b_deg = icrs_to_galactic(ra_deg, dec_deg)
    l = np.radians(l_deg)
    b = np.radians(b_deg)

    # 접선점 최대 LSR 속도 (평탄 회전 곡선 기준, 내부 은하만 의미 있음)
    v_tan = v_circ_kms * (1.0 - np.abs(np.sin(l)))

    # 운동학적 거리 (평면 근사, |b| < 5° 일 때만 의미 있음)
    sin_l = np.sin(l)
    if abs(sin_l) < 0.01:
        d_near = d_far = float('nan')
        in_inner = False
    else:
        # v_lsr = v_circ * (R_sun/R - 1) * sin(l) * cos(b) 에서 R 역산
        cos_b = np.cos(b)
        with np.errstate(invalid='ignore', divide='ignore'):
            ratio = v_lsr_kms / (v_circ_kms * sin_l * cos_b) + 1.0
            if ratio <= 0:
                d_near = d_far = float('nan')
                in_inner = False
            else:
                R = R_sun_kpc / ratio
                in_inner = R < R_sun_kpc
                # 거리 공식 (2차 방정식 해)
                discriminant = R_sun_kpc**2 - R**2 * (1 / np.cos(b)**2 - np.tan(l)**2)
                if discriminant < 0:
                    d_near = d_far = float('nan')
                else:
                    sqrt_d = np.sqrt(max(discriminant, 0))
                    d_near = R_sun_kpc * np.cos(l) - sqrt_d
                    d_far  = R_sun_kpc * np.cos(l) + sqrt_d
                    d_near = max(d_near, 0.0)

    return {
        'l_deg':                       l_deg,
        'b_deg':                       b_deg,
        'v_lsr_kms':                   v_lsr_kms,
        'v_tangent_kms':               float(v_tan),
        'kinematic_distance_near_kpc': float(d_near) if 'd_near' in dir() else float('nan'),
        'kinematic_distance_far_kpc':  float(d_far)  if 'd_far'  in dir() else float('nan'),
        'in_inner_galaxy':             in_inner if 'in_inner' in dir() else False,
    }


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
# 4. 밝기온도 환산 (밴드패스 보정)
# ───────────────────────────────────────────────────────────

def estimate_bandpass(
    power_spectral_density: np.ndarray,
    window_frac: float = 0.07,
) -> np.ndarray:
    """
    기기 밴드패스 B(ν) 추정 — 이동 중앙값(running median).

    SDR 수신기의 파워 스펙트럼은 아날로그/디지털 필터에 의해
    중앙이 높고 가장자리로 갈수록 떨어지는 '돔' 형태의 밴드패스를
    가집니다. 단일 스칼라 기준선으로는 이 주파수 의존 형태를 제거할 수
    없어 스펙트럼 전체가 부풀려집니다.

    이동 중앙값은 폭이 좁은 HI 방출선은 건너뛰고(중앙값은 이상치에
    강건) 완만한 밴드패스 곡선만 추적하므로, 임의의 밴드패스 형태
    (비대칭 롤오프 포함)에 대해 강건하게 동작합니다.

    Parameters
    ----------
    power_spectral_density : 선형 파워 배열
    window_frac            : 중앙값 창 크기(전체 채널 대비 비율).
                             창은 밴드패스 변화(수백 km/s)보다는 좁고
                             HI 선폭(수~수십 km/s)보다는 충분히 넓어야 함.
                             기본 0.07 → nfft=2048에서 ≈143채널(≈35 km/s)
    """
    from scipy.ndimage import median_filter

    P = np.asarray(power_spectral_density, dtype=np.float64)
    n = len(P)
    k = max(11, int(n * window_frac))
    if k % 2 == 0:
        k += 1   # 홀수 창
    B = median_filter(P, size=k, mode='nearest')
    # 0/음수 보호
    fallback = np.median(P[P > 0]) if np.any(P > 0) else 1.0
    B = np.where(B > 0, B, fallback)
    return B


def rayleigh_jeans_temperature(
    power_spectral_density: np.ndarray,
    freq_hz: np.ndarray,
    G_sys: float = 1.0,
    nfft: int = 2048,
    T_sys: float = 50.0,
    bandpass_window_frac: float = 0.07,
) -> np.ndarray:
    """
    밴드패스 보정 기반 상대 밝기온도 계산.

    SDR 수신기는 정규화된 ADC count를 출력하므로 절대 전력[W]을 알 수
    없어 Rayleigh-Jeans 역산(T = P·c²/2ν²k_B)으로 절대 온도를 구하는
    것이 불가능합니다. 대신 기기 밝기패스 B(ν)로 정규화한 상대 온도를
    사용합니다:

        T_b(ν) = [P(ν) / B(ν) − 1] × T_sys

    여기서 B(ν)는 이동 중앙값으로 추정한 기기 밴드패스입니다.
    (이전 버전은 B를 스펙트럼 양 가장자리의 단일 스칼라로 추정했으나,
     가장자리가 밴드패스 롤오프의 최저점이라 중앙 전체가 ~T_sys만큼
     부풀려지는 버그가 있었습니다.)

    이 정의에서:
      - off-line(HI 선 없는) 채널: T_b ≈ 0 K
      - HI 방출선 피크: T_b = (선 초과분 / 밴드패스) × T_sys  [K]

    Parameters
    ----------
    power_spectral_density : compute_power_spectrum() 반환 power[mask]
    freq_hz                : 대응하는 주파수 배열 (현재는 사용 안 함, 호환성 유지)
    G_sys                  : 시스템 이득 (현재는 사용 안 함, 호환성 유지)
    nfft                   : FFT 크기 (현재는 사용 안 함, 호환성 유지)
    T_sys                  : 시스템 잡음 온도 [K] (기본: 50 K)
    bandpass_window_frac   : 밴드패스 추정 이동 중앙값 창 비율 (기본 0.07)
    """
    P = np.asarray(power_spectral_density, dtype=np.float64)
    B = estimate_bandpass(P, window_frac=bandpass_window_frac)
    return (P / B - 1.0) * T_sys


def representative_brightness_temp(
    T_b_spectrum: np.ndarray,
    method: str = 'peak',
    v_axis: np.ndarray = None,
    v_window_kms: float = 150.0,
    smooth_bins: int = 3,
) -> float:
    """
    스펙트럼에서 하늘 밝기온도 대푯값 추출 (HI 선 영역 기준).

    밴드패스 보정 후 off-line 채널은 T_b ≈ 0 이므로, 전체 스펙트럼의
    중앙값/평균은 잡음 수준(≈0)일 뿐 하늘 신호를 대표하지 못합니다.
    따라서 HI 선이 존재하는 속도 창(|v_LSR| < v_window_kms)으로 한정해
    대푯값을 계산합니다.

    method
    ------
    'peak'     : 선 영역 최대 T_b [K] — 그 방향에서 가장 밝은 HI (기본값)
    'integral' : 적분 강도 W = Σ T_b·Δv [K·km/s] — HI 주상밀도 N_HI 비례
    'mean'     : 선 영역 평균 T_b [K]
    'median'   : 선 영역 중앙값 T_b [K]

    Parameters
    ----------
    v_axis       : 각 채널의 LSR 속도 [km/s]. None이면 전체 스펙트럼 사용.
    v_window_kms : HI 선 영역 속도 창 반폭 [km/s] (기본 150)
    smooth_bins  : 'peak' 추출 전 이동평균 창 [채널] — 단일 채널 잡음/RFI
                   스파이크가 피크로 잡히는 것을 방지 (기본 3, 0이면 생략)
    """
    T = np.asarray(T_b_spectrum, dtype=np.float64)
    finite = np.isfinite(T)
    if v_axis is not None:
        in_line = finite & (np.abs(np.asarray(v_axis)) < v_window_kms)
    else:
        in_line = finite
    if not np.any(in_line):
        return float('nan')

    T_line = T[in_line]

    if method == 'peak':
        if smooth_bins and smooth_bins > 1 and len(T_line) >= smooth_bins:
            from scipy.ndimage import uniform_filter1d
            T_line = uniform_filter1d(T_line, size=smooth_bins)
        return float(np.max(T_line))
    elif method == 'integral':
        if v_axis is None:
            raise ValueError("method='integral'은 v_axis가 필요합니다.")
        v_line = np.asarray(v_axis)[in_line]
        order  = np.argsort(v_line)
        # 방출(T_b>0)만 적분 — 음의 잡음이 강도를 깎지 않도록
        T_pos = np.clip(T_line[order], 0.0, None)
        # NumPy 2.0+ 는 trapz → trapezoid 로 이름 변경
        _trap = getattr(np, 'trapezoid', None) or np.trapz
        return float(_trap(T_pos, v_line[order]))
    elif method == 'mean':
        return float(np.mean(T_line))
    elif method == 'median':
        return float(np.median(T_line))
    else:
        raise ValueError(
            f"method는 'peak','integral','mean','median' 중 하나여야 합니다. "
            f"(입력: {method!r})"
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
    n_samples: int = 2_097_152,
    T_sys: float = 50.0,
    G_sys: float = 1.0,
    line_width_kms: float = 18.0,
    line_offset_kms: float = 0.0,
    seed: int = None,
) -> np.ndarray:
    """
    HI 관측 시뮬레이션용 더미 IQ 데이터 생성.
    bin_filepath / wav_filepath 모두 None이면 process_observation 에서 자동 호출됨.

    구성
    ----
    1) 시스템 잡음 : 평탄 PSD 백색 복소 잡음 (T_sys)
    2) HI 방출선   : 기저대역 중심 부근에 Gaussian PSD로 대역제한된 잡음
                     (방출선은 비간섭성 → CW 톤이 아니라 잡음 형태)
                     세기는 _hi_temperature_model(ra,dec)의 T_sky 로 결정.

    n_samples 가 충분히 크면(기본 2^21 → 1024청크 평균) 잡음 바닥이
    낮아져, 신호가 없을 때 detect_peaks 가 거짓 피크를 만들지 않습니다.

    Parameters
    ----------
    line_width_kms  : HI 방출선 FWHM [km/s]  (은하 HI 전형값 ~15-25)
    line_offset_kms : 기저대역상 선 중심 속도 오프셋 [km/s]
                      (도플러 보정은 이후 단계에서 별도 적용됨)
    """
    rng   = np.random.default_rng(seed)
    T_sky = _hi_temperature_model(ra_deg, dec_deg)
    nu    = center_freq_hz

    # ── 1) 시스템 잡음 (평탄)
    P_sys  = G_sys * 2.0 * nu ** 2 * _K_B * T_sys / _C_MS ** 2
    s_sys  = np.sqrt(max(P_sys, 1e-30) / 2.0)
    iq = (rng.normal(0, s_sys, n_samples)
          + 1j * rng.normal(0, s_sys, n_samples))

    # ── 2) HI 방출선 (Gaussian PSD 대역제한 잡음)
    if T_sky > 0 and line_width_kms > 0:
        P_line = G_sys * 2.0 * nu ** 2 * _K_B * T_sky / _C_MS ** 2
        s_line = np.sqrt(max(P_line, 1e-30) / 2.0)
        line = (rng.normal(0, s_line, n_samples)
                + 1j * rng.normal(0, s_line, n_samples))
        # 선폭 FWHM → 기저대역 σ [Hz];  중심 오프셋 [Hz]
        sigma_hz = (line_width_kms / _C_KMS) * nu / 2.3548
        f0_hz    = (line_offset_kms / _C_KMS) * nu
        f = np.fft.fftfreq(n_samples, d=1.0 / sample_rate)
        gauss = np.exp(-0.5 * ((f - f0_hz) / sigma_hz) ** 2)
        # 피크=1 정규화 → 선 중심 PSD 높이가 s_line²(=T_sky) 수준 유지
        # ⇒ 선 피크 T_b ≈ T_sky (PSD 비율로 정의되는 밝기온도와 일치)
        line = np.fft.ifft(np.fft.fft(line) * gauss)
        iq = iq + line

    return iq.astype(np.complex64)


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
    wav_filepath: str = None,
    center_freq_hz: float = HI_FREQ_HZ,
    sample_rate: float = 2.5e6,
    nfft: int = 2048,
    obs_height_m: float = 0.0,
    T_sys: float = 50.0,
    G_sys: float = 1.0,
    temp_method: str = 'peak',
    seed: int = None,
) -> dict:
    """
    관측 1포인트 처리:
    IQ 읽기(또는 생성) → FFT → 도플러 보정 → T_b 환산 → 대푯값

    bin_filepath  : Airspy .bin (float32 IQ). None이면 wav_filepath 확인.
    wav_filepath  : WAV/RF64 IQ 파일. sample_rate 헤더에서 자동 감지.
    둘 다 None이면 더미 IQ 자동 생성.

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
    if wav_filepath is not None:
        iq, sample_rate = load_iq_wav(wav_filepath, max_seconds=30.0)
    elif bin_filepath is not None:
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
    # T_b(ν) = [P(ν)/B(ν) − 1] × T_sys   (B = 이동 중앙값 밴드패스)
    # off-line 채널 ≈ 0 K, HI 피크 = 선 초과분/밴드패스 × T_sys
    mask         = freqs_corrected > 0
    freqs_m      = freqs_corrected[mask]
    T_b_spectrum = rayleigh_jeans_temperature(
        power[mask], freqs_m,
        G_sys=G_sys, nfft=nfft, T_sys=T_sys,
    )

    # HI 선 영역 속도축 (LSR)
    v_axis = _C_KMS * (center_freq_hz - freqs_m) / center_freq_hz

    # 하늘 대푯값: 선 영역 피크 T_b (지도 색상값) + 적분 강도(주상밀도 비례)
    # temp_method('peak'/'integral'/'mean'/'median')로 지도 색상값 선택 가능
    T_b_peak = representative_brightness_temp(
        T_b_spectrum, method='peak', v_axis=v_axis)
    W_HI = representative_brightness_temp(
        T_b_spectrum, method='integral', v_axis=v_axis)
    try:
        T_sky = representative_brightness_temp(
            T_b_spectrum, method=temp_method, v_axis=v_axis)
    except ValueError:
        T_sky = T_b_peak   # 알 수 없는 method면 피크로 폴백
    T_b_raw = T_b_peak

    l_deg, b_deg = icrs_to_galactic(ra_deg, dec_deg)
    return {
        'ra':              ra_deg,
        'dec':             dec_deg,
        'v_radial_kms':    v_kms,
        'T_brightness':    T_sky,
        'T_b_raw':         T_b_raw,
        'T_b_peak':        T_b_peak,
        'W_HI_K_kms':      W_HI,
        'success':         np.isfinite(T_sky),
        'l_deg':           l_deg,
        'b_deg':           b_deg,
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
# 8. 시각화  (Mollweide 투영)
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