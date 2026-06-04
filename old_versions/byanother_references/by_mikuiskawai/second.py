#by @mikuiskawai
#%pip install healpy
#%pip install matplotlib
import healpy as hp
import matplotlib.pyplot as plt

m = hp.read_map("map_ilc_yr1_v1.fits")

hp.mollview(
    m,
    cmap="jet",
    min="-0.2",
    max="0.2",
    title="CMB Map (jet tuned)",
    unit="μK"
)

plt.show()
