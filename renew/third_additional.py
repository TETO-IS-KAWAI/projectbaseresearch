#temporary file
#library import
import sys
import os
import numpy

import astropy
import astropy_healpix
from astropy_healpix import HEALPix
from astropy.coordinates import SkyCoord
import astropy.units as astunits

import matplotlib
import matplotlib.pyplot as pyplot
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

import PySide6
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

import pyqtgraph
import pyqtgraph.opengl as pygl

import tkinter

data=numpy.fromfile("test.bin", dtype=np.float32)
iq_data=data[0::2]+1j*data[1::2]
print(f"Sample count: {len(iq_data)}")



import matplotlib.pyplot as plt
NFFT = 2048
#2.5MSPS
sample_rate = 2.5e6

num_chunks = len(iq_data) // NFFT
iq_data = iq_data[:num_chunks * NFFT]

chunks = iq_data.reshape((num_chunks, NFFT))

window = numpy.blackman(NFFT)
chunks = chunks * window

fft_results = numpy.fft.fftshift(numpy.fft.fft(chunks, axis=1), axes=1)

power_spectra = numpy.abs(fft_results) ** 2

averaged_power = numpy.mean(power_spectra, axis=0)

power_db = 10 * numpy.log10(averaged_power)

#-1.25MHz — +1.25MHz range
freqs = numpy.fft.fftshift(numpy.fft.fftfreq(NFFT, d=1/sample_rate))

plt.figure(figsize=(10, 5))
#frequency to hertz
plt.plot(freqs / 1e3, power_db, color='blue', linewidth=1)
plt.title("Hydrogen Line Power Spectrum (Averaged)")
plt.xlabel("Frequency Offset (kHz)")
plt.ylabel("Power (dB)")
plt.grid(True, linestyle='--', alpha=0.7)
plt.axvline(x=100, color='red', linestyle='--', label='Expected Target (+100 kHz)')
plt.legend()
plt.tight_layout()
plt.show()
