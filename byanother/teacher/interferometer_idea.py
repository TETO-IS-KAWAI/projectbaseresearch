#선생님이 참고하라고 주신 코드
#interferometer 관련
#뭔지는 모르겠으나 AI로 돌리신 것 같음

#!/usr/bin/env python3
import numpy as np
import matplotlib.pyplot as plt
from dataclasses import dataclass
from typing import List
from astropy.io import fits
from astropy.wcs import WCS
import finufft

# 1. 상수
C = 2.99792458e8
FREQ = 1.420405751768e9
LAMBDA = C / FREQ

# 2. 배열 정의
@dataclass
class Antenna:
    name: str
    east: float
    north: float
    up: float = 0.0

class Array:
    def __init__(self, ants: List[Antenna], lat_deg=37.5):
        self.ants = ants
        self.lat = np.radians(lat_deg)

    def baselines(self):
        bl = []
        for i in range(len(self.ants)):
            for j in range(i+1, len(self.ants)):
                d = np.array([
                    self.ants[j].east - self.ants[i].east,
                    self.ants[j].north - self.ants[i].north,
                    self.ants[j].up - self.ants[i].up
                ])
                bl.append((i, j, d))
        return bl

# 3. UV 계산 (Earth rotation synthesis 포함)
def compute_uv(array, dec_deg, hour_angles):
    dec = np.radians(dec_deg)
    bls = array.baselines()

    u_list, v_list, vis_idx = [], [], []

    for h in hour_angles:
        H = np.radians(h)

        for k, (i, j, b) in enumerate(bls):
            E, N, U = b

            u = ( np.sin(H)*E + np.cos(H)*N ) / LAMBDA
            v = (-np.sin(dec)*np.cos(H)*E + np.sin(dec)*np.sin(H)*N + np.cos(dec)*U) / LAMBDA

            u_list.append(u)
            v_list.append(v)
            vis_idx.append((i, j))

    return np.array(u_list), np.array(v_list), vis_idx

# 4. RFI 제거 (robust sigma clipping)
def flag_rfi(vis, sigma=3.5):
    amp = np.abs(vis)
    med = np.median(amp)
    mad = np.median(np.abs(amp - med))
    mask = amp < (med + sigma * 1.4826 * mad)
    return vis[mask], mask

# 5. Delay calibration (baseline별)
def apply_delay(vis, vis_idx, delays):
    out = []
    for (i, j), v in zip(vis_idx, vis):
        tau = delays[j] - delays[i]
        out.append(v * np.exp(-2j*np.pi*FREQ*tau))
    return np.array(out)

# 6. Phase center shift (정확)
def phase_shift(u, v, vis, dra_deg, ddec_deg, dec0_deg):
    dra = np.radians(dra_deg)
    ddec = np.radians(ddec_deg)
    dec0 = np.radians(dec0_deg)

    l = np.cos(dec0) * np.sin(dra)
    m = np.sin(ddec)

    return vis * np.exp(2j*np.pi*(u*l + v*m))

# 7. NUFFT imaging
def make_image_nufft(u, v, vis, npix=256, fov_deg=10):
    fov = np.radians(fov_deg)
    du = 1.0 / fov

    # normalize coords to [-pi, pi]
    x = 2*np.pi * u * du
    y = 2*np.pi * v * du

    img = finufft.nufft2d1(x, y, vis, npix, npix)
    return np.fft.fftshift(img.real)

# 8. PSF 생성
def make_psf(u, v, npix=256, fov_deg=10):
    vis = np.ones_like(u, dtype=complex)
    return make_image_nufft(u, v, vis, npix, fov_deg)

# 9. CLEAN (Högbom)
def clean(dirty, psf, gain=0.1, niter=500):
    model = np.zeros_like(dirty)
    residual = dirty.copy()

    psf_center = np.array(psf.shape)//2

    for _ in range(niter):
        peak = np.unravel_index(np.argmax(residual), residual.shape)
        amp = residual[peak]

        model[peak] += gain * amp

        shift = np.array(peak) - psf_center
        shifted_psf = np.roll(np.roll(psf, shift[0], axis=0), shift[1], axis=1)

        residual -= gain * amp * shifted_psf

    return model, residual

# 10. Primary beam
def apply_primary_beam(image, fov_deg=10):
    npix = image.shape[0]
    x = np.linspace(-1,1,npix)
    X,Y = np.meshgrid(x,x)

    sigma = 0.4
    beam = np.exp(-(X**2 + Y**2)/sigma**2)

    return image * beam

# 11. FITS 저장 (WCS 포함)
def save_fits(image, filename="output.fits", fov_deg=10):
    npix = image.shape[0]
    w = WCS(naxis=2)

    w.wcs.crpix = [npix/2, npix/2]
    w.wcs.cdelt = [-fov_deg/npix, fov_deg/npix]
    w.wcs.crval = [0, 0]
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]

    hdu = fits.PrimaryHDU(image, header=w.to_header())
    hdu.writeto(filename, overwrite=True)

# 12. 실행 예시
if __name__ == "__main__":

    array = Array([
        Antenna("A1",0,0),
        Antenna("A2",100,0),
        Antenna("A3",-50,86.6),
        Antenna("A4",-50,-86.6)
    ])

    hour_angles = np.linspace(-3,3,50)
    u,v,idx = compute_uv(array, dec_deg=45, hour_angles=hour_angles)

    # synthetic sky
    vis = np.exp(-(u**2+v**2)/1e5) + 0.05*(np.random.randn(len(u))+1j*np.random.randn(len(u)))

    # RFI 제거
    vis, mask = flag_rfi(vis)
    u,v = u[mask], v[mask]
    idx = [idx[i] for i in range(len(idx)) if mask[i]]

    # delay 보정
    delays = [0, 0.2e-9, -0.1e-9, 0.05e-9]
    vis = apply_delay(vis, idx, delays)

    # phase shift
    vis = phase_shift(u, v, vis, 0.2, -0.1, 45)

    # imaging
    dirty = make_image_nufft(u, v, vis)
    psf = make_psf(u, v)

    model, residual = clean(dirty, psf)

    final = apply_primary_beam(model + residual)

    save_fits(final)

    plt.imshow(final, cmap='inferno')
    plt.title("Final CLEAN Image (HI 21cm)")
    plt.colorbar()
    plt.show()
