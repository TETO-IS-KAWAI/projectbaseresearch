"""
sky_viewer.py
PyVista 기반 3D HEALPix 천구 뷰어 (내부 시점)

기능: HI 히트맵, 은하 전경 차감, 커버리지 표시, MOC보내기, 은하/적도 격자
"""

from __future__ import annotations

import sys
from typing import Optional

import numpy as np
from astropy_healpix import HEALPix
import astropy.units as u
from astropy.coordinates import SkyCoord

from PySide6.QtCore import Qt, QThread, Signal, Slot, QSize
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox,
)

import pyvista as pv
from pyvistaqt import QtInteractor

from config import Config
from astro_processing import get_pixel_coords, _hi_temperature_model
from data_manager import get_project
from ui_theme import BG, BG2, BG3, FG, FG2, ACC, BTN_STYLE
from ui_icons import icon, ICON_SIZE_TOOLBAR


class DummyMapWorker(QThread):
    ready = Signal(np.ndarray)

    def __init__(self, nside: int, parent=None):
        super().__init__(parent)
        self._nside = nside

    def run(self):
        ra, dec = get_pixel_coords(self._nside)
        self.ready.emit(np.array([
            _hi_temperature_model(float(r), float(d))
            for r, d in zip(ra, dec)
        ], dtype=np.float32))


class SkyViewerWidget(QWidget):
    """
    공개 API
    --------
    update_from_obs(result)   관측 완료 → 픽셀 갱신
    refresh_from_project()    프로젝트 열기 후 전체 갱신
    reset_map()               더미 지도로 초기화
    """

    _R = 50.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cfg    = Config.get()
        self._nside  = self._cfg.nside
        self._hp     = HEALPix(nside=self._nside, order='ring', frame='icrs')

        self._dummy_map:   Optional[np.ndarray] = None
        self._current_map: Optional[np.ndarray] = None
        self._fg_map:      Optional[np.ndarray] = None
        self._fg_method:   str = ''
        self._mesh:        Optional[pv.PolyData] = None
        self._actor                             = None

        self._fg_on       = False
        self._moc_on      = False
        self._gal_on      = False
        self._grid_on     = True
        self._gal_actors  : list = []
        self._grid_actors : list = []

        self._build_ui()
        self._init_scene()
        self._start_dummy_worker()

    def _build_ui(self):
        self.setStyleSheet(f'background:{BG};')
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        title = QLabel('HI 21cm Brightness Temperature Map')
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f'color:{FG};font-size:14px;font-weight:600;'
            f'padding:8px;background:{BG2};letter-spacing:2px;'
            f'border-bottom:1px solid {BG3};')
        root.addWidget(title)

        self._plotter = QtInteractor(self)
        self._plotter.set_background(BG)
        root.addWidget(self._plotter, stretch=1)

        bar = QWidget()
        bar.setStyleSheet(f'background:{BG2};border-top:1px solid {BG3};')
        hb = QHBoxLayout(bar)
        hb.setContentsMargins(12, 6, 12, 6)
        hb.setSpacing(8)

        self._status = QLabel('더미 지도 생성 중...')
        self._status.setStyleSheet(f'color:{FG2};font-size:12px;')
        hb.addWidget(self._status)
        hb.addStretch()

        def btn(label: str, slot, icon_name: str | None = None):
            b = QPushButton(label)
            b.setStyleSheet(BTN_STYLE)
            if icon_name:
                ic = icon(icon_name)
                if not ic.isNull():
                    b.setIcon(ic)
                    b.setIconSize(QSize(ICON_SIZE_TOOLBAR, ICON_SIZE_TOOLBAR))
            b.clicked.connect(slot)
            hb.addWidget(b)
            return b

        btn('초기화', self.reset_map, 'reset')
        self._fg_btn = btn('은하 전경 차감', self._toggle_foreground, 'foreground')
        self._moc_btn = btn('커버리지 표시', self._toggle_moc, 'coverage')
        btn('MOC보내기', self._export_moc, 'moc_export')
        self._gal_btn = btn('은하 격자', self._toggle_galactic, 'galactic_grid')
        self._grd_btn = btn('격자 끄기', self._toggle_grid, 'grid')

        root.addWidget(bar)

    def _init_scene(self):
        self._build_mesh()
        self._add_equatorial_grid()
        self._add_galactic_grid()
        self._add_labels()

        self._set_internal_camera()

    @staticmethod
    def _scalar_range(sky_map: np.ndarray) -> tuple[float, float]:
        """표시 중인 T_b 배열의 유한값 min/max → 컬러맵 범위 [K]."""
        f = np.asarray(sky_map, dtype=np.float64).ravel()
        f = f[np.isfinite(f)]
        if f.size == 0:
            return 0.0, 1.0
        vmin, vmax = float(f.min()), float(f.max())
        if abs(vmax - vmin) < 1e-9:
            return vmin - 0.5, vmax + 0.5
        return vmin, vmax

    def _set_scalar_clim(self, vmin: float, vmax: float) -> None:
        """메쉬·컬러바 범위를 데이터 min/max에 맞춤."""
        if self._actor is None:
            return
        mapper = self._actor.GetMapper()
        if mapper is not None:
            mapper.SetScalarRange(vmin, vmax)
            mapper.Update()
        try:
            sb = self._plotter.scalar_bars.get('T_b')
            if sb is not None:
                sb.SetTitle(f'T_b [K]  {vmin:.2f} – {vmax:.2f}')
        except (AttributeError, KeyError, TypeError):
            pass

    def _build_mesh(self, sky_map: Optional[np.ndarray] = None):
        npix = self._hp.npix
        lon, lat = self._hp.boundaries_lonlat(np.arange(npix), step=1)
        lo = lon.to_value('rad')
        la = lat.to_value('rad')
        r  = self._R

        x = r * np.cos(la) * np.cos(lo)
        y = r * np.cos(la) * np.sin(lo)
        z = r * np.sin(la)
        verts = np.column_stack([x.flatten(), y.flatten(), z.flatten()])

        faces = np.zeros(npix * 5, dtype=int)
        for i in range(npix):
            v = i * 4
            faces[i * 5:i * 5 + 5] = [4, v, v + 1, v + 2, v + 3]

        self._mesh = pv.PolyData(verts, faces).flip_faces(inplace=True)
        T = sky_map if sky_map is not None else np.zeros(npix, dtype=np.float32)
        vmin, vmax = self._scalar_range(T)
        T = self._fill_display_scalars(T)
        self._mesh.cell_data['T_b'] = T

        if self._actor:
            self._plotter.remove_actor(self._actor)
        self._actor = self._plotter.add_mesh(
            self._mesh, scalars='T_b', cmap='RdYlBu_r',
            clim=(vmin, vmax),
            show_scalar_bar=True,
            scalar_bar_args={
                'title': f'T_b [K]  {vmin:.2f} – {vmax:.2f}',
                'color': 'white',
                'vertical': True, 'position_x': 0.88,
            },
            smooth_shading=False, show_edges=False,
            ambient=1.0, diffuse=0.0, specular=0.0,
        )
        self._set_internal_camera()
        self._plotter.render()

    @staticmethod
    def _fill_display_scalars(T: np.ndarray) -> np.ndarray:
        """NaN 픽셀을 표시용으로만 최솟값으로 채움 (범위 계산은 원본 기준)."""
        out = T.copy()
        finite = np.isfinite(out)
        if np.any(finite):
            out[~finite] = float(np.nanmin(out[finite]))
        else:
            out[~finite] = 0.0
        return out

    def _add_equatorial_grid(self):
        r = self._R * 0.9995
        for lat_d in range(-75, 91, 15):
            p = np.radians(lat_d)
            t = np.linspace(0, 2 * np.pi, 180)
            pts = np.column_stack([
                r * np.cos(p) * np.cos(t),
                r * np.cos(p) * np.sin(t),
                np.full(180, r * np.sin(p)),
            ])
            a = self._plotter.add_mesh(
                pv.Spline(pts, 180), color='white', opacity=0.2, line_width=1)
            self._grid_actors.append(a)
        for lon_d in range(0, 360, 30):
            t = np.radians(lon_d)
            p = np.linspace(-np.pi / 2, np.pi / 2, 180)
            pts = np.column_stack([
                r * np.cos(p) * np.cos(t),
                r * np.cos(p) * np.sin(t),
                r * np.sin(p),
            ])
            a = self._plotter.add_mesh(
                pv.Spline(pts, 180), color='white', opacity=0.2, line_width=1)
            self._grid_actors.append(a)

    def _add_galactic_grid(self):
        r = self._R * 0.998
        for b_d in range(-75, 91, 15):
            b = np.radians(b_d)
            l_arr = np.linspace(0, 2 * np.pi, 180)
            coords = SkyCoord(
                l=l_arr * u.rad, b=np.full(180, b) * u.rad, frame='galactic')
            ic = coords.icrs
            pts = np.column_stack([
                r * np.cos(ic.dec.rad) * np.cos(ic.ra.rad),
                r * np.cos(ic.dec.rad) * np.sin(ic.ra.rad),
                r * np.sin(ic.dec.rad),
            ])
            a = self._plotter.add_mesh(
                pv.Spline(pts, 180), color='yellow', opacity=0.3, line_width=1)
            a.SetVisibility(False)
            self._gal_actors.append(a)
        for l_d in range(0, 360, 30):
            l = np.radians(l_d)
            b_arr = np.linspace(-np.pi / 2, np.pi / 2, 180)
            coords = SkyCoord(
                l=np.full(180, l) * u.rad, b=b_arr * u.rad, frame='galactic')
            ic = coords.icrs
            pts = np.column_stack([
                r * np.cos(ic.dec.rad) * np.cos(ic.ra.rad),
                r * np.cos(ic.dec.rad) * np.sin(ic.ra.rad),
                r * np.sin(ic.dec.rad),
            ])
            a = self._plotter.add_mesh(
                pv.Spline(pts, 180), color='yellow', opacity=0.3, line_width=1)
            a.SetVisibility(False)
            self._gal_actors.append(a)

    def _add_labels(self):
        r = self._R * 0.97
        for text, pos in [('N', (0, 0, r)), ('S', (0, 0, -r)),
                          ('E', (0, r, 0)), ('W', (0, -r, 0))]:
            self._plotter.add_point_labels(
                [pos], [text], font_size=18, bold=True,
                text_color='yellow', always_visible=True,
                show_points=False, shape=None)
        for ra_d in range(0, 360, 30):
            t = np.radians(ra_d)
            self._plotter.add_point_labels(
                [[r * np.cos(t), r * np.sin(t), r * 0.04]], [f'{ra_d}°'],
                font_size=9, text_color='lightblue', always_visible=True,
                show_points=False, shape=None)
        for dec_d in range(-75, 91, 15):
            if dec_d == 0:
                continue
            p = np.radians(dec_d)
            self._plotter.add_point_labels(
                [[r * np.cos(p), r * 0.02, r * np.sin(p)]], [f'{dec_d:+d}°'],
                font_size=9, text_color='lightgreen', always_visible=True,
                show_points=False, shape=None)

    def _start_dummy_worker(self):
        self._worker = DummyMapWorker(nside=self._nside)
        self._worker.ready.connect(self._on_dummy_ready)
        self._worker.start()

    @Slot(np.ndarray)
    def _on_dummy_ready(self, sky_map: np.ndarray):
        self._dummy_map   = sky_map
        self._current_map = sky_map
        self._apply_map(sky_map)
        f = sky_map[np.isfinite(sky_map)]
        self._status.setText(
            f'더미 HI 모델  T:{f.min():.1f}~{f.max():.1f} K  |  '
            f'프로젝트를 열면 실제 데이터로 갱신')

    @Slot(dict)
    def update_from_obs(self, result: dict):
        proj = get_project()
        if proj.sky_map is not None:
            self._current_map = proj.sky_map.copy()
            self._apply_map(self._current_map)
            f = self._current_map[np.isfinite(self._current_map)]
            self._status.setText(
                f'관측 {proj.obs_count}건  T:{f.min():.1f}~{f.max():.1f} K  '
                f'RA={result["ra"]:.1f}° Dec={result["dec"]:.1f}°  '
                f'l={result.get("l_deg", 0):.1f}° b={result.get("b_deg", 0):.1f}°  '
                f'v={result["v_radial_kms"]:+.1f} km/s')

    def refresh_from_project(self):
        proj = get_project()
        if not proj.is_open or proj.sky_map is None:
            return
        if proj.nside != self._nside:
            self._nside = proj.nside
            self._hp    = HEALPix(nside=self._nside, order='ring', frame='icrs')
            self._fg_map = None
            self._build_mesh()
        self._current_map = proj.sky_map.copy()
        self._apply_map(self._current_map)
        f = self._current_map[np.isfinite(self._current_map)]
        n = len(f)
        self._status.setText(
            f'프로젝트: {proj.name}  관측 {proj.obs_count}건  유효픽셀 {n}'
            + (f'  T:{f.min():.1f}~{f.max():.1f} K' if n else ''))

    def reset_map(self):
        self._fg_on = False
        self._fg_btn.setText('은하 전경 차감')
        self._moc_on = False
        self._moc_btn.setText('커버리지 표시')
        src = (self._dummy_map if self._dummy_map is not None
               else np.zeros(self._hp.npix, dtype=np.float32))
        self._current_map = src.copy()
        self._apply_map(src)
        self._status.setText('더미 HI 모델로 초기화됨.')

    def _toggle_foreground(self):
        if self._fg_map is None:
            self._status.setText('전경 모델 로딩 중...')
            try:
                from foreground_processing import get_foreground_map
                self._fg_map, self._fg_method = get_foreground_map(self._nside)
                label = 'FITS' if self._fg_method == 'fits' else '해석식'
                self._status.setText(f'전경 모델 로드 ({label}).')
            except Exception as e:
                self._status.setText(f'전경 오류: {e}')
                return

        self._fg_on = not self._fg_on
        self._fg_btn.setText(
            '전경 차감 ✓' if self._fg_on else '은하 전경 차감')

        base = get_project().sky_map if get_project().is_open else self._dummy_map
        if base is None:
            return

        if self._moc_on:
            self._moc_on = False
            self._moc_btn.setText('커버리지 표시')

        if self._fg_on:
            scale = self._cfg.fg_scale
            corrected = base.copy()
            valid = np.isfinite(base)
            corrected[valid] = base[valid] - scale * self._fg_map[valid]
            self._apply_map(corrected)
            label = 'FITS(GSM)' if self._fg_method == 'fits' else '해석식|b|'
            f = self._fg_map[np.isfinite(self._fg_map)]
            self._status.setText(
                f'은하 전경 차감 ({label})  |  '
                f'전경 T:{f.min():.1f}~{f.max():.1f} K')
        else:
            self._apply_map(base)

    def _toggle_moc(self):
        self._moc_on = not self._moc_on
        self._moc_btn.setText('커버리지 끄기' if self._moc_on else '커버리지 표시')

        from moc_manager import get_moc_manager
        proj = get_project()
        mm   = get_moc_manager(self._nside)
        if proj.is_open:
            mm.add_from_project(proj.observations)

        base = proj.sky_map if proj.is_open else self._dummy_map
        if base is None:
            return

        if self._fg_on:
            self._fg_on = False
            self._fg_btn.setText('은하 전경 차감')

        if self._moc_on:
            T = base.copy()
            unobs = ~mm.coverage_mask()
            T[unobs] = float(np.nanmin(base)) - 5.0
            self._apply_map(T)
            cov = mm.coverage_fraction() * 100
            self._status.setText(
                f'커버리지: {cov:.2f}%  '
                f'({len(mm._obs_pix)}/{mm._hp.npix} 픽셀)  |  빨강=미관측')
        else:
            self._apply_map(base)

    def _export_moc(self):
        from moc_manager import get_moc_manager
        proj = get_project()
        mm   = get_moc_manager(self._nside)
        if proj.is_open:
            mm.add_from_project(proj.observations)
        if not mm._obs_pix:
            QMessageBox.warning(self, '경고', '관측 데이터가 없습니다.')
            return
        try:
            path, _ = QFileDialog.getSaveFileName(
                self, 'MOC 저장', 'coverage.fits', 'FITS (*.fits)')
            if path:
                mm.save(path)
                QMessageBox.information(self, '완료', f'MOC 저장됨:\n{path}')
        except Exception as e:
            QMessageBox.critical(self, '오류', str(e))

    def _toggle_galactic(self):
        self._gal_on = not self._gal_on
        for a in self._gal_actors:
            a.SetVisibility(self._gal_on)
        self._gal_btn.setText('은하 격자 끄기' if self._gal_on else '은하 격자')
        self._plotter.render()

    def _toggle_grid(self):
        self._grid_on = not self._grid_on
        for a in self._grid_actors:
            a.SetVisibility(self._grid_on)
        self._grd_btn.setText('격자 켜기' if not self._grid_on else '격자 끄기')
        self._plotter.render()

    def _set_internal_camera(self):
        """시점 중심 = 구 중심 (0,0,0). 내면 HEALPix를 바라봄."""
        cam = self._plotter.camera
        cam.position    = (0.0, 0.0, 0.0)
        cam.focal_point = (0.0, 0.0, 1.0)
        cam.up          = (0.0, 1.0, 0.0)
        cam.view_angle  = 90.0

    def _apply_map(self, sky_map: np.ndarray):
        if self._mesh is None:
            self._build_mesh(sky_map)
            return
        vmin, vmax = self._scalar_range(sky_map)
        T = self._fill_display_scalars(sky_map.copy())
        self._mesh.cell_data['T_b'] = T
        self._mesh.set_active_scalars('T_b', preference='cell')
        if self._actor is None:
            self._build_mesh(sky_map)
            return
        try:
            self._mesh['T_b'] = self._mesh['T_b']
            self._plotter.update_scalars(
                'T_b', mesh=self._mesh, render=False, clim=(vmin, vmax))
        except (TypeError, AttributeError):
            try:
                self._mesh['T_b'] = self._mesh['T_b']
                self._plotter.update_scalars('T_b', mesh=self._mesh, render=False)
            except (TypeError, AttributeError):
                pass
        self._set_scalar_clim(vmin, vmax)
        self._set_internal_camera()
        self._plotter.render()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = QMainWindow()
    win.setWindowTitle('HI 21cm Sky Viewer')
    win.resize(1200, 800)
    win.setCentralWidget(SkyViewerWidget())
    win.show()
    sys.exit(app.exec())
