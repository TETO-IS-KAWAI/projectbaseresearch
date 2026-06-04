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
# [설정 항목] 내 관측 환경 및 은하계 표준 상수
# ==========================================
F_0 = 1420405751.768       # 21cm 수소선 고유 주파수 (Hz)
C = 299792458.0            # 빛의 속도 (m/s)

# 내 관측소 위치 (세종시 부근 좌표 반영 완료)
MY_LOCATION = EarthLocation(lat=36.522764*u.deg, lon=127.248878*u.deg, height=66*u.m)
DATA_FOLDER = "./observation/"

# 🌌 [천문학 상수] 우리 은하 매핑을 위한 표준값 세팅 (IAU 기준)
R_0 = 8.5   # 태양(지구)에서 은하 중심까지의 거리 (kpc, 킬로파섹)
V_0 = 220.0 # 태양 위치에서의 우리 은하 기본 회전 속도 (km/s)

# ==========================================
# 2. 데이터 처리 함수들 (기존 스택 알고리즘 유지)
# ==========================================
def process_wav_file(file_path):
    """1분짜리 대용량 WAV를 0.5초씩 쪼개서 스택(평균) 연산하여 속도와 화질을 모두 잡습니다."""
    sample_rate, data = wav.read(file_path)
    if len(data.shape) > 1:
        data = data.mean(axis=1) # 모노 변환
        
    segment_len = int(sample_rate * 0.5) 
    num_segments = len(data) // segment_len
    
    if num_segments == 0:
        num_segments = 1
        segment_len = len(data)

    print(f"   [스택 연산] 총 {num_segments}개의 조각으로 나누어 누적(Stacking) 중...")
    
    fft_freq = np.fft.fftfreq(segment_len, d=1/sample_rate)
    pos_mask = fft_freq >= 0
    freqs = fft_freq[pos_mask]
    
    total_power = np.zeros(len(freqs))
    for i in range(num_segments):
        start_idx = i * segment_len
        end_idx = start_idx + segment_len
        chunk = data[start_idx:end_idx]
        
        fft_data = np.fft.fft(chunk)
        power = np.abs(fft_data[pos_mask])**2
        total_power += power
        
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
# 3. 폴더 자동 스캔 및 은하 평면 공간 좌표 변환
# ==========================================
x_points, y_points, intensity_values = [], [], []

if not os.path.exists(DATA_FOLDER):
    print(f"❌ '{DATA_FOLDER}' 폴더가 없습니다.")
    exit()

all_files = [f for f in os.listdir(DATA_FOLDER) if f.endswith('.wav')]
print(f"📡 '{DATA_FOLDER}' 폴더에서 총 {len(all_files)}개의 파일로 은하 평면도 매핑 시작...\n")

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
    velocities_kms = velocities / 1000.0  # km/s 단위 변환
    
    # 은하 좌표계 변환
    sc_icrs = SkyCoord(ra=ra*u.deg, dec=dec*u.deg, frame='icrs')
    l_rad = sc_icrs.galactic.l.rad
    l_deg = sc_icrs.galactic.l.degree
    b_rad = sc_icrs.galactic.b.rad
    
    print(f"🔄 공간 변환 중: {file_name} -> 은경: {l_deg:.1f}°, 은위: {sc_icrs.galactic.b.degree:.1f}°")
    
    # 💡 [핵심 알고리즘] 주파수 채널별 신호를 은하 위에서 내려다본 X, Y 평면 좌표로 전개
    for v, p in zip(velocities_kms, power):
        # 1. 기하학적 왜곡을 만드는 노이즈 대역 차단 (-150 ~ 150 km/s 유효 수소선 대역 설정)
        # 2. 바닥에 깔린 자잘한 RFI/시스템 열잡음 피크(최대 강도의 5% 이하) 무시
        if (v < -150) or (v > 150) or (p < np.max(power) * 0.05):
            continue
            
        try:
            sin_l = np.sin(l_rad)
            cos_l = np.cos(l_rad)
            cos_b = np.cos(b_rad)
            
            # 은하 중심과 은하 반대 중심 방향(sin(l)~0)은 거리 분해가 불가능하므로 수학적 특이점 보호
            if np.abs(sin_l) < 0.08: 
                continue
                
            # 은하 중심 기준 가스 구름의 반경 거리 R 계산 (은하 회전 모델)
            R = R_0 * (V_0 * sin_l) / (v / cos_b + V_0 * sin_l)
            if (R <= 0) or (R > 22): 
                continue
                
            # 제2코사인 법칙의 근의 공식을 이용해 태양-수소 구름 간 직선거리 d 역산
            discriminant = R**2 - (R_0 * sin_l)**2
            if discriminant < 0: 
                continue
                
            d = R_0 * cos_l + np.sqrt(discriminant)
            if d < 0 or d > 20: 
                continue
                
            # 💡 3D 투영: 태양이 (0, 8.5)에 있고 은하 중심이 (0, 0)인 2D 평면 직교 좌표계(kpc 단위)
            x = d * sin_l * cos_b
            y = R_0 - d * cos_l * cos_b
            
            x_points.append(x)
            y_points.append(y)
            intensity_values.append(p)
        except:
            continue
            
    print(f"✅ 좌표 맵인 완료!\n")

# ==========================================
# 4. 은하 평면도(Top-down View) 시각화 세팅
# ==========================================
if len(x_points) < 5:
    print("❌ 2D 공간 지도를 그리기에 유효한 수소 가스 데이터 포인트가 부족합니다.")
    print("💡 은경(l) 방향이 서로 다른 관측 파일을 최소 2~3개 이상 추가해 주세요!")
    exit()

# 격자 공간 생성 (은하 중심 사방 15kpc 영역 탐색 grid)
grid_x, grid_y = np.mgrid[-15:15:300j, -15:15:300j]

# 데이터 밀도에 맞춰 보간 방식 자동 전환
interpolation_method = 'linear' if len(x_points) >= 50 else 'nearest'
grid_z = griddata(np.vstack((x_points, y_points)).T, np.array(intensity_values), 
                  (grid_x, grid_y), method=interpolation_method, fill_value=0)

# 밤하늘 우주 느낌을 내기 위해 검은색 배경 테마 적용
fig = plt.figure(figsize=(10, 10), facecolor='black')
ax = plt.subplot(111, facecolor='black')

# 회색조(gray) 또는 원하는 경우 오렌지색 계열(copper, magma)로 은하 구름 출력
img = ax.imshow(grid_z.T, extent=[-15, 15, -15, 15], origin='lower', cmap='gray', alpha=0.85)
cbar = fig.colorbar(img, ax=ax, shrink=0.75)
cbar.set_label("Hydrogen Line Intensity", color='white')
cbar.ax.tick_params(colors='white')

# 🎯 핵심 랜드마크 마킹 (은하 중심 및 내 태양계의 위치)
ax.scatter(0, 0, color='crimson', s=150, marker='*', edgecolors='white', zorder=5, label='Galactic Center (0,0)')
ax.scatter(0, R_0, color='deepskyblue', s=60, edgecolors='white', zorder=5, label='Sun / Earth (0, 8.5)')

# 나선팔 구조 판단을 돕는 가이드 동심원(반경 3, 5, 8.5, 12 kpc) 그리기
for r in [3, 5, R_0, 12]:
    linestyle = '-' if r == R_0 else ':'
    alpha = 0.5 if r == R_0 else 0.25
    circle = plt.Circle((0, 0), r, color='white', linestyle=linestyle, alpha=alpha, fill=False)
    ax.add_patch(circle)

# 인포메이션 디자인 세팅
ax.set_title("Milky Way Hydrogen Structure\n[Top-Down View]", color='white', fontsize=14, fontweight='bold', pad=15)
ax.set_xlabel("X (kpc)", color='white', fontsize=11)
ax.set_ylabel("Y (kpc)", color='white', fontsize=11)
ax.tick_params(colors='white')
ax.grid(color='gray', linestyle='--', alpha=0.15)

plt.xlim(-15, 15)
plt.ylim(-15, 15)
plt.legend(facecolor='#111111', edgecolor='gray', labelcolor='white', loc='upper right')
plt.tight_layout()
plt.show()
