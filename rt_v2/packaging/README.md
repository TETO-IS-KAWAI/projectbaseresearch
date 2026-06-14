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

## 사용자 데이터 위치

빌드된 앱은 설정·프로젝트를 다음 위치에 저장합니다 (읽기 전용 번들과 분리):

```
%APPDATA%\RWA_HI21cm\config.json     ← 설정
%APPDATA%\RWA_HI21cm\projects\       ← 관측 프로젝트(.json) 기본 폴더
```

개발 중(`python run.pyw`)에는 기존처럼 `rt_v2/assets/config.json`,
`rt_v2/projects/` 를 사용합니다. (`config.py` 의 `_FROZEN` 분기 참고)

## 구성 파일

| 파일 | 역할 |
|---|---|
| `rwa_app.spec` | PyInstaller 빌드 설정 (진입점 `run.pyw`, 아이콘 `app.ico`, VTK/astropy 수집) |
| `build.bat` | 빌드 실행 스크립트 |

## 자주 겪는 문제

- **창이 안 뜨고 바로 종료** — 보통 번들 누락. 임시로 `rwa_app.spec` 의 `console=False`
  를 `True` 로 바꿔 다시 빌드하면 콘솔에 오류가 보입니다.
- **`vtk`/`pyvista` 관련 ImportError** — `rwa_app.spec` 의 `collect_all` 목록에
  누락 패키지를 추가하세요.
- **아이콘이 기본 아이콘으로 보임** — 탐색기 아이콘 캐시 때문일 수 있습니다.
  `assets/icons/app.ico` 가 있는지 먼저 확인하세요.
- **용량이 큼(수백 MB)** — VTK 때문입니다. onedir 특성상 정상입니다.
