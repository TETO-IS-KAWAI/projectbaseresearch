# Qt 위젯 UI (v1) — 보관용

v2.0 에서 화면이 Qt WebEngine + HTML/CSS/JS (`rt_v2/web/`) 로 바뀌면서 더 이상
쓰지 않는 PySide6 위젯 UI 입니다. 논문(AJP 원고) IV.B 의 그림 7 은 이 버전의 화면입니다.

| 파일 | 역할 |
|---|---|
| `spectrum_widget.py` | 관측 파라미터 + 스펙트럼 (pyqtgraph) |
| `sky_viewer.py` | 3D 전천 히트맵 (PyVista/VTK) |
| `galactic_map.py` | 은하 조감도 / 나선팔 (pyqtgraph) |
| `ui_theme.py`, `ui_icons.py` | Qt 스타일시트 · 아이콘 로더 |
| `rwa_app_lite.spec`, `build_lite.bat` | 3D 제외 경량 빌드 설정 |

계산 모듈(`astro_processing`, `spiral_arm`, `data_manager` …)은 `rt_v2/` 에 그대로 있습니다.
실행하려면 `rt_v2/` 를 PYTHONPATH 에 넣고 pyqtgraph·pyvista·pyvistaqt 를 따로 설치해야 합니다.
