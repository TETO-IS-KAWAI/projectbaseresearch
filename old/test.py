import sys
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

# HEALPix 관련 라이브러리
from astropy_healpix import HEALPix
from astropy.coordinates import SkyCoord
import astropy.units as u

class HealpixCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(5, 5), dpi=100)
        self.axes = self.fig.add_subplot(111, projection='3d')
        super().__init__(self.fig)
        
    def plot_hp(self, nside=4):
        self.axes.clear()
        hp = HEALPix(nside=nside, order='ring')
        num_pix = hp.npix
        
        # 1. 모든 픽셀의 중심 좌표(Ra, Dec) 구하기
        pix_indices = np.arange(num_pix)
        coords = hp.healpix_to_skycoord(pix_indices)
        ra = coords.ra.radian
        dec = coords.dec.radian

        # 2. 구면 좌표(Ra, Dec)를 3D 직교 좌표(x, y, z)로 변환
        # 천문학에서는 Dec이 90도(북극)에서 -90도(남극)이므로 변환에 주의
        x = np.cos(dec) * np.cos(ra)
        y = np.cos(dec) * np.sin(ra)
        z = np.sin(dec)

        # 3. 픽셀 데이터를 가시화 (여기선 픽셀 번호를 데이터값으로 사용)
        data = pix_indices 
        
        # 산점도(Scatter)로 픽셀 중심 찍기 혹은 Poly3D로 면 그리기
        # 여기서는 이해를 돕기 위해 픽셀 중심을 점으로 표시합니다.
        sc = self.axes.scatter(x, y, z, c=data, cmap='viridis', s=20)
        
        # 구체 가이드라인 (선택 사항)
        self.draw_sphere_wireframe()

        self.axes.set_title(f"HEALPix NSIDE={nside} (Total {num_pix} Pixels)")
        self.axes.axis('off')
        self.draw()

    def draw_sphere_wireframe(self):
        u = np.linspace(0, 2 * np.pi, 20)
        v = np.linspace(0, np.pi, 20)
        x = 0.99 * np.outer(np.cos(u), np.sin(v))
        y = 0.99 * np.outer(np.sin(u), np.sin(v))
        z = 0.99 * np.outer(np.ones(np.size(u)), np.cos(v))
        self.axes.plot_wireframe(x, y, z, color="gray", alpha=0.2)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySide6 + Astropy HEALPix 3D")
        self.resize(800, 800)
        
        widget = QWidget()
        self.setCentralWidget(widget)
        layout = QVBoxLayout(widget)
        
        self.canvas = HealpixCanvas(self)
        layout.addWidget(self.canvas)
        
        # NSIDE 4로 매핑 시작
        self.canvas.plot_hp(nside=4)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
