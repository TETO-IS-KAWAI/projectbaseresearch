# 앱 빌드 (Windows 폴더형 .exe)

`rt_v2` 를 Python 설치가 없는 PC 에서도 실행되는 **폴더형 실행 파일**로 묶습니다.
PyInstaller(onedir) 사용.

## 빌드 방법

빌드하는 PC 에서 (한 번만):

```bat
pip install -r requirements.txt
pip install -r requirements-build.txt
packaging\build.bat
```

완료되면:

```
dist\RWA_HI21cm\RWA_HI21cm.exe   ← 실행 파일
dist\RWA_HI21cm\                  ← 이 폴더 통째로 배포
```

> ⚠️ `RWA_HI21cm.exe` 만 떼어내면 동작하지 않습니다. **폴더 전체**를 복사해서 배포하세요.

## 정식 배포 (설치 파일 + GitHub Release)

### 한 번에 만들기 (이 PC)

```bat
pip install -r requirements.txt -r requirements-build.txt
winget install JRSoftware.InnoSetup          REM 설치 파일 컴파일러 (한 번만)
python packaging\make_release.py
```

`distelease\` 에 다음이 생깁니다.

| 파일 | 설명 |
|---|---|
| `RWA_HI21cm-<버전>-setup.exe` | 설치 파일 — 관리자 권한 없이 내 계정에 설치(첫 화면에서 '모든 사용자' 선택 가능), 시작 메뉴·바탕화면 바로가기, 제거 지원 |
| `RWA_HI21cm-<버전>-portable-win64.zip` | 휴대용 판 — 압축 풀고 바로 실행 |
| `SHA256SUMS.txt` | 파일 확인용 해시 |
| `RELEASE_NOTES.md` | `CHANGELOG.md` 에서 뽑은 Release 본문 |

버전은 `api.py` 의 `APP_VERSION` 한 곳만 고치면 exe 속성·설치 파일 이름·Release 제목이 같이 바뀝니다.
새 버전을 낼 때는 `CHANGELOG.md` 맨 위에 `## [x.y.z] — 날짜` 항목을 추가하세요.

### GitHub 에 게시

- **자동 (권장)** — `main` 에 합친 뒤 버전 태그를 올리면 `.github/workflows/release.yml` 이
  GitHub 의 Windows 서버에서 빌드해서 Release 를 만듭니다.
  ```bat
  git tag v2.0.0
  git push origin v2.0.0
  ```
  태그가 `APP_VERSION` 과 다르면 빌드가 멈춥니다. Actions 탭의 *Run workflow* 는 게시 없이 빌드만 합니다.
- **수동** — GitHub 저장소 → Releases → *Draft a new release* → 태그 `v2.0.0` →
  `distelease\` 의 setup.exe·zip·SHA256SUMS.txt 를 끌어다 놓고 본문에 `RELEASE_NOTES.md` 내용 붙여넣기.

### 라이선스

설치 폴더의 `licenses\` 에 앱(MIT)·Qt/PySide6(LGPL-3.0, GPL-3.0 원문)·Python(PSF)·NumPy·SciPy·Astropy·
astropy-healpix·PyERFA 라이선스와 `THIRD_PARTY_NOTICES` 가 자동으로 들어갑니다. Qt 는 수정 없이
별도 DLL 로 동적 연결되어 LGPL 조건(교체 가능)을 만족합니다.

### 코드 서명

서명이 없으면 인터넷에서 받은 setup.exe 에 SmartScreen 경고가 뜹니다(사용자는 *추가 정보 → 실행*).
인증서를 구하면 빌드 후 `signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a <파일>`
로 `dist\RWA_HI21cm\RWA_HI21cm.exe` 와 setup.exe 에 서명합니다.

## 사용자 데이터 위치

빌드된 앱은 설정·프로젝트를 다음 위치에 저장합니다 (읽기 전용 번들과 분리):

```
%APPDATA%\RWA_HI21cm\config.json     ← 설정
%APPDATA%\RWA_HI21cm\projects\       ← 관측 프로젝트(.json) 기본 폴더
```

개발 중(`python run.pyw`)에는 `rt_v2/config.user.json`(git 무시)과 `rt_v2/projects/` 를
사용합니다. `assets/config.json` 은 기본값으로만 읽습니다. (`config.py` 의 `_FROZEN` 분기 참고)

## 구성 파일

| 파일 | 역할 |
|---|---|
| `rwa_app.spec` | PyInstaller 빌드 설정 (진입점 `run.pyw`, 아이콘 `app.ico`, `web/`·`assets/` 번들, astropy 수집) |
| `build.bat` | 빌드 실행 스크립트 |

## 자주 겪는 문제

- **창이 안 뜨고 바로 종료** — 보통 번들 누락. 임시로 `rwa_app.spec` 의 `console=False`
  를 `True` 로 바꿔 다시 빌드하면 콘솔에 오류가 보입니다.
- **창은 뜨는데 화면이 하얗거나 깨짐** — GPU 드라이버 문제일 수 있습니다.
  환경 변수 `RWA_SOFTWARE_GL=1` 로 실행하면 소프트웨어 렌더링으로 돌아갑니다.
- **ImportError** — `rwa_app.spec` 의 `collect_all` 목록이나 `hiddenimports` 에
  누락 패키지를 추가하세요.
- **아이콘이 기본 아이콘으로 보임** — 탐색기 아이콘 캐시 때문일 수 있습니다.
  `assets/icons/app.ico` 가 있는지 먼저 확인하세요.
- **용량** — Qt WebEngine(Chromium) 런타임이 대부분입니다. v1 의 VTK 판보다는 작습니다.
