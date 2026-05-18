"""
sky_viewer.py  [PyVista 버전]
PyVista + pyvistaqt 기반 3D HEALPix 천구 뷰어

pyqtgraph 대비 장점
  - VTK 렌더링 품질 (안티앨리어싱, 조명, 셰이더)
  - 쿼드 메쉬 직접 지원 → 픽셀 경계 틈 없음
  - 컬러바, 축, 레이블 내장

내부 시점: 카메라를 구 중심(0,0,0)에 두고 바깥 방향을 바라봄.
"""

from __future__ import annotations

import sys
from typing import Optional

import numpy as np
from astropy_healpix import HEALPix
import astropy.units as u

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)

import pyvista as pv
from pyvistaqt import QtInteractor

from config import Config
from astro_processing import get_pixel_coords, _hi_temperature_model
from data_manager import get_project


# ── 더미 지도 스레드 ────────────────────────────────────────

class DummyMapWorker(QThread):
    ready = Signal(np.ndarray)
    def __init__(self, nside, parent=None):
        super().__init__(parent); self._nside = nside
    def run(self):
        ra, dec = get_pixel_coords(self._nside)
        self.ready.emit(np.array([
            _hi_temperature_model(float(r), float(d))
            for r, d in zip(ra, dec)], dtype=np.float32))


# ── 메인 뷰어 위젯 ──────────────────────────────────────────

class SkyViewerWidget(QWidget):
    """
    외부 인터페이스
    ---------------
    update_from_obs(result)
    refresh_from_project()
    reset_map()
    """

    _R = 50.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cfg   = Config.get()
        self._nside = self._cfg.nside
        self._hp    = HEALPix(nside=self._nside, order='ring', frame='icrs')
        self._mesh: Optional[pv.PolyData] = None
        self._actor = None
        self._dummy_map: Optional[np.ndarray] = None
        self._build_ui()
        self._init_scene()
        self._start_dummy_worker()

    # ── UI ──────────────────────────────────────────────────

    def _build_ui(self):
        self.setStyleSheet('background:#000008;')
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        title = QLabel('HI 21cm Brightness Temperature Map  [PyVista]')
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            'color:#cce8ff;font-size:14px;font-weight:600;'
            'padding:6px;background:#00000f;letter-spacing:2px;')
        root.addWidget(title)

        self._plotter = QtInteractor(self)
        self._plotter.set_background('black')
        root.addWidget(self._plotter.interactor, stretch=1)

        bar = QWidget(); bar.setStyleSheet('background:#00000f;')
        hb  = QHBoxLayout(bar); hb.setContentsMargins(16,5,16,5)
        self._status = QLabel('더미 지도 생성 중...')
        self._status.setStyleSheet('color:#7aaccc;font-size:11px;')
        hb.addWidget(self._status); hb.addStretch()

        btn_s = ('background:#0f3460;color:#cce8ff;border:none;'
                 'border-radius:3px;padding:3px 10px;font-size:11px;')
        for label, slot in [('더미 지도로 초기화', self.reset_map),
                             ('격자 토글', self._toggle_grid)]:
            b = QPushButton(label); b.setStyleSheet(btn_s); b.clicked.connect(slot)
            hb.addWidget(b)
        root.addWidget(bar)

        self._grid_on = True

    # ── 씬 초기화 ────────────────────────────────────────────

    def _init_scene(self):
        self._build_healpix_mesh()
        self._add_grid()
        self._add_labels()
        # 내부 시점: 카메라를 중심에, 은하 중심 방향으로 focalpoint 설정
        self._plotter.camera.position       = (0.0, 0.0, 0.0)
        self._plotter.camera.focal_point    = (
            self._R * np.cos(np.radians(-29)) * np.cos(np.radians(266)),
            self._R * np.cos(np.radians(-29)) * np.sin(np.radians(266)),
            self._R * np.sin(np.radians(-29)),
        )
        self._plotter.camera.view_up        = (0.0, 0.0, 1.0)
        self._plotter.camera.view_angle     = 90.0

    def _build_healpix_mesh(self, sky_map: Optional[np.ndarray] = None):
        """PyVista 쿼드 메쉬로 HEALPix 구체 생성."""
        npix     = self._hp.npix
        lon, lat = self._hp.boundaries_lonlat(np.arange(npix), step=1)
        lo = lon.to_value('rad'); la = lat.to_value('rad')
        r  = self._R

        x = r * np.cos(la) * np.cos(lo)
        y = r * np.cos(la) * np.sin(lo)
        z = r * np.sin(la)
        verts = np.column_stack([x.flatten(), y.flatten(), z.flatten()])

        # 쿼드 면 배열: [4, v0, v1, v2, v3] × npix
        faces = np.zeros(npix * 5, dtype=int)
        for i in range(npix):
            v0 = i * 4
            faces[i*5:i*5+5] = [4, v0, v0+1, v0+2, v0+3]

        self._mesh = pv.PolyData(verts, faces)

        T = sky_map if sky_map is not None else np.zeros(npix, dtype=np.float32)
        self._mesh.cell_data['T_brightness'] = T

        if self._actor is not None:
            self._plotter.remove_actor(self._actor)

        self._actor = self._plotter.add_mesh(
            self._mesh,
            scalars='T_brightness',
            cmap='RdYlBu_r',
            show_scalar_bar=True,
            scalar_bar_args={'title': 'T_b [K]', 'color': 'white'},
            smooth_shading=False,
            show_edges=False,
            flip_scalars=False,
        )
        self._plotter.render()

    def _add_grid(self):
        self._grid_actors = []
        r = self._R * 0.999
        # 위선
        for lat_deg in range(-75, 91, 15):
            p = np.radians(lat_deg); t = np.linspace(0, 2*np.pi, 180)
            pts = np.column_stack([r*np.cos(p)*np.cos(t),
                                   r*np.cos(p)*np.sin(t),
                                   np.full(180, r*np.sin(p))])
            line = pv.Spline(pts, 180)
            a = self._plotter.add_mesh(line, color='white', opacity=0.2, line_width=1)
            self._grid_actors.append(a)
        # 경선
        for lon_deg in range(0, 360, 30):
            t = np.radians(lon_deg); p = np.linspace(-np.pi/2, np.pi/2, 180)
            pts = np.column_stack([r*np.cos(p)*np.cos(t),
                                   r*np.cos(p)*np.sin(t), r*np.sin(p)])
            line = pv.Spline(pts, 180)
            a = self._plotter.add_mesh(line, color='white', opacity=0.2, line_width=1)
            self._grid_actors.append(a)

    def _add_labels(self):
        r = self._R * 0.97
        labels = [
            ('N',  (0,    0,    r)),
            ('S',  (0,    0,   -r)),
            ('E',  (0,    r,    0)),
            ('W',  (0,   -r,    0)),
        ]
        for text, pos in labels:
            self._plotter.add_point_labels(
                [pos], [text], font_size=18, bold=True,
                text_color='yellow', always_visible=True,
                show_points=False, shape=None,
            )
        # RA 레이블
        for ra_deg in range(0, 360, 30):
            t = np.radians(ra_deg)
            pos = [r*np.cos(t), r*np.sin(t), r*0.05]
            self._plotter.add_point_labels(
                [pos], [f'{ra_deg}°'], font_size=10,
                text_color='lightblue', always_visible=True,
                show_points=False, shape=None,
            )
        # Dec 레이블
        for dec_deg in range(-75, 91, 15):
            if dec_deg == 0: continue
            p   = np.radians(dec_deg)
            pos = [r*np.cos(p), r*0.02, r*np.sin(p)]
            self._plotter.add_point_labels(
                [pos], [f'{dec_deg:+d}°'], font_size=10,
                text_color='lightgreen', always_visible=True,
                show_points=False, shape=None,
            )

    # ── 더미 지도 ────────────────────────────────────────────

    def _start_dummy_worker(self):
        self._worker = DummyMapWorker(nside=self._nside)
        self._worker.ready.connect(self._on_dummy_ready)
        self._worker.start()

    @Slot(np.ndarray)
    def _on_dummy_ready(self, sky_map: np.ndarray):
        self._dummy_map = sky_map
        self._apply_map(sky_map)
        finite = sky_map[np.isfinite(sky_map)]
        self._status.setText(
            f'더미 HI 모델  |  T: {finite.min():.1f}~{finite.max():.1f} K  '
            f'|  프로젝트를 열면 실제 관측 데이터로 갱신.')

    # ── 공개 메서드 ──────────────────────────────────────────

    @Slot(dict)
    def update_from_obs(self, result: dict):
        proj = get_project()
        if proj.sky_map is not None:
            self._apply_map(proj.sky_map)
            filled = proj.sky_map[np.isfinite(proj.sky_map)]
            self._status.setText(
                f'관측 {proj.obs_count}건  |  T: {filled.min():.1f}~{filled.max():.1f} K  |  '
                f'RA={result["ra"]:.1f}° Dec={result["dec"]:.1f}°')

    def refresh_from_project(self):
        proj = get_project()
        if not proj.is_open or proj.sky_map is None: return
        if proj.nside != self._nside:
            self._nside = proj.nside
            self._hp    = HEALPix(nside=self._nside, order='ring', frame='icrs')
        self._apply_map(proj.sky_map)
        filled = proj.sky_map[np.isfinite(proj.sky_map)]
        n = len(filled)
        self._status.setText(
            f'프로젝트: {proj.name}  |  관측 {proj.obs_count}건  |  유효픽셀 {n}' +
            (f'  |  T: {filled.min():.1f}~{filled.max():.1f} K' if n else ''))

    def reset_map(self):
        if self._dummy_map is not None:
            self._apply_map(self._dummy_map)
        self._status.setText('더미 HI 모델로 초기화됨.')

    def _toggle_grid(self):
        self._grid_on = not self._grid_on
        for a in self._grid_actors:
            a.SetVisibility(self._grid_on)
        self._plotter.render()

    # ── 내부 ────────────────────────────────────────────────

    def _apply_map(self, sky_map: np.ndarray):
        if self._mesh is None:
            self._build_healpix_mesh(sky_map); return
        T = sky_map.copy()
        T[~np.isfinite(T)] = float(np.nanmin(sky_map))
        self._mesh.cell_data['T_brightness'] = T
        self._plotter.update_scalars('T_brightness', mesh=self._mesh)
        self._plotter.render()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = QMainWindow()
    win.setWindowTitle('Sky Viewer — PyVista')
    win.resize(1100, 750)
    win.setCentralWidget(SkyViewerWidget())
    win.show()
    sys.exit(app.exec())
