import numpy as np
from astropy_healpix import HEALPix

def project_mollweide(ra, dec):
    ra, dec = np.atleast_1d(ra), np.atleast_1d(dec)
    lon, lat = np.radians(ra - 180), np.radians(dec)
    theta = lat.copy()
    for _ in range(10):
        denom = 2 + 2 * np.cos(2 * theta)
        denom = np.where(np.abs(denom) < 1e-10, 1e-10, denom)
        theta += -(2 * theta + np.sin(2 * theta) - np.pi * np.sin(lat)) / denom
    x = (2 * np.sqrt(2) / np.pi) * lon * np.cos(theta)
    y = np.sqrt(2) * np.sin(theta)
    return x, y

def get_hp_coords(nside, ordering='ring'):
    hp = HEALPix(nside=nside, order=ordering, frame='icrs')
    indices = np.arange(hp.npix)
    coords = hp.healpix_to_skycoord(indices)
    return coords.ra.deg, coords.dec.deg