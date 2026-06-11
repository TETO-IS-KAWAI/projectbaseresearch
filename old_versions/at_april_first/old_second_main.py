import sys, os
import PySide6
import scipy, astropy
import numpy as np
import matplotlib.pyplot as plt
from astropy_healpix import HEALPix
from astropy.coordinates import SkyCoord
import astropy.units as units
from scipy.optimize import curve_fit
import json
import time
import astropy.io.fits as fits
from astropy.coordinates import EarthLocation, AltAz, SkyCoord
from astropy.time import Time

import old_versions.at_april_first.main as main
import healpix_view

healpix_view.StellarEngine.planck_law
