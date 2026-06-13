@echo off
REM ============================================================
REM  RWA HI 21cm 전파망원경 - Windows 폴더형(.exe) 빌드
REM  실행:  packaging\build.bat   (rt_v2 어디서 더블클릭해도 됨)
REM ============================================================
setlocal
cd /d "%~dp0.."

echo === PyInstaller 빌드 시작 (VTK 포함, 수 분 소요) ===
python -m PyInstaller --noconfirm --clean "packaging\rwa_app.spec"
if errorlevel 1 (
  echo.
  echo [실패] 빌드 중 오류가 발생했습니다. 위 로그를 확인하세요.
  exit /b 1
)

echo.
echo === 빌드 완료 ===
echo 실행 파일: dist\RWA_HI21cm\RWA_HI21cm.exe
echo (dist\RWA_HI21cm 폴더 통째로 복사해서 배포하세요)
endlocal
