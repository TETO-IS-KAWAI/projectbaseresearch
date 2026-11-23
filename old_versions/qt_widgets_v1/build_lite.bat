@echo off
REM ============================================================
REM  RWA HI 21cm 전파망원경 - 경량(Lite) 빌드 (3D 뷰어 제외)
REM  실행:  packaging\build_lite.bat
REM ============================================================
setlocal
cd /d "%~dp0.."

echo === 경량 빌드 시작 (VTK 제외, 수 분 소요) ===
python -m PyInstaller --noconfirm --clean "packaging\rwa_app_lite.spec"
if errorlevel 1 (
  echo.
  echo [실패] 빌드 중 오류가 발생했습니다. 위 로그를 확인하세요.
  exit /b 1
)

echo.
echo === 경량 빌드 완료 ===
echo 실행 파일: dist\RWA_HI21cm_Lite\RWA_HI21cm_Lite.exe
echo (3D 전천 히트맵 탭 없음 / 은하 조감도-나선팔 탭만)
endlocal
