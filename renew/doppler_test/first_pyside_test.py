
# cmb_viewer_3d.py

import sys
import numpy
from astropy_healpix import HEALPix
import astropy.units as u

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QSlider, QSizePolicy,
)
from PySide6.QtGui import QFont, QColor
import pyqtgraph.opengl as pygl

# RdYlBu_r 근사


def temperature_to_rgba(
    values: numpy.ndarray,
    vmin: float = None,
    vmax: float = None,
    alpha: float = 1.0,
) -> numpy.ndarray:
    """
    밝기온도 배열을 RGBA 색상 배열로 변환.
    NaN(빈 픽셀) 은 투명(alpha=0) 처리.

    Return은  colors : (N, 4) float32  RGBA [0, 1]
    """
    v = numpy.array(values, dtype=float)
    finite = v[numpy.isfinite(v)]

    if vmin is None:
        vmin = numpy.percentile(finite,  2) if len(finite) else 0.0
    if vmax is None:
        vmax = numpy.percentile(finite, 98) if len(finite) else 1.0

    norm = numpy.clip((v - vmin) / max(vmax - vmin, 1e-30), 0.0, 1.0)

    # RdYlBu_r 근사: 파랑(0) to 노랑(0.5) to 빨강(1)
    r = numpy.where(norm < 0.5,
                    norm * 2.0,
                    1.0)
    g = numpy.where(norm < 0.5,
                    norm * 2.0,
                    2.0 * (1.0 - norm))
    b = numpy.where(norm < 0.5,
                    1.0 - norm * 2.0,
                    0.0)

    colors = numpy.zeros((len(v), 4), dtype=numpy.float32)
    colors[:, 0] = r
    colors[:, 1] = g
    colors[:, 2] = b
    colors[:, 3] = numpy.where(numpy.isfinite(v), alpha, 0.0)
    return colors


# ═══════════════════════════════════════════════════════════
# 데이터 처리 스레드
# ═══════════════════════════════════════════════════════════

class CMBDataProcessor(QThread):
    """
    백그라운드에서 CMB 더미 데이터(또는 실 데이터)를 계산하고
    완료되면 sky_map 배열을 UI 스레드로 전달.
    
    데이터 연결 시:
      self.sky_map 을 astro_processing.build_sky_map() 결과로 교체하기
    """
    data_ready = Signal(numpy.ndarray)   # sky_map [K] 배열

    def __init__(self, nside: int = 16, parent=None):
        super().__init__(parent)
        self.nside = nside

    def run(self):
        from astropy_healpix import HEALPix
        hp   = HEALPix(nside=self.nside, order='ring', frame='icrs')
        npix = hp.npix

        # 데이터 연결 시 이 블록을 astro_processing 호출로 교체.
        coords  = hp.healpix_to_skycoord(numpy.arange(npix))
        ra_deg  = coords.ra.deg
        dec_deg = coords.dec.deg

        T_cmb = 2.725
        # 쌍극자 이방성
        dip_ra  = numpy.radians(168.0)
        dip_dec = numpy.radians(-7.0)
        ra_r    = numpy.radians(ra_deg)
        dec_r   = numpy.radians(dec_deg)
        cos_a   = (numpy.cos(dec_r) * numpy.cos(dip_dec) * numpy.cos(ra_r - dip_ra)
                   + numpy.sin(dec_r) * numpy.sin(dip_dec))
        T_dipole     = 3.36e-3 * cos_a
        # 은하 전경 (dec+-15도 근처일걸?)
        T_foreground = 0.5 * numpy.exp(-0.5 * (dec_deg / 15.0) ** 2)
        rng   = numpy.random.default_rng(42)
        noise = rng.normal(0, 1e-3, npix)

        sky_map = T_cmb + T_dipole + T_foreground + noise

        self.data_ready.emit(sky_map)


class CMBViewWidget(pygl.GLViewWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.opts['fov'] = 60
        self.min_fov     = 10
        self.max_fov     = 110

    def wheelEvent(self, ev):
        delta = ev.angleDelta().y()
        new_fov = self.opts['fov'] + (2 if delta > 0 else -2)
        self.opts['fov'] = numpy.clip(new_fov, self.min_fov, self.max_fov)
        self.update()

    def mouseMoveEvent(self, ev):
        lpos = ev.position() if hasattr(ev, 'position') else ev.localPos()
        diff = lpos - getattr(self, '_last_mouse', lpos)
        self._last_mouse = lpos

        if ev.buttons() == Qt.MouseButton.LeftButton:
            self.orbit(-diff.x(), diff.y())

    def mousePressEvent(self, ev):
        self._last_mouse = (ev.position()
                            if hasattr(ev, 'position') else ev.localPos())
        super().mousePressEvent(ev)


# 메인 윈도우
class CelestialViewer(QMainWindow):

    def __init__(self, nside: int = 16):
        super().__init__()
        self.nside  = nside
        self.radius = 50.0
        self.hp     = HEALPix(nside=nside, order='ring', frame='icrs')

        self._build_ui()
        self._init_scene()
        self._start_data_thread()


    def _build_ui(self):
        self.setWindowTitle("CMB Sky Viewer — HEALPix 3D")
        self.resize(1400, 900)
        self.setStyleSheet("background:#0a0a12;")

        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # 상단 타이틀
        title = QLabel("CMB Brightness Temperature Map")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "color:#cce8ff; font-size:15px; font-weight:600;"
            "padding:8px; background:#0d0d1a; letter-spacing:2px;"
        )
        vbox.addWidget(title)

        # 3D 뷰어
        self.view = CMBViewWidget()
        self.view.setBackgroundColor((10, 10, 20, 255))
        vbox.addWidget(self.view, stretch=1)

        # 하단 정보 바
        info_bar = QWidget()
        info_bar.setStyleSheet("background:#0d0d1a;")
        hbox = QHBoxLayout(info_bar)
        hbox.setContentsMargins(16, 6, 16, 6)

        self.status_label = QLabel("데이터 처리 중...")
        self.status_label.setStyleSheet("color:#7aaccc; font-size:11px;")
        hbox.addWidget(self.status_label)

        hbox.addStretch()

        hint = QLabel("드래그: 회전   휠: 줌   데이터: CMB 쌍극자 시뮬레이션")
        hint.setStyleSheet("color:#445566; font-size:10px;")
        hbox.addWidget(hint)

        vbox.addWidget(info_bar)


    def _init_scene(self):
        self.view.setCameraPosition(distance=40, elevation=0, azimuth=0)
        self.view.opts['fov'] = 70

        self._add_stars()
        self._add_grid()
        self._init_healpix_mesh()

    def _add_stars(self):
        rng = numpy.random.default_rng(0)
        n   = 2000
        pos = rng.standard_normal((n, 3))
        pos /= numpy.linalg.norm(pos, axis=1, keepdims=True)
        pos *= self.radius * 0.98

        brightness = rng.uniform(0.3, 1.0, n)
        col = numpy.zeros((n, 4), dtype=numpy.float32)
        col[:, :3] = brightness[:, None]
        col[:,  3] = brightness

        stars = pygl.GLScatterPlotItem(pos=pos, color=col, size=1.2, pxMode=True)
        self.view.addItem(stars)

    def _add_grid(self):
        gc = (0.2, 0.35, 0.5, 0.25)

        # 위선
        for lat_deg in range(-75, 91, 15):
            phi   = numpy.radians(lat_deg)
            theta = numpy.linspace(0, 2 * numpy.pi, 120)
            x = self.radius * numpy.cos(phi) * numpy.cos(theta)
            y = self.radius * numpy.cos(phi) * numpy.sin(theta)
            z = numpy.full_like(x, self.radius * numpy.sin(phi))
            pts  = numpy.column_stack([x, y, z])
            line = pygl.GLLinePlotItem(pos=pts, color=gc, width=1, antialias=True)
            self.view.addItem(line)

        # 경선
        for lon_deg in range(0, 360, 30):
            theta = numpy.radians(lon_deg)
            phi   = numpy.linspace(-numpy.pi / 2, numpy.pi / 2, 120)
            x = self.radius * numpy.cos(phi) * numpy.cos(theta)
            y = self.radius * numpy.cos(phi) * numpy.sin(theta)
            z = self.radius * numpy.sin(phi)
            pts  = numpy.column_stack([x, y, z])
            line = pygl.GLLinePlotItem(pos=pts, color=gc, width=1, antialias=True)
            self.view.addItem(line)

    def _init_healpix_mesh(self):
        """
        HEALPix 픽셀 경계선으로 구체 메쉬 뼈대 구성.
        meshInitializeHealPix 그대로 유지.
        """
        npix = self.hp.npix
        lon, lat = self.hp.boundaries_lonlat(numpy.arange(npix), step=1)

        lon_rad = lon.to_value('rad')
        lat_rad = lat.to_value('rad')

        x = self.radius * numpy.cos(lat_rad) * numpy.cos(lon_rad)
        y = self.radius * numpy.cos(lat_rad) * numpy.sin(lon_rad)
        z = self.radius * numpy.sin(lat_rad)

        self.vertices = numpy.column_stack(
            [x.flatten(), y.flatten(), z.flatten()]
        )

        # 사각형 픽셀 삼각형 2개
        self.faces = numpy.zeros((npix * 2, 3), dtype=int)
        for i in range(npix):
            v0 = i * 4
            self.faces[i * 2]     = [v0,     v0 + 1, v0 + 2]
            self.faces[i * 2 + 1] = [v0,     v0 + 2, v0 + 3]

        # 초기 색상: 중간 회색 (데이터 도착 전)
        dummy = numpy.full((npix * 2, 4), 0.15, dtype=numpy.float32)
        dummy[:, 3] = 0.9

        self.mesh_data = pygl.MeshData(
            vertexes=self.vertices,
            faces=self.faces,
            faceColors=dummy,
        )
        # shader 제거 그림자/조명 없음, 색상 그대로 표시
        self.sky_mesh = pygl.GLMeshItem(
            meshdata=self.mesh_data,
            smooth=False,
            glOptions='translucent',
        )
        self.view.addItem(self.sky_mesh)


    def _start_data_thread(self):
        self.processor = CMBDataProcessor(nside=self.nside)
        self.processor.data_ready.connect(self._on_data_ready)
        self.processor.start()

    def _on_data_ready(self, sky_map: numpy.ndarray):
        """스레드에서 sky_map이 도착하면 색상 업데이트."""
        self.update_sky(sky_map)

        finite = sky_map[numpy.isfinite(sky_map)]
        vmin   = float(numpy.percentile(finite,  2))
        vmax   = float(numpy.percentile(finite, 98))
        mean   = float(numpy.mean(finite))
        self.status_label.setText(
            f"픽셀 수: {len(sky_map)}   "
            f"T 범위: {vmin:.4f} ~ {vmax:.4f} K   "
            f"평균: {mean:.4f} K"
        )

    def update_sky(self, sky_map: numpy.ndarray):
        """
        sky_map(HEALPix 밝기온도 배열) → 메쉬 face 색상 업데이트.
        updateSky 구조 그대로, 색상 맵만 CMB용으로 교체.
        """
        # 픽셀당 색상 계산
        pixel_colors = temperature_to_rgba(sky_map, alpha=1.0)

        # 삼각형이 픽셀당 2개 → 색상 복제
        face_colors = numpy.repeat(pixel_colors, 2, axis=0).astype(numpy.float32)

        self.mesh_data.setFaceColors(face_colors)
        self.sky_mesh.setMeshData(meshdata=self.mesh_data)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName("CMB Sky Viewer")

    window = CelestialViewer(nside=16)
    window.show()
    sys.exit(app.exec())
