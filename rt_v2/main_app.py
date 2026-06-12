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

from config import Config
from ui_theme import APP_STYLESHEET, BG, FG, BG3
from ui_icons import icon
from data_manager import get_project
from spectrum_widget import SpectrumWidget
from sky_viewer import SkyViewerWidget
from galactic_map import GalacticMapWidget

APP_NAME    = 'HI 21cm 전파망원경 소프트웨어'
APP_VERSION = '1.0'

# 크레딧
CREDIT_SCHOOL = 'SASA · 10기'
CREDIT_TEAM   = '팀 RWA'
CREDIT_DEVS   = 'TETO-IS-KAWAI'

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
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icon('app'))
        self.resize(1700, 950)
        self.setStyleSheet(APP_STYLESHEET)

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
        splitter.setSizes([580, 1120])
        self.setCentralWidget(splitter)

        # 상태 바
        self._statusbar  = QStatusBar()
        self._status_lbl = QLabel('프로젝트를 열거나 새로 만드세요.  (파일 → 새 프로젝트 / 열기)')
        self._statusbar.addWidget(self._status_lbl)
        self.setStatusBar(self._statusbar)

    def _build_menu(self):
        mb = self.menuBar()

        # ── 파일
        fm = mb.addMenu('파일')
        for label, shortcut, slot, ic in [
            ('새 프로젝트',   'Ctrl+N', self._new_project,  'new_project'),
            ('프로젝트 열기', 'Ctrl+O', self._open_project, 'open'),
            (None, None, None, None),
            ('FITS 내보내기', '',       self._export_fits,  ''),
            (None, None, None, None),
            ('종료',          'Ctrl+Q', self.close,         'quit'),
        ]:
            if label is None:
                fm.addSeparator(); continue
            a = QAction(icon(ic), label, self) if ic else QAction(label, self)
            if shortcut: a.setShortcut(shortcut)
            a.triggered.connect(slot)
            fm.addAction(a)

        # ── 설정
        sm = mb.addMenu('설정')
        for label, slot in [
            ('T_sys 설정', self._set_tsys),
            ('nside 설정', self._set_nside),
        ]:
            a = QAction(label, self); a.triggered.connect(slot); sm.addAction(a)

        # ── 보기
        vm = mb.addMenu('보기')
        a1 = QAction('3D 전천 히트맵', self)
        a1.triggered.connect(lambda: self._tabs.setCurrentIndex(0))
        a2 = QAction('은하 조감도 / 나선팔', self)
        a2.triggered.connect(lambda: self._tabs.setCurrentIndex(1))
        vm.addAction(a1); vm.addAction(a2)

        # ── 도움말
        hm = mb.addMenu('도움말')
        about = QAction(icon('app'), '정보', self)
        about.triggered.connect(self._about)
        hm.addAction(about)

    def _connect(self):
        self._spectrum.obs_finished.connect(self._viewer.update_from_obs)
        self._spectrum.obs_finished.connect(self._galmap.update_from_obs)
        self._spectrum.obs_finished.connect(self._on_obs_done)

    # ── 프로젝트 ─────────────────────────────────────────────

    def _new_project(self):
        name, ok = QInputDialog.getText(self, '새 프로젝트', '프로젝트 이름:')
        if not ok or not name.strip(): return
        default = str(self._cfg.projects_dir_path / (name.strip() + '.json'))
        path, _ = QFileDialog.getSaveFileName(
            self, '저장 위치', default, 'RT 프로젝트 (*.json)')
        if not path: return
        self._proj.create(path, name=name.strip())
        self._update_title()
        self._viewer.refresh_from_project()
        self._galmap.refresh_from_project()
        self._status_lbl.setText(f'새 프로젝트: {Path(path).name}')

    def _open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, '프로젝트 열기', str(self._cfg.projects_dir_path),
            'RT 프로젝트 (*.json);;모든 파일 (*)')
        if not path: return
        try:
            self._proj.open(path)
        except Exception as e:
            QMessageBox.critical(self, '오류', f'열기 실패:\n{e}'); return
        self._update_title()
        self._viewer.refresh_from_project()
        self._galmap.refresh_from_project()
        self._status_lbl.setText(
            f'{Path(path).name}  |  관측 {self._proj.obs_count}건 로드')

    def _export_fits(self):
        if not self._proj.is_open:
            QMessageBox.warning(self, '경고', '열린 프로젝트가 없습니다.'); return
        path, _ = QFileDialog.getSaveFileName(
            self, 'FITS 내보내기', self._proj.name + '.fits', 'FITS (*.fits)')
        if not path: return
        try:
            out = self._proj.export_fits(path)
            QMessageBox.information(self, '완료', f'저장:\n{out}')
        except Exception as e:
            QMessageBox.critical(self, '오류', str(e))

    # ── 설정 ────────────────────────────────────────────────

    def _set_tsys(self):
        val, ok = QInputDialog.getDouble(
            self, 'T_sys', '시스템 잡음 온도 [K]:',
            value=self._cfg.T_sys, min=0, max=10000, decimals=1)
        if ok:
            self._cfg.T_sys = val; self._cfg.save()
            self._status_lbl.setText(f'T_sys = {val} K')

    def _set_nside(self):
        opts = ['8','16','32','64','128']
        cur  = opts.index(str(self._cfg.nside)) if str(self._cfg.nside) in opts else 2
        val, ok = QInputDialog.getItem(self, 'nside', 'HEALPix nside:', opts,
                                        current=cur, editable=False)
        if ok:
            self._cfg.nside = int(val); self._cfg.save()
            self._status_lbl.setText(f'nside = {val}  (다음 프로젝트부터 적용)')

    # ── 슬롯 ────────────────────────────────────────────────

    def _on_obs_done(self, result: dict):
        if self._proj.is_open:
            self._status_lbl.setText(
                f'{self._proj.name}  |  관측 {self._proj.obs_count}건  |  '
                f'T_sky={result["T_brightness"]:.3f} K  '
                f'v={result["v_radial_kms"]:+.2f} km/s  '
                f'l={result.get("l_deg", 0):.1f}°  '
                f'b={result.get("b_deg", 0):.1f}°  → 저장됨'
            )

    def _update_title(self):
        self.setWindowTitle(f'HI 21cm 전파망원경  —  {self._proj.name}')

    def _about(self):
        box = QMessageBox(self)
        box.setWindowTitle('정보')
        box.setIconPixmap(icon('app').pixmap(64, 64))
        box.setTextFormat(Qt.RichText)
        box.setText(
            f"<h3 style='margin:0'>{APP_NAME}</h3>"
            f"<p style='color:#666;margin:2px 0 10px'>v{APP_VERSION}</p>"
            "<p>SDR로 수신한 HI 21cm 수소선을 처리하여 도플러 보정·밝기온도"
            "<br>환산을 거쳐 우리 은하 나선팔을 시각화하는 소프트웨어입니다.</p>"
            "<hr>"
            f"<p><b>{CREDIT_SCHOOL} · {CREDIT_TEAM}</b><br>"
            f"코드 작성 &nbsp; {CREDIT_DEVS}</p>"
            "<p style='color:#666'>© 2026 Team RWA · MIT License</p>"
            "<p style='color:#888;font-size:11px'>Built with "
            "PySide6 · pyqtgraph · PyVista · Astropy · astropy-healpix · NumPy · SciPy</p>"
        )
        box.exec()


def main():
    from PySide6.QtGui import QSurfaceFormat

    # Windows 작업표시줄에서 python.exe 가 아닌 앱 고유 아이콘(app.png)으로 표시되도록
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                'rwa.hi21cm.telescope')
        except Exception:
            pass

    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setVersion(3, 2)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setWindowIcon(icon('app'))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
