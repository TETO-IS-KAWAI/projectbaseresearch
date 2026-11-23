#!/usr/bin/env pythonw
"""
run.pyw — HI 21cm 전파망원경 GUI 런처

콘솔 창 없이 GUI 만 띄웁니다.
  · 더블클릭으로 실행 (Windows: pythonw 연결)
  · 또는 터미널에서  python run.pyw

flat import 구조라서 이 폴더를 모듈 검색 경로 맨 앞에 추가합니다.
"""

import multiprocessing
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == '__main__':
    # PyInstaller 빌드에서 관측 계산 프로세스(compute.py)가 자기 일만 하고 끝나게 한다
    multiprocessing.freeze_support()
    from main_app import main
    main()
