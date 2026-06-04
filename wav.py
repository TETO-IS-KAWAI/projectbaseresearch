import numpy as np
import scipy.io.wavfile as wav
import matplotlib.pyplot as plt
from scipy.interpolate import griddata
from astropy.coordinates import SkyCoord, EarthLocation
from astropy.time import Time
import astropy.units as u
import os
import re

# ==========================================
# [설정 항목] 내 관측 환경에 맞게 필수 수정!
# ==========================================
F_0 = 1420405751.768       # 21cm 수소선 고유 주파수 (Hz)
C = 299792458.0            # 빛의 속도 (m/s)

# 내 관측소 위치 (예: 서울)
MY_LOCATION = EarthLocation(lat=36.522764*u.deg, lon=127.248878*u.deg, height=66*u.m)
DATA_FOLDER = "./observation/"

# ==========================================
# 2. 데이터 처리 함수들
# ==========================================
def process_wav_file(file_path):
    """1분짜리 대용량 WAV를 0.5초씩 쪼개서 스택(평균) 연산하여 속도와 화질을 모두 잡습니다."""
    sample_rate, data = wav.read(file_path)
    if len(data.shape) > 1:
        data = data.mean(axis=1) # 모노 변환
        
    # 0.5초 크기의 조각(Segment)으로 분할 계산 설정
    segment_len = int(sample_rate * 0.5) 
    num_segments = len(data) // segment_len
    
    if num_segments == 0:
        num_segments = 1
        segment_len = len(data)

    print(f"   [스택 연산] 총 {num_segments}개의 조각으로 나누어 누적(Stacking) 중...")
    
    # 첫 번째 조각으로 주파수 축 기초 생성
    fft_freq = np.fft.fftfreq(segment_len, d=1/sample_rate)
    pos_mask = fft_freq >= 0
    freqs = fft_freq[pos_mask]
    
    # 누적할 빈 배열 생성
    total_power = np.zeros(len(freqs))
    
    # 루프를 돌며 각 조각의 FFT 결과를 겹쳐서 더함 (스택 효과)
    for i in range(num_segments):
        start_idx = i * segment_len
        end_idx = start_idx + segment_len
        chunk = data[start_idx:end_idx]
        
        fft_data = np.fft.fft(chunk)
        power = np.abs(fft_data[pos_mask])**2
        total_power += power
        
    # 평균 내기 (노이즈 감소)
    avg_power = total_power / num_segments
    
    center_freq_obs = 1420.4e6 
    actual_freqs = freqs - freqs.mean() + center_freq_obs
    return actual_freqs, avg_power

def get_doppler_velocity(freqs, ra, dec, obs_time):
    sc = SkyCoord(ra=ra*u.deg, dec=dec*u.deg, frame='icrs')
    v_corr = sc.radial_velocity_correction(kind='barycentric', obstime=obs_time, location=MY_LOCATION)
    v_corr_ms = v_corr.to(u.m/u.s).value
    freqs_rest = freqs * (1 - v_corr_ms / C)
    velocities = C * (F_0 - freqs_rest) / F_0
    l = sc.galactic.l.rad
    b = sc.galactic.b.rad
    v_sun_to_lsr = 10000.0 * np.cos(l) * np.cos(b) + 15400.0 * np.sin(l) * np.cos(b) + 7800.0 * np.sin(b)
    return velocities - v_sun_to_lsr

# ==========================================
# 3. 폴더 자동 스캔 및 데이터 수집
# ==========================================
ra_list, dec_list, intensity_list = [], [], []
last_velocities, last_power = None, None
last_gl, last_gb = 0, 0

if not os.path.exists(DATA_FOLDER):
    print(f"❌ '{DATA_FOLDER}' 폴더가 없습니다.")
    exit()

all_files = [f for f in os.listdir(DATA_FOLDER) if f.endswith('.wav')]
print(f"📡 '{DATA_FOLDER}' 폴더에서 총 {len(all_files)}개의 수소선 파일 매핑 시작...")

for file_name in all_files:
    match = re.match(r"obs_([+-]?\d+\.?\d*)_([+-]?\d+\.?\d*)_(\d{8}-\d{6})\.wav", file_name)
    if not match:
        continue
        
    ra = float(match.group(1))
    dec = float(match.group(2))
    time_raw = match.group(3)
    
    time_str = f"{time_raw[:4]}-{time_raw[4:6]}-{time_raw[6:8]}T{time_raw[9:11]}:{time_raw[11:13]}:{time_raw[13:15]}"
    obs_time = Time(time_str, format='isot', scale='utc')
    
    file_path = os.path.join(DATA_FOLDER, file_name)
    freqs, power = process_wav_file(file_path)
    velocities = get_doppler_velocity(freqs, ra, dec, obs_time)
    
    # 임시 저장 (파일이 1개일 때 스펙트럼 플롯용)
    last_velocities = velocities / 1000.0  # km/s 단위
    last_power = power
    
    v_mask = (velocities >= -150000) & (velocities <= 150000)
    intensity = np.abs(np.trapezoid(power[v_mask], velocities[v_mask]))
    
    sc_icrs = SkyCoord(ra=ra*u.deg, dec=dec*u.deg, frame='icrs')
    last_gl = sc_icrs.galactic.l.degree
    last_gb = sc_icrs.galactic.b.degree
    
    ra_list.append(sc_icrs.galactic.l.wrap_at(180*u.deg).degree)
    dec_list.append(last_gb)
    intensity_list.append(intensity)
    print(f"✅ 분석 완료: {file_name} -> 은경: {last_gl:.1f}°")

# ==========================================
# 4. 스마트 가시화 (개수에 따라 자동 분기)
# ==========================================
if len(ra_list) == 0:
    print("❌ 읽어온 정상 파일이 전혀 없습니다. 파일명을 다시 확인해 주세요.")

elif len(ra_list) == 1:
    # 💡 데이터가 1개뿐일 때는 수소선 스펙트럼 그래프를 보여줍니다.
    print("\n💡 데이터가 1개이므로 해당 방향의 수소선 스펙트럼 프로파일을 출력합니다.")
    plt.figure(figsize=(10, 5))
    plt.plot(last_velocities, last_power, color='crimson', label='HI Signal')
    plt.axvspan(-300, 300, color='gray', alpha=0.1, label='Galactic Velocity Range')
    plt.axvline(0, color='black', linestyle='--', alpha=0.5)
    plt.title(f"21cm Line Profile (Galactic $l$={last_gl:.1f}°, $b$={last_gb:.1f}°)")
    plt.xlabel("LSR Velocity (km/s)")
    plt.ylabel("Intensity")
    plt.xlim(-500, 500)
    plt.grid(True, linestyle=':')
    plt.legend()
    plt.show()

else:
    # 💡 데이터가 여러 개 모이면 2D 지도를 그려줍니다.
    print(f"\n💡 {len(ra_list)}개의 데이터가 확인되어 2D 은하수 매핑 지도를 출력합니다.")
    points = np.vstack((ra_list, dec_list)).T
    values = np.array(intensity_list)
    grid_l, grid_b = np.mgrid[-180:180:300j, -90:90:150j]
    
    interpolation_method = 'linear' if len(ra_list) >= 4 else 'nearest'
    grid_z = griddata(points, values, (grid_l, grid_b), method=interpolation_method)
    
    plt.figure(figsize=(12, 6))
    plt.imshow(grid_z.T, extent=[-180, 180, -90, 90], origin='lower', cmap='magma', aspect='equal')
    plt.colorbar(label="Intensity")
    plt.scatter(ra_list, dec_list, color='cyan', s=30, edgecolors='black', label='Observed')
    plt.title("21cm Hydrogen Line Galactic Map (2D)")
    plt.grid(color='white', linestyle=':', alpha=0.3)
    plt.legend()
    plt.show()
