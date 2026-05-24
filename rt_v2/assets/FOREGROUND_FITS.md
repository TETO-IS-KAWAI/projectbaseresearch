# 전경 FITS (선택)

앱은 **healpy 없이** 동작합니다. 더 정확한 GSM 전경을 쓰려면 아래 FITS를 이 폴더에 넣으세요.

## 파일 이름 (둘 중 하나)

- `foreground_gsm_1420.fits` (권장)
- `gsm_1420.fits`

## 만드는 방법

### A) 다른 PC에서 pygdsm으로 1회 생성

```bash
pip install pygdsm   # healpy 빌드 가능한 환경
python scripts/generate_foreground_fits.py
```

생성된 `assets/foreground_gsm_1420.fits` 를 이 프로젝트 `assets/` 로 복사합니다.

### B) 외부 HEALPix FITS

GSM2016 / LAMBDA 등에서 받은 **RING** HEALPix FITS도 사용할 수 있습니다.  
열 이름: `I`, `TEMPERATURE`, `T` 등 float 컬럼.

## FITS가 없을 때

`은하 전경 차감` 버튼은 **은하 위도 |b| 해석 모델**을 사용합니다 (교육·시연용).
