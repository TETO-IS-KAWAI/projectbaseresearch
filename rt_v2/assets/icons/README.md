# 아이콘 (PNG)

PySide6에서 **PNG**를 그대로 쓸 수 있습니다. 이 폴더에 파일만 넣으면 앱·버튼·메뉴에 자동 반영됩니다.

> **`app.ico` 안내** — 앱 창/작업표시줄 아이콘은 `app.png` 를 직접 씁니다.
> 다만 **Windows 바탕화면 바로가기(.lnk)** 는 PNG 를 인식하지 못하므로 `app.ico` 가 필요합니다.
> `python scripts/setup_icon.py` 를 실행하면 `app.png` 에서 `app.ico` 를 자동 생성하고(Pillow 필요)
> 바로가기에 적용합니다. 즉 **원본은 `app.png` 하나만 유지하면 됩니다.**

## 권장 크기

| 용도 | 크기 |
|------|------|
| 창 아이콘 `app.png` | 32×32 ~ 256×256 |
| 버튼·메뉴 | 20×20 ~ 24×24 (투명 배경 PNG) |

## 파일 이름

### 앱 / 메뉴 (`main_app.py`)

| 파일명 | 위치 |
|--------|------|
| `app.png` | 작업 표시줄·창 아이콘 |
| `new_project.png` | 파일 → 새 프로젝트 |
| `open.png` | 파일 → 프로젝트 열기 |
| `export_fits.png` | 파일 → FITS보내기 |
| `quit.png` | 파일 → 종료 |
| `settings.png` | 설정 메뉴 (선택) |

### 3D 뷰어 (`sky_viewer.py`)

| 파일명 | 버튼 |
|--------|------|
| `reset.png` | 초기화 |
| `foreground.png` | 은하 전경 차감 |
| `coverage.png` | 커버리지 표시 |
| `moc_export.png` | MOC보내기 |
| `galactic_grid.png` | 은하 격자 |
| `grid.png` | 격자 끄기 |

### 스펙트럼 (`spectrum_widget.py`)

| 파일명 | 버튼 |
|--------|------|
| `run.png` | ▶ 분석 실행 |
| `file.png` | 파일 선택 (선택) |

## 예시

```
assets/icons/
  app.png
  reset.png
  foreground.png
  run.png
  ...
```

SVG도 동일 이름으로 넣을 수 있습니다 (`app.svg`).
