"""
main_app.py
전파망원경 소프트웨어 — 진입점

실행: python main_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QSplitter, QTabWidget,
    QFileDialog, QMessageBox, QInputDialog,
    QLabel, QStatusBar,
)
from PySide6.QtGui import QAction

from old_versions.at_april_second.config import Config
from old_versions.at_april_second.ui_theme import APP_STYLESHEET, BG, FG, BG3
from old_versions.at_april_second.data_manager import get_project
from old_versions.at_april_second.spectrum_widget import SpectrumWidget
from old_versions.at_april_second.sky_viewer import SkyViewerWidget
from old_versions.at_april_second.galactic_map import GalacticMapWidget

_TAB_STYLE = f"""
QTabWidget::pane {{
    border: 1px solid {BG3};
    background: {BG};
}}
QTabBar::tab {{
    background: {BG};
    color: {FG};
    padding: 7px 20px;
    border: 1px solid {BG3};
    border-bottom: none;
    border-radius: 4px 4px 0 0;
    font-size: 13px;
}}
QTabBar::tab:selected {{
    background: #e0faf4;
    color: #008f77;
    font-weight: 600;
}}
QTabBar::tab:hover {{
    background: #f0faf7;
}}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._cfg  = Config.get()
        self._proj = get_project()
        self._build_ui()
        self._build_menu()
        self._connect()
        self.setWindowTitle('HI 21cm 전파망원경 소프트웨어')
        self.resize(1600, 900)
        self._apply_korean_design_theme()

    # ── UI ──────────────────────────────────────────────────

    def _build_ui(self):
        # VTK(OpenGL) 먼저 초기화한 뒤 pyqtgraph 위젯 생성 (컨텍스트 충돌 방지)
        self._viewer  = SkyViewerWidget()
        self._galmap  = GalacticMapWidget()
        self._spectrum = SpectrumWidget()

        # 오른쪽: 탭
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(_TAB_STYLE)
        self._tabs.addTab(self._viewer,  '🌌  3D 전천 히트맵')
        self._tabs.addTab(self._galmap,  '🌀  은하 조감도 / 나선팔')

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._spectrum)
        splitter.addWidget(self._tabs)
        splitter.setSizes([580, 1020])
        self.setCentralWidget(splitter)

        # 상태 바
        self._statusbar  = QStatusBar()
        self._status_lbl = QLabel('프로젝트를 열거나 새로 만드세요.  (파일 → 새 프로젝트 / 열기)')
        self._statusbar.addWidget(self._status_lbl)
        self.setStatusBar(self._statusbar)

    def _build_menu(self):
        mb = self.menuBar()

        # ── 파일 메뉴
        file_m = mb.addMenu('파일')

        act_new = QAction('새 프로젝트', self)
        act_new.setShortcut('Ctrl+N')
        act_new.triggered.connect(self._new_project)
        file_m.addAction(act_new)

        act_open = QAction('프로젝트 열기', self)
        act_open.setShortcut('Ctrl+O')
        act_open.triggered.connect(self._open_project)
        file_m.addAction(act_open)

        file_m.addSeparator()

        act_fits = QAction('FITS 내보내기', self)
        act_fits.triggered.connect(self._export_fits)
        file_m.addAction(act_fits)

        file_m.addSeparator()

        act_quit = QAction('종료', self)
        act_quit.setShortcut('Ctrl+Q')
        act_quit.triggered.connect(self.close)
        file_m.addAction(act_quit)

        # ── 설정 메뉴
        cfg_m = mb.addMenu('설정')

        act_tsys = QAction('T_sys 설정', self)
        act_tsys.triggered.connect(self._set_tsys)
        cfg_m.addAction(act_tsys)

        act_nside = QAction('nside 설정', self)
        act_nside.triggered.connect(self._set_nside)
        cfg_m.addAction(act_nside)

    def _connect(self):
        # 스펙트럼 분석 완료 → 뷰어 갱신
        self._spectrum.obs_finished.connect(self._viewer.update_from_obs)
        # 스펙트럼 분석 완료 → 은하 조감도 갱신
        self._spectrum.obs_finished.connect(self._galmap.update_from_obs)
        # 스펙트럼 분석 완료 → 상태 바 갱신
        self._spectrum.obs_finished.connect(self._on_obs_done)

    # ── 프로젝트 핸들러 ──────────────────────────────────────

    def _new_project(self):
        name, ok = QInputDialog.getText(self, '새 프로젝트', '프로젝트 이름:')
        if not ok or not name.strip():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, '프로젝트 저장 위치', name.strip() + '.json',
            'RT 프로젝트 (*.json)')
        if not path:
            return
        self._proj.create(path, name=name.strip())
        self._update_title()
        self._viewer.refresh_from_project()
        self._galmap.refresh_from_project()
        self._status_lbl.setText(f'새 프로젝트 생성: {Path(path).name}')

    def _open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, '프로젝트 열기', '',
            'RT 프로젝트 (*.json);;모든 파일 (*)')
        if not path:
            return
        try:
            self._proj.open(path)
        except Exception as e:
            QMessageBox.critical(self, '오류', f'프로젝트 열기 실패:\n{e}')
            return
        self._update_title()
        self._viewer.refresh_from_project()
        self._galmap.refresh_from_project()
        self._status_lbl.setText(
            f'프로젝트 열림: {Path(path).name}  |  '
            f'관측 {self._proj.obs_count}건 로드'
        )

    def _export_fits(self):
        if not self._proj.is_open:
            QMessageBox.warning(self, '경고', '열린 프로젝트가 없습니다.')
            return
        path, _ = QFileDialog.getSaveFileName(
            self, 'FITS 내보내기', self._proj.name + '.fits',
            'FITS 파일 (*.fits)')
        if not path:
            return
        try:
            out = self._proj.export_fits(path)
            QMessageBox.information(self, '완료', f'저장 완료:\n{out}')
        except Exception as e:
            QMessageBox.critical(self, '오류', str(e))

    # ── 설정 핸들러 ──────────────────────────────────────────

    def _set_tsys(self):
        val, ok = QInputDialog.getDouble(
            self, 'T_sys 설정', '시스템 잡음 온도 [K]:',
            value=self._cfg.T_sys, min=0.0, max=10000.0, decimals=1)
        if ok:
            self._cfg.T_sys = val
            self._cfg.save()
            self._status_lbl.setText(f'T_sys = {val} K  (저장됨)')

    def _set_nside(self):
        val, ok = QInputDialog.getItem(
            self, 'nside 설정', 'HEALPix nside:',
            ['8','16','32','64','128'], editable=False,
            current=['8','16','32','64','128'].index(str(self._cfg.nside))
                if str(self._cfg.nside) in ['8','16','32','64','128'] else 2)
        if ok:
            self._cfg.nside = int(val)
            self._cfg.save()
            self._status_lbl.setText(f'nside = {val}  (저장됨, 다음 프로젝트부터 적용)')

    # ── 슬롯 ────────────────────────────────────────────────

    def _on_obs_done(self, result: dict):
        if self._proj.is_open:
            self._status_lbl.setText(
                f'{self._proj.name}  |  관측 {self._proj.obs_count}건  |  '
                f'T_sky={result["T_brightness"]:.3f} K  '
                f'v={result["v_radial_kms"]:+.2f} km/s  → 저장됨'
            )

    def _apply_korean_design_theme(self):
        self.setStyleSheet(APP_STYLESHEET)

    def _update_title(self):
        self.setWindowTitle(
            f'HI 21cm 전파망원경  —  {self._proj.name}')


def main():
    from PySide6.QtGui import QSurfaceFormat

    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setVersion(3, 2)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
