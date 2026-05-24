# HI 21cm 전파망원경 소프트웨어

고등학교 전파망원경 프로젝트용 데이터 처리 앱입니다.  
Airspy SDR `.bin` IQ 데이터를 분석해 HI 21cm 수소선 밝기온도 지도를 만듭니다.

## 요구 사항

- Python 3.11 ~ 3.13 권장 (3.14도 대부분 동작)
- Windows / macOS / Linux

## 설치

```powershell
cd rt_combined
pip install -r requirements.txt
```

HEALPix 연산은 **astropy-healpix** (BSD)만 사용합니다.

### 은하 전경 차감 (healpy 없음)

| 방식 | 조건 |
|------|------|
| **해석식** | 항상 사용 가능 — 은하 위도 \|b\| 기반 연속체 근사 |
| **FITS** | `assets/foreground_gsm_1420.fits` 있으면 자동 우선 (GSM 등) |

FITS 생성(선택, 1회): `python scripts/generate_foreground_fits.py`  
→ healpy/pygdsm 필요. 없으면 해석식만 사용. 자세한 내용: `assets/FOREGROUND_FITS.md`

### 선택 기능

| 기능 | 패키지 | 없을 때 |
|------|--------|---------|
| MOC FITS 저장 | `mocpy` | FITS 저장만 불가 |
| 커버리지 표시 | (불필요) | HEALPix 마스크로 동작 |

```powershell
pip install -r requirements-optional.txt
```

## 아이콘 (PNG)

`assets/icons/` 에 PNG를 넣으면 메뉴·버튼·창 아이콘에 자동 적용됩니다.  
파일 이름·크기: [assets/icons/README.md](assets/icons/README.md)

## 실행

```powershell
python main_app.py
```

## 파일 구조

| 파일 | 역할 |
|------|------|
| `main_app.py` | 메인 윈도우, 메뉴, 프로젝트 열기/저장 |
| `config.py` | 설정 싱글턴 (`assets/config.json`) |
| `astro_processing.py` | FFT, 도플러 보정, 밝기온도, HEALPix 지도 |
| `data_manager.py` | 프로젝트 `.json` / FITS보내기 |
| `spectrum_widget.py` | 스펙트럼 분석 UI |
| `sky_viewer.py` | PyVista 3D 천구 뷰어 |
| `foreground_processing.py` | 은하 연속체 전경 (해석식 / FITS) |
| `moc_manager.py` | 관측 커버리지 MOC (선택) |

## 사용 흐름

1. **파일 → 새 프로젝트** 또는 **열기**
2. 왼쪽 패널에서 RA/Dec, 관측 시각 입력 후 **▶ 분석 실행**
3. 오른쪽 3D 구에 HEALPix 히트맵 갱신
4. **파일 → FITS보내기**로 결과 저장

더미 데이터 모드로 `.bin` 없이도 파이프라인을 시험할 수 있습니다.

## 프로젝트 규칙

- HEALPix: RING ordering, ICRS, `astropy-healpix` 사용
- 프로젝트 파일: `.json` (무거운 배열 미저장, 열 때 sky_map 재구성)
- `astro_processing.py` 도플러 보정 로직은 변경하지 않음
