# HI 21cm 전파망원경 소프트웨어

SDR로 수신한 **HI 21cm 수소선(1.420 GHz)** 데이터를 처리하여, 도플러 보정과
밝기온도 환산을 거쳐 **우리 은하의 나선팔**을 시각화하는 데스크톱 소프트웨어입니다.

> SASA · 10기 · 팀 RWA

---

## 주요 기능

- **관측 입력** — 위도/경도/날짜/시각 + `.wav`(SDR IQ 데이터) 파일
- **도플러 보정** — 지구 자전 · 공전 · 은하 LSR을 합산해 정지좌표계 속도로 변환
- **밝기온도 환산** — 이동중앙값 밴드패스 추정 후 레일리-진스 공식으로 `T_b(ν)` 계산
- **3D 전천 히트맵** — HEALPix로 천구를 분할해 구면 위에 밝기온도 표시 (PyVista)
- **은하 나선팔 조감도** — HI 피크 검출 → 운동학적 거리 환산 → 은하면 위 나선팔 매핑
- **은하 전경 차감 / 커버리지(MOC)** — 선택 기능
- **프로젝트 관리** — 관측을 `.json` 프로젝트로 저장/열기, FITS 내보내기

---

## 설치

Python 3.10+ 권장.

```bash
pip install -r requirements.txt
# (선택) MOC 내보내기·진단 플롯·바탕화면 바로가기
pip install -r requirements-optional.txt
```

## 실행

```bash
python run.pyw        # 콘솔 창 없이 GUI 실행 (권장)
# 또는
python main_app.py
```

Windows에서 바탕화면 바로가기를 만들려면 (pywin32 필요):

```bash
python scripts/setup_icon.py
```

---

## 처리 흐름

```
.wav (SDR IQ)
   └─ FFT → 파워 스펙트럼
        └─ 밴드패스 추정(이동중앙값) → T_b(ν)  [레일리-진스]
             ├─ 대표 밝기온도(peak/integral/mean/median) → HEALPix 픽셀 → 3D 히트맵
             └─ HI 피크 검출(MAD 기반) → 운동학적 거리 → 나선팔 조감도
```

---

## 모듈 구조

| 파일 | 역할 |
|---|---|
| `run.pyw` | GUI 런처 (콘솔 없이 실행) |
| `main_app.py` | 진입점 · 메인 윈도우 · 메뉴 |
| `config.py` | 설정 관리 (`assets/config.json`) |
| `data_manager.py` | 프로젝트 `.json` 입출력 · FITS 내보내기 |
| `astro_processing.py` | **핵심 신호처리** — 도플러 · 밴드패스 · 밝기온도 · HEALPix |
| `spiral_arm.py` | HI 피크 검출 · 운동학적 거리 환산 |
| `spectrum_widget.py` | 좌측 관측/스펙트럼 패널 |
| `sky_viewer.py` | 3D 전천 히트맵 (PyVista) |
| `galactic_map.py` | 은하 조감도 / 나선팔 (pyqtgraph) |
| `foreground_processing.py` | 은하 연속체 전경 모델 *(선택)* |
| `moc_manager.py` | 관측 커버리지 / MOC *(선택)* |
| `ui_theme.py`, `ui_icons.py` | UI 테마 · 아이콘 로더 |
| `scripts/` | 개발용 1회성 도구 (전경 FITS 생성, 바로가기 설정) |
| `assets/` | `config.json` · 아이콘 |
| `projects/` | 관측 프로젝트(`.json`) 기본 저장 폴더 |

> 핵심 라이브러리: **PySide6 · pyqtgraph · PyVista · Astropy · astropy-healpix · NumPy · SciPy**
> HEALPix 연산은 라이선스 호환을 위해 `healpy` 대신 **astropy-healpix(BSD)** 만 사용합니다.

---

## 크레딧

**SASA · 10기 · 팀 RWA**

- 코드 작성 — TETO-IS-KAWAI

© 2026 Team RWA — [MIT License](../LICENSE)
