"""
setup_icon.py
run.pyw 파일에 아이콘 지정

실행: python setup_icon.py
"""

import os
import sys
from pathlib import Path

# Windows API를 사용하여 파일에 아이콘 속성 지정
try:
    import win32com.client
    
    shell = win32com.client.Dispatch("WScript.Shell")
    
    # run.pyw 파일 경로
    pyw_path = Path(__file__).parent / "run.pyw"
    
    # 아이콘 파일 경로 (assets/icons/app.ico 또는 app.png)
    icon_path = Path(__file__).parent / "assets" / "icons" / "app.ico"
    
    if not icon_path.exists():
        # PNG가 있으면 ICO가 없을 수 있으므로, PNG 대신 사용
        icon_path = Path(__file__).parent / "assets" / "icons" / "app.png"
    
    if pyw_path.exists() and icon_path.exists():
        # 바로가기 생성
        shortcut_path = str(pyw_path.parent / "RT_망원경.lnk")
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.TargetPath = str(pyw_path)
        shortcut.WorkingDirectory = str(pyw_path.parent)
        shortcut.IconLocation = str(icon_path)
        shortcut.save()
        print(f"✅ 바로가기 생성: {shortcut_path}")
        print(f"   아이콘: {icon_path}")
    else:
        print("❌ run.pyw 또는 아이콘 파일을 찾을 수 없습니다.")
        
except ImportError:
    print("❌ win32com 라이브러리 필요: pip install pywin32")
    sys.exit(1)
