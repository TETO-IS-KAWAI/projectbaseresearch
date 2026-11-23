# 제3자 구성요소 고지 (Third-Party Notices)

**HI 21cm 전파망원경**(© 2026 Team RWA, SASA 10th — MIT License, `LICENSE.txt`)은
아래 오픈소스 구성요소를 포함해 배포됩니다. 각 구성요소는 해당 라이선스를 따릅니다.
이 폴더(`licenses/`)에 라이선스 원문이 함께 들어 있습니다.

This application bundles the open-source components below. Each component remains
under its own license; full texts are in this `licenses/` folder.

| 구성요소 | 용도 | 라이선스 | 원문 |
|---|---|---|---|
| Python 3 | 실행 환경 (OpenSSL·libffi·bzip2 등 포함) | PSF License (+ 포함 라이브러리별 조건) | `Python-LICENSE.txt` |
| Qt 6 / PySide6 (Qt for Python) | 창, 웹 화면(Qt WebEngine), QWebChannel | **LGPL-3.0** | `LGPL-3.0.txt`, `GPL-3.0.txt` |
| Qt WebEngine (Chromium 기반) | HTML·CSS·JS 화면 렌더링 | LGPL-3.0 + Chromium 구성요소별 라이선스 | 아래 참고 |
| NumPy | 수치 계산 | BSD-3-Clause (+ 포함 라이브러리) | `numpy\` |
| SciPy | 신호 처리 | BSD-3-Clause (+ 포함 라이브러리) | `scipy\` |
| Astropy | 좌표·시간·도플러 보정, FITS | BSD-3-Clause | `astropy\` |
| astropy-healpix | HEALPix 천구 분할 | BSD-3-Clause | `astropy_healpix\` |
| PyERFA | 천문 기본 계산(astropy 의존) | BSD-3-Clause | `pyerfa\` |
| MOCPy | 관측 커버리지(MOC) 내보내기 | BSD-3-Clause | `mocpy\` |
| Geist, Geist Mono | 글꼴 | SIL Open Font License 1.1 | `fonts\Geist-OFL.txt` |
| Pretendard | 글꼴 | SIL Open Font License 1.1 | `fonts\Pretendard-LICENSE.txt` |
| PyInstaller 부트로더 | 실행 파일 묶음 | GPL-2.0 + 부트로더 예외 | 예외 조항에 따라 배포물에 GPL 이 적용되지 않음 |

## Qt / PySide6 (LGPL-3.0) 관련 안내

- Qt 와 PySide6 는 LGPL-3.0 에 따라 **수정하지 않은 상태로**, 별도 DLL·모듈 파일로 동적 연결되어
  들어 있습니다(설치 폴더의 `_internal\PySide6\`). 사용자는 이 파일들을 호환되는 다른 버전으로
  교체할 수 있습니다.
- 소스 코드: Qt — <https://download.qt.io/official_releases/qt/>,
  Qt for Python(PySide6) — <https://code.qt.io/cgit/pyside/pyside-setup.git/>
  (사용한 버전: PySide6 6.10.2).
- 이 앱 자체의 소스 코드: <https://github.com/TETO-IS-KAWAI/projectbaseresearch>

## Qt WebEngine / Chromium

Qt WebEngine 은 Chromium 과 그 제3자 라이브러리를 포함하며, 각각 BSD·MIT·LGPL 등
개별 라이선스를 가집니다. 전체 목록은 Qt 문서
<https://doc.qt.io/qt-6/qtwebengine-licensing.html> 를 참고하세요.
