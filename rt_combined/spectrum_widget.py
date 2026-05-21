"""
spectrum_widget.py
PySide6 스펙트럼 분석기 위젯
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from PySide6.QtCore import Qt, QThread, Signal, Slot, QSize
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog,
    QGroupBox, QComboBox,
)
from PySide6.QtGui import QFont
import pyqtgraph as pg

# PyVista(VTK)와 OpenGL 컨텍스트 충돌 방지
pg.setConfigOptions(useOpenGL=False)

from config import Config
from astro_processing import process_observation, HI_FREQ_HZ
from data_manager import get_project
from ui_theme import BG, BG2, BG3, FG, ACC, OK, ERR, WARN
from ui_icons import icon, ICON_SIZE_TOOLBAR

_BG, _BG2, _BG3, _FG = BG, BG2, BG3, FG
_ACC, _OK, _ERR, _WARN = ACC, OK, ERR, WARN
_MONO = QFont('Consolas', 9)


# ── 백그라운드 처리 스레드 ────────────────────────────────────

class SpectrumWorker(QThread):
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, params: dict, parent=None):
        super().__init__(parent)
        self._params = params

    def run(self):
        try:
            self.finished.emit(process_observation(**self._params))
        except Exception as e:
            self.error.emit(str(e))


# ── 관측 파라미터 입력 패널 ────────────────────────────────────

class ObsParamPanel(QGroupBox):
    run_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__('관측 파라미터', parent)
        self._cfg      = Config.get()
        self._bin_path : Optional[str] = None
        self._build_ui()
        self._style()

    def _build_ui(self):
        g = QGridLayout(self)
        g.setSpacing(6)

        def lbl(t):
            l = QLabel(t); l.setFont(_MONO); return l
        def edt(ph, val=''):
            e = QLineEdit(val); e.setPlaceholderText(ph); e.setFont(_MONO); return e

        self._ra  = edt('예: 266.4', '266.4');  g.addWidget(lbl('RA [deg]'), 0,0); g.addWidget(self._ra,  0,1)
        self._dec = edt('예: -28.9', '-28.9');   g.addWidget(lbl('Dec [deg]'),1,0); g.addWidget(self._dec, 1,1)

        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        self._time = edt('YYYY-MM-DDTHH:MM:SS', now)
        now_btn = QPushButton('현재'); now_btn.setFixedWidth(50)
        now_btn.clicked.connect(lambda: self._time.setText(
            datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')))
        row = QHBoxLayout(); row.addWidget(self._time); row.addWidget(now_btn)
        g.addWidget(lbl('관측 시각 (UTC)'), 2,0); g.addLayout(row, 2,1)

        self._mode = QComboBox()
        self._mode.addItems(['더미 데이터', '.bin 파일'])
        self._mode.currentIndexChanged.connect(lambda i: self._file_row.setVisible(i==1))
        g.addWidget(lbl('데이터 소스'), 3,0); g.addWidget(self._mode, 3,1)

        self._file_row = QWidget()
        fl = QHBoxLayout(self._file_row); fl.setContentsMargins(0,0,0,0)
        self._file_lbl = QLabel('(파일 없음)'); self._file_lbl.setFont(_MONO)
        self._file_lbl.setStyleSheet(f'color:{_WARN}')
        pick = QPushButton('파일 선택'); pick.clicked.connect(self._pick)
        fl.addWidget(self._file_lbl, 1); fl.addWidget(pick)
        g.addWidget(self._file_row, 4,0,1,2); self._file_row.setVisible(False)

        self._method = QComboBox(); self._method.addItems(['median','mean','peak'])
        g.addWidget(lbl('T_b 대푯값'), 5,0); g.addWidget(self._method, 5,1)

        self._run = QPushButton('▶  분석 실행')
        self._run.setFixedHeight(36)
        _ric = icon('run')
        if not _ric.isNull():
            self._run.setIcon(_ric)
            self._run.setIconSize(QSize(ICON_SIZE_TOOLBAR, ICON_SIZE_TOOLBAR))
        self._run.clicked.connect(self._emit)
        g.addWidget(self._run, 6, 0, 1, 2)

    def _style(self):
        base = f'''
            QGroupBox{{
                color: {_FG};
                border: 1px solid {_BG3};
                border-radius: 12px;
                margin-top: 8px;
                padding-top: 12px;
                background-color: {_BG2};
            }}
            QGroupBox::title{{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: {_FG};
                font-weight: 500;
            }}
            QLineEdit{{
                background-color: {_BG};
                color: {_FG};
                border: 1.5px solid {_BG3};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus{{
                border: 1.5px solid {_ACC};
                background-color: {_BG2};
            }}
            QComboBox{{
                background-color: {_BG};
                color: {_FG};
                border: 1.5px solid {_BG3};
                border-radius: 6px;
                padding: 6px 12px;
            }}
            QComboBox:focus{{
                border: 1.5px solid {_ACC};
            }}
            QComboBox QAbstractItemView{{
                background-color: {_BG2};
                color: {_FG};
                border: 1px solid {_BG3};
            }}
            QPushButton{{
                background-color: {_BG3};
                color: {_FG};
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton:hover{{
                background-color: {_ACC};
                color: {_BG};
            }}
            QPushButton:pressed{{
                background-color: {_OK};
            }}
        '''
        self.setStyleSheet(base)
        self._run.setStyleSheet(
            f'QPushButton{{'
            f'background-color: {_ACC};'
            f'color: {_BG};'
            f'font-weight: bold;'
            f'padding: 10px 20px;'
            f'font-size: 14px;'
            f'}}'
            f'QPushButton:hover{{'
            f'background-color: {_OK};'
            f'color: {_BG2};'
            f'}}'
        )

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(
            self, '.bin 파일 선택', str(self._cfg.data_dir_path),
            'SDR 파일 (*.bin);;모든 파일 (*)')
        if path:
            self._bin_path = path
            self._file_lbl.setText(Path(path).name)
            self._file_lbl.setStyleSheet(f'color:{_OK}')

    def _emit(self):
        try:
            ra  = float(self._ra.text())
            dec = float(self._dec.text())
        except ValueError:
            return
        obs_time = self._time.text().strip() or \
                   datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        cfg = self._cfg
        self.run_requested.emit(dict(
            ra_deg=ra, dec_deg=dec, obs_time=obs_time,
            obs_lat=cfg.obs_lat, obs_lon=cfg.obs_lon,
            obs_height_m=cfg.obs_height_m,
            bin_filepath=self._bin_path if self._mode.currentIndex()==1 else None,
            center_freq_hz=cfg.center_freq_hz,
            sample_rate=cfg.sample_rate, nfft=cfg.nfft,
            T_sys=cfg.T_sys, G_sys=cfg.G_sys,
            temp_method=self._method.currentText(),
        ))

    def set_running(self, v: bool):
        self._run.setEnabled(not v)
        self._run.setText('⏳ 처리 중...' if v else '▶  분석 실행')

    @property
    def current_bin_path(self) -> Optional[str]:
        return self._bin_path if self._mode.currentIndex()==1 else None


# ── 결과 패널 ──────────────────────────────────────────────────

class ResultPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__('결과', parent)
        g = QGridLayout(self); g.setSpacing(4)

        def key(t):
            l=QLabel(t); l.setFont(_MONO); return l
        def val():
            l=QLabel('—'); l.setFont(QFont('Consolas',11))
            l.setStyleSheet(f'color:{_ACC}'); l.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
            return l

        self._v   = val(); self._ts = val(); self._tr = val()
        self._lb  = val(); self._vt = val(); self._dist = val()
        self._st  = QLabel('대기 중'); self._st.setFont(_MONO)
        self._st.setStyleSheet(f'color:{_WARN}')

        g.addWidget(key('v_LSR'),   0,0); g.addWidget(self._v,  0,1); g.addWidget(key('[km/s]'),0,2)
        g.addWidget(key('T_sky'),   1,0); g.addWidget(self._ts, 1,1); g.addWidget(key('[K]'),   1,2)
        g.addWidget(key('T_b_raw'), 2,0); g.addWidget(self._tr, 2,1); g.addWidget(key('[K]'),   2,2)
        g.addWidget(key('(l, b)'),  3,0); g.addWidget(self._lb, 3,1,1,2)
        g.addWidget(key('v_tan'),   4,0); g.addWidget(self._vt, 4,1); g.addWidget(key('[km/s]'),4,2)
        g.addWidget(key('d_kin'),   5,0); g.addWidget(self._dist,5,1); g.addWidget(key('[kpc]'),5,2)
        g.addWidget(self._st, 6,0,1,3)

        self.setStyleSheet(
            f'QGroupBox{{'
            f'color: {_FG};'
            f'border: 1px solid {_BG3};'
            f'border-radius: 12px;'
            f'margin-top: 8px;'
            f'padding-top: 12px;'
            f'background-color: {_BG2};'
            f'}}'
            f'QGroupBox::title{{'
            f'subcontrol-origin: margin;'
            f'left: 10px;'
            f'padding: 0 6px;'
            f'color: {_FG};'
            f'font-weight: 500;'
            f'}}')

    def update(self, r: dict):
        from astro_processing import galactocentric_velocity
        self._v.setText(f'{r["v_radial_kms"]:+.3f}')
        self._ts.setText(f'{r["T_brightness"]:.4f}')
        self._tr.setText(f'{r["T_b_raw"]:.4f}')
        l = r.get('l_deg', float('nan'))
        b = r.get('b_deg', float('nan'))
        self._lb.setText(f'l={l:.1f}°  b={b:.1f}°')
        try:
            gc = galactocentric_velocity(r['ra'], r['dec'], r['v_radial_kms'])
            self._vt.setText(f'{gc["v_tangent_kms"]:+.2f}')
            dn = gc['kinematic_distance_near_kpc']
            df = gc['kinematic_distance_far_kpc']
            self._dist.setText(
                f'{dn:.2f} / {df:.2f}' if (dn == dn and df == df) else '—')
        except Exception:
            self._vt.setText('—'); self._dist.setText('—')
        ok = r['success']
        self._st.setText('성공 ✓' if ok else '실패')
        self._st.setStyleSheet(f'color:{_OK if ok else _ERR}')

    def set_error(self, msg):
        self._st.setText(f'오류: {msg[:60]}'); self._st.setStyleSheet(f'color:{_ERR}')

    def set_running(self):
        self._st.setText('계산 중...'); self._st.setStyleSheet(f'color:{_WARN}')


# ── 플롯 영역 ──────────────────────────────────────────────────

class SpectrumPlotArea(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        pg.setConfigOption('background', _BG2)
        pg.setConfigOption('foreground', _FG)
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(4)

        # 파워 스펙트럼
        self._pw = pg.PlotWidget(title='파워 스펙트럼 (도플러 보정 후)')
        self._pw.setLabel('bottom','주파수',units='GHz')
        self._pw.setLabel('left','파워',units='dB')
        self._pw.showGrid(x=True,y=True,alpha=0.2)
        self._pc = self._pw.plot(pen=pg.mkPen(_ACC,width=1))
        self._pw.addItem(pg.InfiniteLine(
            pos=HI_FREQ_HZ/1e9, angle=90,
            pen=pg.mkPen(_ERR,width=1,style=Qt.DashLine),
            label=f'HI {HI_FREQ_HZ/1e9:.5f} GHz',
            labelOpts={'color':_ERR,'position':0.95}))
        lay.addWidget(self._pw)

        # 밝기온도
        self._tb = pg.PlotWidget(title='밝기온도 스펙트럼 (레일리-진스)')
        self._tb.setLabel('bottom','주파수',units='GHz')
        self._tb.setLabel('left','T_b',units='K')
        self._tb.showGrid(x=True,y=True,alpha=0.2)
        self._tc  = self._tb.plot(pen=pg.mkPen('#ff6b6b',width=1))
        self._tsl = pg.InfiniteLine(angle=0,pen=pg.mkPen(_OK,width=1.5,style=Qt.DashLine),
                                    label='T_sky',labelOpts={'color':_OK,'position':0.9})
        self._trl = pg.InfiniteLine(angle=0,pen=pg.mkPen(_WARN,width=1,style=Qt.DashLine),
                                    label='T_b_raw',labelOpts={'color':_WARN,'position':0.7})
        self._tb.addItem(self._tsl); self._tb.addItem(self._trl)
        lay.addWidget(self._tb)

    def update_plots(self, r: dict):
        mask = r['freqs_corrected'] > 0
        fg   = r['freqs_corrected'][mask] / 1e9
        self._pc.setData(fg, 10*np.log10(r['power'][mask]+1e-30))
        self._tc.setData(fg, r['T_b_spectrum'])
        self._tsl.setValue(r['T_brightness'])
        self._trl.setValue(r['T_b_raw'])
        self._tsl.label.setFormat(f'T_sky = {r["T_brightness"]:.3f} K')
        self._trl.label.setFormat(f'T_b_raw = {r["T_b_raw"]:.3f} K')

    def clear_plots(self):
        self._pc.setData([],[]); self._tc.setData([],[])


# ── 메인 위젯 ──────────────────────────────────────────────────

class SpectrumWidget(QWidget):
    """
    스펙트럼 분석기 위젯.
    obs_finished: 관측 완료 시 result dict 전달 (sky_viewer 연결용).
    """
    obs_finished = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: Optional[SpectrumWorker] = None
        self._last_params: dict = {}
        lay = QHBoxLayout(self); lay.setSpacing(8); lay.setContentsMargins(8,8,8,8)

        left = QVBoxLayout(); left.setSpacing(8)
        self._param  = ObsParamPanel()
        self._result = ResultPanel()
        left.addWidget(self._param); left.addWidget(self._result); left.addStretch()
        lw = QWidget(); lw.setLayout(left); lw.setFixedWidth(285)
        lay.addWidget(lw)

        self._plots = SpectrumPlotArea()
        lay.addWidget(self._plots, 1)

        self._param.run_requested.connect(self._on_run)
        self.setStyleSheet(f'background:{_BG};color:{_FG};')

    @Slot(dict)
    def _on_run(self, params: dict):
        if self._worker and self._worker.isRunning():
            return
        self._last_params = params
        self._param.set_running(True)
        self._result.set_running()
        self._plots.clear_plots()
        self._worker = SpectrumWorker(params)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @Slot(dict)
    def _on_finished(self, result: dict):
        self._param.set_running(False)
        self._result.update(result)
        self._plots.update_plots(result)

        # obs_time 을 result에 추가 (저장용)
        result['obs_time'] = self._last_params.get('obs_time', '')

        # 프로젝트가 열려 있으면 자동 저장
        proj = get_project()
        if proj.is_open:
            proj.add_observation(result, bin_filepath=self._param.current_bin_path or '')

        self.obs_finished.emit(result)

    @Slot(str)
    def _on_error(self, msg: str):
        self._param.set_running(False)
        self._result.set_error(msg)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    win = QMainWindow()
    win.setWindowTitle('스펙트럼 분석기 — 테스트')
    win.resize(1100, 680)
    win.setCentralWidget(SpectrumWidget())
    win.show()
    sys.exit(app.exec())
