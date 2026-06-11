"""
galactic_map.py
은하 조감도 2D 뷰어 위젯

역할
  - 태양 위치를 원점으로 은하 평면을 내려다보는 2D 지도
  - 문헌 나선팔 참조 곡선 오버레이
  - 관측된 HI 피크를 거리 + 방향으로 점으로 표시
  - 클릭 시 해당 관측 정보 표시
  - 실시간 갱신 (obs_finished 시그널 연결)

좌표계
  원점 = 태양 위치
  Y축 = 태양 → 은하 중심 방향 (+Y = 은하 중심)
  X축 = 은하 회전 방향 (반시계)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional

import numpy as np

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QGroupBox, QSplitter, QTableWidgetItem,
)
from PySide6.QtGui import QFont

import pyqtgraph as pg

from spiral_arm import (
    analyze_observation, get_reference_spiral_arms,
    SpiralArmResult, VelocityPeak, R_SUN_KPC,
)
from data_manager import get_project

# 색상
from ui_theme import BG as _BG, FG as _FG, ACC as _ACC


_SUN  = '#f2a818'


# ═══════════════════════════════════════════════════════════
# 조감도 플롯
# ═══════════════════════════════════════════════════════════

class GalacticPlot(pg.PlotWidget):
    """
    pyqtgraph 기반 은하 조감도.
    - 참조 나선팔 곡선
    - 태양 위치 마커
    - 은하 중심 마커
    - 관측 HI 피크 점들
    """
    point_clicked = Signal(dict)   # 점 클릭 시 피크 정보

    def __init__(self, parent=None):
        super().__init__(parent, background=_BG)
        self._arm_items:  list = []
        self._peak_items: list = []
        self._all_peaks:  list = []   # 전체 피크 저장

        self._setup_plot()
        self._draw_reference_arms()
        self._draw_fixed_markers()

    def _setup_plot(self):
        self.setLabel('left',   'Y [kpc]', color=_FG)
        self.setLabel('bottom', 'X [kpc]', color=_FG)
        self.setTitle('은하 조감도 (태양 원점)', color=_FG)
        self.showGrid(x=True, y=True, alpha=0.15)
        self.setAspectLocked(True)
        self.setRange(xRange=(-15, 15), yRange=(-5, 20))
        self.addLegend(offset=(10, 10))

        # 동심원 (거리 눈금)
        for r_kpc in [2, 4, 6, 8, 10, 12]:
            theta = np.linspace(0, 2*np.pi, 200)
            self.plot(r_kpc*np.sin(theta), r_kpc*np.cos(theta),
                      pen=pg.mkPen((80,80,80,80), width=0.5))
            self.addItem(pg.TextItem(
                f'{r_kpc} kpc', color=(100,100,100),
                anchor=(0.5, 0.5),
            ) if False else pg.TextItem(''))  # 거리 눈금 텍스트는 혼잡해서 생략

        # 시선 방향 팬 (l = 0°~360°, 점선)
        for l_deg in range(0, 360, 30):
            l = np.radians(l_deg)
            d = 14.0
            self.plot([0, d*np.sin(l)], [0, d*np.cos(l)],
                      pen=pg.mkPen((60,60,90,100), width=0.5,
                                   style=Qt.PenStyle.DashLine))

    def _draw_reference_arms(self):
        arms = get_reference_spiral_arms()
        for name, info in arms.items():
            x, y = info['xy']
            color = info['color']
            item = self.plot(x, y, pen=pg.mkPen(color, width=1.5),
                             name=name)
            self._arm_items.append(item)

    def _draw_fixed_markers(self):
        # 태양
        sun = pg.ScatterPlotItem(
            [0], [0], size=12,
            pen=pg.mkPen(_SUN, width=2),
            brush=pg.mkBrush(_SUN),
            symbol='star',
        )
        self.addItem(sun)
        self.addItem(pg.TextItem('☉ 태양', color=_SUN, anchor=(0, 1)))

        # 은하 중심
        gc = pg.ScatterPlotItem(
            [0], [R_SUN_KPC], size=14,
            pen=pg.mkPen('#ff4444', width=2),
            brush=pg.mkBrush('#ff4444'),
            symbol='x',
        )
        self.addItem(gc)
        t = pg.TextItem('은하 중심', color='#ff4444', anchor=(0.5, 1))
        t.setPos(0, R_SUN_KPC)
        self.addItem(t)

    def add_peaks(self, peaks: list[VelocityPeak], color='#00ffcc'):
        """관측 HI 피크를 조감도에 추가."""
        if not peaks: return

        x_near = [p.x_near_kpc for p in peaks if np.isfinite(p.x_near_kpc)]
        y_near = [p.y_near_kpc for p in peaks if np.isfinite(p.x_near_kpc)]
        x_far  = [p.x_far_kpc  for p in peaks if np.isfinite(p.x_far_kpc)]
        y_far  = [p.y_far_kpc  for p in peaks if np.isfinite(p.x_far_kpc)]

        if x_near:
            item = pg.ScatterPlotItem(
                x_near, y_near, size=8,
                pen=pg.mkPen(color, width=1),
                brush=pg.mkBrush(color + '99'),
                symbol='o',
            )
            self.addItem(item)
            self._peak_items.append(item)

        if x_far:
            item = pg.ScatterPlotItem(
                x_far, y_far, size=6,
                pen=pg.mkPen(color, width=1),
                brush=pg.mkBrush(color + '44'),
                symbol='t',   # 삼각형 = 원거리 (모호성)
            )
            self.addItem(item)
            self._peak_items.append(item)

        self._all_peaks.extend(peaks)

    def clear_peaks(self):
        for item in self._peak_items:
            self.removeItem(item)
        self._peak_items.clear()
        self._all_peaks.clear()

    def toggle_arms(self, visible: bool):
        for item in self._arm_items:
            item.setVisible(visible)

    def load_from_project(self):
        """ProjectManager의 observations에서 나선팔 분석 재실행."""
        self.clear_peaks()
        proj = get_project()
        if not proj.is_open: return

        # 저장된 peaks 불러오기 (있으면), 없으면 재계산
        for obs in proj.observations:
            saved_peaks = obs.get('spiral_peaks', [])
            if saved_peaks:
                peaks = [VelocityPeak(**p) for p in saved_peaks]
                self.add_peaks(peaks)


# ═══════════════════════════════════════════════════════════
# 피크 목록 패널
# ═══════════════════════════════════════════════════════════

class PeakListPanel(QWidget):
    """감지된 피크 목록 표시."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self); lay.setContentsMargins(6,6,6,6); lay.setSpacing(4)

        title = QLabel('감지된 HI 피크')
        title.setStyleSheet(f'color:{_ACC}; font-weight:bold; font-size:12px;')
        lay.addWidget(title)

        self._table = pg.TableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ['l [°]', 'v_LSR [km/s]', 'T_b [K]', 'd_near [kpc]', 'd_far [kpc]', 'R [kpc]'])
        self._table.setStyleSheet(
            f'background:{_BG}; color:{_FG}; gridline-color:#1a1a3a;')
        lay.addWidget(self._table)

        self.setStyleSheet(f'background:{_BG}; color:{_FG};')

    def update_peaks(self, arm_result: SpiralArmResult):
        peaks = arm_result.peaks
        self._table.setRowCount(len(peaks))
        for i, p in enumerate(peaks):
            from spiral_arm import velocity_to_distance
            dist = velocity_to_distance(p.v_lsr_kms, p.l_deg, p.b_deg)
            R    = dist.get('R_kpc', np.nan)
            for j, val in enumerate([
                f'{p.l_deg:.1f}',
                f'{p.v_lsr_kms:+.1f}',
                f'{p.T_b_peak:.1f}',
                f'{p.d_near_kpc:.2f}' if np.isfinite(p.d_near_kpc) else '—',
                f'{p.d_far_kpc:.2f}'  if np.isfinite(p.d_far_kpc)  else '—',
                f'{R:.2f}'            if np.isfinite(R)             else '—',
            ]):
                self._table.setItem(i, j, QTableWidgetItem(val))

    def clear(self):
        self._table.setRowCount(0)


# ═══════════════════════════════════════════════════════════
# 메인 위젯
# ═══════════════════════════════════════════════════════════

class GalacticMapWidget(QWidget):
    """
    은하 조감도 + 피크 목록 통합 위젯.

    공개 인터페이스
    ---------------
    update_from_obs(result)   obs_finished 수신 → 피크 감지 + 지도 갱신
    refresh_from_project()    프로젝트 열기 후 전체 갱신
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.setStyleSheet(f'background:{_BG}; color:{_FG};')

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # 제목
        title = QLabel('나선팔 구조 분석  —  HI 21cm 운동학적 거리')
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f'color:#cce8ff; font-size:14px; font-weight:600;'
            f'padding:6px; background:#00000f; letter-spacing:2px;')
        root.addWidget(title)

        # 메인 영역: 지도(좌) + 피크 목록(우)
        splitter = QSplitter(Qt.Horizontal)

        self._plot       = GalacticPlot()
        self._peak_panel = PeakListPanel()
        splitter.addWidget(self._plot)
        splitter.addWidget(self._peak_panel)
        splitter.setSizes([750, 300])
        root.addWidget(splitter, stretch=1)

        # 하단 컨트롤
        bar = QWidget(); bar.setStyleSheet('background:#00000f;')
        hb  = QHBoxLayout(bar); hb.setContentsMargins(12,4,12,4); hb.setSpacing(8)

        self._status = QLabel('관측 데이터 없음')
        self._status.setStyleSheet('color:#7aaccc; font-size:11px;')
        hb.addWidget(self._status); hb.addStretch()

        btn_s = ('background:#0f3460; color:#cce8ff; border:none;'
                 'border-radius:3px; padding:3px 9px; font-size:11px;')

        self._arm_chk = QCheckBox('참조 나선팔'); self._arm_chk.setChecked(True)
        self._arm_chk.setStyleSheet(f'color:{_FG};')
        self._arm_chk.toggled.connect(self._plot.toggle_arms)
        hb.addWidget(self._arm_chk)

        self._near_chk = QCheckBox('근거리 모호성 표시'); self._near_chk.setChecked(True)
        self._near_chk.setStyleSheet(f'color:{_FG};')
        hb.addWidget(self._near_chk)

        clear_btn = QPushButton('초기화'); clear_btn.setStyleSheet(btn_s)
        clear_btn.clicked.connect(self._clear)
        hb.addWidget(clear_btn)

        root.addWidget(bar)

    # ── 공개 메서드 ──────────────────────────────────────────

    @Slot(dict)
    def update_from_obs(self, result: dict):
        """obs_finished 수신 → 나선팔 분석 → 지도 갱신."""
        arm_result = analyze_observation(result)

        # xy 좌표가 유효한 피크만 추림 (nan이면 조감도에 찍을 수 없음)
        plottable = [
            p for p in arm_result.peaks
            if np.isfinite(p.x_near_kpc) or np.isfinite(p.x_far_kpc)
        ]

        if arm_result.peaks:
            self._peak_panel.update_peaks(arm_result)   # 테이블은 항상 갱신
            if plottable:
                self._plot.add_peaks(plottable)
                self._status.setText(
                    f'l={arm_result.l_deg:.1f}°  b={arm_result.b_deg:.1f}°  '
                    f'피크 {len(arm_result.peaks)}개 감지 (지도 {len(plottable)}개)  '
                    f'| ● 근거리  ▲ 원거리(모호성)')
            else:
                self._status.setText(
                    f'l={arm_result.l_deg:.1f}°  b={arm_result.b_deg:.1f}°  '
                    f'피크 {len(arm_result.peaks)}개 감지 — 이 방향은 운동학적 거리 계산 불가 '
                    f'(은하 중심/반중심 방향 또는 고위도)')
        else:
            self._status.setText(
                f'l={arm_result.l_deg:.1f}°  b={arm_result.b_deg:.1f}°  '
                f'유의미한 피크 없음')

        # 프로젝트에 피크 저장
        proj = get_project()
        if proj.is_open and proj.observations:
            last = proj.observations[-1]
            last['spiral_peaks'] = [
                {k: (float(v) if isinstance(v, (float, np.floating)) else
                     bool(v)  if isinstance(v, (bool, np.bool_)) else v)
                 for k, v in p.__dict__.items()}
                for p in arm_result.peaks
            ]
            proj.save()

    def refresh_from_project(self):
        self._plot.load_from_project()
        proj = get_project()
        if proj.is_open:
            total_peaks = sum(
                len(obs.get('spiral_peaks', [])) for obs in proj.observations)
            self._status.setText(
                f'프로젝트: {proj.name}  '
                f'관측 {proj.obs_count}건  피크 {total_peaks}개 로드')

    def _clear(self):
        self._plot.clear_peaks()
        self._peak_panel.clear()
        self._status.setText('초기화됨.')


# ═══════════════════════════════════════════════════════════
# 단독 실행
# ═══════════════════════════════════════════════════════════

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = QMainWindow()
    win.setWindowTitle('은하 조감도 — 테스트')
    win.resize(1200, 750)
    win.setCentralWidget(GalacticMapWidget())
    win.show()
    sys.exit(app.exec())