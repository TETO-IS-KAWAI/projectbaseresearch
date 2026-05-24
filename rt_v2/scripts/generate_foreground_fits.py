#!/usr/bin/env python3
"""
GSM2016 1420 MHz HEALPix FITS 생성 (선택, 1회만 실행)

healpy/pygdsm 이 있는 환경에서만 동작합니다.
생성 파일: assets/foreground_gsm_1420.fits

앱 본체는 이 파일 없이도 해석식 전경 보정을 사용합니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT  = ROOT / 'assets' / 'foreground_gsm_1420.fits'

HI_MHZ = 1420.40575177


def main() -> int:
    try:
        from pygdsm import GlobalSkyModel2016 as GSM
    except ImportError:
        print(
            'pygdsm 이 설치되어 있지 않습니다.\n'
            '  (healpy 빌드가 필요해 이 PC에서는 생략 가능합니다.)\n'
            '앱은 해석식 전경 보정만으로 동작합니다.',
            file=sys.stderr,
        )
        return 1

    print(f'GSM2016 @ {HI_MHZ} MHz 생성 중...')
    gsm = GSM(freq_unit='MHz', data_unit='TRJ')
    gsm.generate(HI_MHZ)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    gsm.write_fits(str(OUT))
    print(f'저장: {OUT}')
    print('앱을 다시 실행하면 FITS 전경 보정이 자동 적용됩니다.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
