#by @mikuiskawai
#vlbi code?
import numpy as np
import matplotlib.pyplot as plt

# 1. 데이터 로드
A = np.load("ant1.npy")   # complex I/Q 추천
B = np.load("ant2.npy")

# 길이 맞추기
N = min(len(A), len(B))
A = A[:N]
B = B[:N]

# 2. 전처리
A = A - np.mean(A)
B = B - np.mean(B)

# 윈도우 적용 (노이즈 감소)
window = np.hanning(N)
A *= window
B *= window

# 3. FFT (주파수 영역)
FA = np.fft.fft(A)
FB = np.fft.fft(B)

# 4. Cross Power Spectrum
cross_power = FA * np.conj(FB)

# 5. 상관 함수 (IFFT)
corr = np.fft.ifft(cross_power)
corr = np.fft.fftshift(corr)

lags = np.arange(-N//2, N//2)

# 최대 상관 위치
max_idx = np.argmax(np.abs(corr))
best_lag = lags[max_idx]

print(f"[INFO] Delay (lag): {best_lag}")

# 6. 위상 차이
phase = np.angle(cross_power)

# 7. Visibility (간섭계 핵심 데이터)
visibility = cross_power / np.abs(cross_power + 1e-10)

# 8. uv-plane (간단 버전)
grid_size = 128
uv_plane = np.zeros((grid_size, grid_size), dtype=complex)

# 중앙에 데이터 넣기 (단일 baseline)
u = grid_size // 2
v = grid_size // 2

uv_plane[u, v] = np.mean(visibility)

# 9. 이미지 복원
image = np.fft.ifft2(uv_plane)
image = np.fft.fftshift(image)

# 10. 시각화
plt.figure(figsize=(12,4))

# 상관 함수
plt.subplot(1,3,1)
plt.plot(lags, np.abs(corr))
plt.axvline(best_lag, linestyle='--')
plt.title("Correlation")

# uv-plane
plt.subplot(1,3,2)
plt.imshow(np.abs(uv_plane))
plt.title("uv-plane")

# 이미지
plt.subplot(1,3,3)
plt.imshow(np.abs(image))
plt.title("Reconstructed Image")

plt.tight_layout()
plt.show()
