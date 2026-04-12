#by @mikuiskawai
from astropy.coordinates import SkyCoord, EarthLocation
from astropy.time import Time
import astropy.units as u

location = EarthLocation(
    lat=36.522764 * u.deg,
    lon=127.248878 * u.deg,
    height=0 * u.m   # 필요하면 고도 넣어도 됨
)

# 관측 방향
coord = SkyCoord(l=30*u.deg, b=0*u.deg, frame='galactic')

# 관측 시간
time = Time("2024-01-01T00:00:00")

# LSR 보정
vcorr = coord.radial_velocity_correction(
    kind='lsr',
    obstime=time,
    location=location
)

print(vcorr.to(u.km/u.s))
