# HI 21cm 전파망원경 소프트웨어 · v2

SDR로 수신한 **HI 21cm 수소선(1420.406 MHz)** 데이터를 처리하여, 도플러 보정과
밝기온도 환산을 거쳐 **우리 은하의 나선팔**을 그리는 데스크톱 앱입니다.

> SASA · 10기 · 팀 RWA

---

## 주요 기능

- **관측** — 적경/적위(소수·HMS·DMS), 관측 시각, 시뮬레이션 또는 SDR 파일(`.wav`/`.bin`).
  방향 프리셋(은하면 l 30° 등·지금 천정), 입력하는 동안 은하 좌표·현재 고도 미리보기.
  실행하면 처리 단계(IQ → FFT → 도플러 → T<sub>b</sub> → 피크 → 거리 → 저장)가 실시간으로 표시됩니다.
- **스펙트럼** — 밝기온도/파워, 속도축(v<sub>LSR</sub>)/주파수축 전환. 휠 확대·드래그 이동·십자선 읽기.
- **하늘 지도** — HEALPix 픽셀에 밝기온도 누적. 몰바이데 / 드래그로 돌리는 천구, 은하·적도 좌표,
  관측지에서 안 뜨는 하늘·지금의 천정과 지평선 표시, FITS·MOC 내보내기.
- **은하 지도 (나선팔)** — 세 가지 보기
  - **관측 데이터로 추론**: 배경 나선팔 없이 관측 피크만 운동학적 거리로 찍고,
    점이 충분히 모이면 **로그 나선 허프 변환**으로 팔을 직접 찾아냅니다 (팔 개수·팔별 피치각 자동).
  - **문헌 모델 예측**: 데이터와 무관하게 Hou & Han (2014) 근사 팔과,
    관측한 시선마다 "팔을 지나는 곳·그곳의 예상 v<sub>LSR</sub>" 을 보여 줍니다.
  - **겹쳐 보기**: 추론한 팔과 문헌 팔 비교.
  - 근/원거리 모호성(자동·근·원), |b| 한계, 팔 폭 허용 등 조건 조절 · 허프 공간 미니맵 ·
    합성 데이터(문헌 팔 + 속도 잡음)로 체험.
- **관측 기록** — 정렬·검색, 행을 펼쳐 피크 확인 · 하늘 지도에서 보기 · 같은 방향 재관측 · 삭제.
- **앱 다운 마감** — 다크/라이트 테마, 명령 팔레트(<kbd>Ctrl</kbd>+<kbd>K</kbd>), 단축키,
  픽셀로 조립·분해되는 제목과 시작 화면, 애니메이션 줄이기 옵션.

---

## 설치 · 실행

Python 3.10+ 권장.

```bash
pip install -r requirements.txt
# (선택) MOC 내보내기 · 진단 그림 · 바탕화면 바로가기
pip install -r requirements-optional.txt

python run.pyw        # 콘솔 창 없이 실행 (권장)
python main_app.py    # 콘솔 로그와 함께 실행
```

- GPU 문제로 화면이 깨지면 **설정 → 하드웨어 → 그래픽 가속: 끄기** 또는 `RWA_SOFTWARE_GL=1` 로 실행하세요.
- `RWA_DEBUG=1` 로 실행하면 <kbd>F12</kbd> 로 개발자 도구가 열립니다.
- Windows `.exe` 빌드는 [`packaging/README.md`](packaging/README.md) 참고.

### 화면만 브라우저로 고치기 (개발용)

```bash
python scripts/dev_server.py      # → http://127.0.0.1:8765/
```

데스크톱 앱과 같은 `api.py` 를 HTTP 로 노출합니다. 파일 대화상자 대신 경로 입력창이 뜹니다.

---

## 구조

```
화면 (web/: HTML · CSS · JS, Qt WebEngine 이 그림)
   │  QWebChannel  ─ backend.request(id, method, args) / response(id, json)
   ▼
main_app.py  ── Bridge (작업 스레드 1개, 대화상자는 메인 스레드)
   ▼
api.py  ── Api.api_<method>()  (Qt 비의존 · JSON 반환)
   ▼
astro_processing · spiral_arm · data_manager · foreground_processing · moc_manager
```

| 파일 | 역할 |
|---|---|
| `run.pyw` | 런처 (콘솔 없이 실행) |
| `main_app.py` | Qt 창 · WebEngine · QWebChannel 다리 · 파일 대화상자 |
| `api.py` | 화면이 부르는 백엔드 API (상태·설정·프로젝트·관측·지도·나선팔) |
| `compute.py` | 관측 처리 전용 프로세스 (다른 CPU 코어, 실패 시 스레드 폴백) |
| `config.py` | 설정 (개발: `config.user.json`, 빌드: `%APPDATA%\RWA_HI21cm`) |
| `data_manager.py` | 프로젝트 `.json` 입출력 · FITS 내보내기 |
| `astro_processing.py` | **신호처리** — FFT · 도플러 · 밴드패스 · 밝기온도 · HEALPix |
| `spiral_arm.py` | HI 피크 검출 · 운동학적 거리 · **나선팔 추론(허프 변환)** · 문헌 모델 |
| `foreground_processing.py` | 은하 연속체 전경 모델 *(선택)* |
| `moc_manager.py` | 관측 커버리지 / MOC *(선택)* |
| `web/` | 화면: `index.html`, `css/app.css`, `js/*.js`, `fonts/` |
| `scripts/` | `dev_server.py`(화면 개발), 전경 FITS 생성, 바로가기 설정 |
| `assets/` | 기본 `config.json` · 아이콘 |
| `projects/` | 관측 프로젝트(`.json`) 기본 저장 폴더 |

`web/js/` — `core.js`(백엔드 연결·좌표·HEALPix·색), `pixel.js`(픽셀 이펙트),
`chart.js`(스펙트럼), `sky.js`(전천 지도), `galaxy.js`(은하 조감도), `pages.js`(화면별 동작), `app.js`(부팅·라우터·팔레트).

v1 의 Qt 위젯 화면(pyqtgraph·PyVista)은 `old_versions/qt_widgets_v1/` 에 보관되어 있습니다.

---

## 하드웨어 · 보안

- **GPU** — 지도·애니메이션은 Qt WebEngine(Chromium)이 GPU 로 그립니다. 오래된 내장 그래픽
  (LattePanda 의 Intel HD 등)도 Chromium 차단 목록을 무시하고 가속을 씁니다. 설정 → 하드웨어에서
  지금 쓰는 그래픽 장치를 볼 수 있고, 문제가 있으면 끌 수 있습니다(다시 시작 후 적용).
- **계산 프로세스** — 관측 처리(FFT·도플러·밴드패스)는 `compute.py` 의 전용 프로세스가 다른 CPU
  코어에서 맡아, 계산 중에도 화면이 끊기지 않습니다. 못 띄우면 자동으로 앱 안 스레드로 돌아갑니다
  (`RWA_NO_SUBPROCESS=1` 로 강제 가능).
- **그리기** — 지도는 한 프레임에 한 번만 다시 그리고, 바뀌지 않는 층(동심원·팔·HEALPix 바탕)은
  캐시해 두었다가 붙여 넣습니다.
- **보안** — 화면은 앱 폴더의 `index.html` 밖으로 이동할 수 없고(새 창·끌어다 놓기·외부 링크 차단),
  콘텐츠 보안 정책(CSP)으로 인라인 스크립트·인터넷 접속을 막습니다. 카메라·위치 등 권한 요청은 모두
  거부하고, 캐시·쿠키를 디스크에 남기지 않습니다. 파이썬 API 는 파일 종류(.json/.fits/.wav/.bin)와
  크기를 검사합니다. astropy 자동 다운로드도 꺼져 있어 앱은 스스로 인터넷에 접속하지 않습니다.
  `scripts/dev_server.py` 는 127.0.0.1 에서만, 같은 출처의 요청만 받습니다.

---

## 물리 모델 메모

- 은하 회전: 평탄 회전 곡선, **R₀ = 8.15 kpc, Θ₀ = 236 km/s** (Reid et al. 2019).
- 태양 고유운동: Schönrich, Binney & Dehnen (2010) UVW = (11.1, 12.24, 7.25) km/s.
- 운동학적 거리: d > 0 인 해만 물리적. 내부 은하 1·4사분면은 근/원 두 해, 외부 은하는 유일해,
  2·3사분면의 '금지 속도'는 거리 없음. 조감도에는 은하면 투영 거리 d·cos b 로 찍습니다.
- 나선팔 추론: ln r + tan ψ · θ = ξ (나선 위상) 가 한 팔 위에서 일정 → (ψ, ξ) 허프 누적 →
  봉우리마다 최소제곱 재맞춤, 소속점 제거 후 반복. 팔 개수·피치각은 데이터가 정합니다.
- 밝기온도는 잡음원·hot/cold 보정이 없는 **상대값**이며, 빔(~20°)과 속도 오차 때문에
  실제 관측만으로 개별 나선팔을 분해하기는 어렵습니다 (논문 VI·VII 장).

> 라이브러리: **PySide6 (Qt WebEngine) · NumPy · SciPy · Astropy · astropy-healpix** (MIT/BSD).
> HEALPix 는 라이선스 호환을 위해 `healpy` 대신 **astropy-healpix** 만 씁니다.
> 글꼴: **Geist · Geist Mono · Pretendard** — SIL Open Font License 1.1 (`web/fonts/`).

---

## 크레딧

**SASA · 10기 · 팀 RWA**

- 코드 작성 — TETO-IS-KAWAI

© 2026 Team RWA — [MIT License](../LICENSE)
