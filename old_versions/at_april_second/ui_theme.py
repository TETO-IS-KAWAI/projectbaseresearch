"""
ui_theme.py
앱 전역 Qt 스타일시트 (main_app, spectrum_widget 공통 색상)
"""

# 한국 디자인 시스템 팔레트
BG   = '#f7f5f0'
BG2  = '#ffffff'
BG3  = '#eeece6'
FG   = '#111010'
FG2  = '#3a3a38'
ACC  = '#00c9a7'
OK   = '#008f77'
ERR  = '#ff5a3c'
WARN = '#f2a818'

APP_STYLESHEET = f'''
QMainWindow, QWidget {{
    background-color: {BG};
    color: {FG};
}}
QMenuBar {{
    background-color: {BG2};
    color: {FG};
    border-bottom: 1px solid {BG3};
    padding: 4px 0;
}}
QMenuBar::item:selected {{
    background-color: #e0faf4;
    color: {OK};
}}
QMenu {{
    background-color: {BG2};
    color: {FG};
    border: 1px solid {BG3};
}}
QMenu::item:selected {{
    background-color: #e0faf4;
    color: {OK};
}}
QMenu::separator {{
    background-color: {BG3};
    height: 1px;
    margin: 4px 0;
}}
QStatusBar {{
    background-color: {BG2};
    color: {FG2};
    border-top: 1px solid {BG3};
    padding: 4px 12px;
}}
QStatusBar::item {{
    border: none;
}}
QGroupBox {{
    border: 1px solid {BG3};
    border-radius: 12px;
    margin-top: 8px;
    padding-top: 12px;
    color: {FG};
    font-weight: 500;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {FG2};
}}
QLabel {{
    color: {FG};
}}
QPushButton {{
    background-color: {ACC};
    color: {FG};
    border: none;
    border-radius: 6px;
    padding: 9px 18px;
    font-weight: 600;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: #00b896;
}}
QPushButton:pressed {{
    background-color: {OK};
}}
QLineEdit {{
    background-color: {BG};
    color: {FG};
    border: 1.5px solid {BG3};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: {ACC};
}}
QLineEdit:focus {{
    border: 1.5px solid {ACC};
    background-color: {BG2};
}}
QComboBox {{
    background-color: {BG};
    color: {FG};
    border: 1.5px solid {BG3};
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
}}
QComboBox:focus {{
    border: 1.5px solid {ACC};
}}
QSplitter::handle {{
    background-color: {BG3};
}}
QSplitter::handle:hover {{
    background-color: #d4d2cc;
}}
'''

BTN_STYLE = (
    f'background:{ACC};color:{FG};border:none;'
    f'border-radius:6px;padding:6px 14px;font-size:12px;font-weight:600;'
)
