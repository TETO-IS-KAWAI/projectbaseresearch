#by @mikuiskawai
import numpy as np
import matplotlib.pyplot as plt

from astropy_healpix import HEALPix
import astropy.units as u
from scipy.ndimage import gaussian_filter

# =========================
# HEALPix 설정
# =========================

NSIDE = 64
hp = HEALPix(nside=NSIDE, order="ring", frame="icrs")

npix = hp.npix

# =========================
# 랜덤 CMB 생성
# =========================

# 랜덤 노이즈
cmb = np.random.normal(0, 1, npix)

# 스무딩 (CMB처럼 얼룩 패턴)
cmb = gaussian_filter(cmb, sigma=10)

# 정규화
cmb = (cmb - np.mean(cmb)) / np.std(cmb)

# =========================
# 좌표 변환
# =========================

lon, lat = hp.healpix_to_lonlat(np.arange(npix))

lon = lon.wrap_at(180*u.deg).radian
lat = lat.radian

# =========================
# 시각화
# =========================

fig = plt.figure(figsize=(12,6))
ax = fig.add_subplot(111, projection="mollweide")

sc = ax.scatter(
    lon,
    lat,
    c=cmb,
    s=5,
    cmap="coolwarm"
)

ax.grid(True)

plt.colorbar(sc, orientation="horizontal", pad=0.05)
plt.title("Simulated CMB Sky")

plt.show()
