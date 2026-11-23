"""
main_app.py
HI 21cm 전파망원경 — 데스크톱 앱 진입점

구조
  · 화면(UI)   : web/ 의 HTML·CSS·JS  (Qt WebEngine 이 그린다)
  · 계산       : api.py → astro_processing / spiral_arm / data_manager (파이썬 그대로)
  · 둘 사이    : QWebChannel 로 연결된 Bridge 객체 하나

JS 는 backend.request(id, method, argsJson) 를 부르고, 결과는 response(id, json)
시그널로 돌아온다. 무거운 계산은 작업 스레드 1개에서 순서대로 돌기 때문에
화면이 멈추지 않는다. 파일 대화상자처럼 Qt 메인 스레드가 필요한 요청은
'dialog_' 로 시작하며 메인 스레드에서 바로 처리한다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow

from config import Config, assets_dir

APP_ID = 'rwa.hi21cm.telescope'
_HERE = Path(__file__).resolve().parent
_FROZEN = bool(getattr(sys, 'frozen', False))
WEB_DIR = (Path(getattr(sys, '_MEIPASS', _HERE)) / 'web') if _FROZEN else (_HERE / 'web')

_BG = {'dark': '#0a0a0b', 'light': '#fafafa'}


def _set_dark_titlebar(win: QMainWindow, dark: bool) -> None:
    """Windows 10/11 제목 표시줄을 테마에 맞춘다 (실패해도 무시)."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        hwnd = int(win.winId())
        val = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):          # DWMWA_USE_IMMERSIVE_DARK_MODE (신/구 빌드)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                break
    except Exception:
        pass


class Bridge(QObject):
    """JS ↔ Python 다리. QWebChannel 에 'backend' 라는 이름으로 등록된다."""

    response = Signal(str, str)      # (요청 id, 결과 json)
    event    = Signal(str, str)      # (이벤트 이름, json)  — 진행률 등
    _done    = Signal(str, str)
    _evt     = Signal(str, str)

    def __init__(self, window: 'MainWindow'):
        super().__init__(window)
        from api import Api
        self._win = window
        self._api = Api(emit=lambda name, payload: self._evt.emit(
            name, json.dumps(payload, ensure_ascii=False)))
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='rt-api')
        # 작업 스레드 → 메인 스레드로 넘겨서 내보낸다 (QueuedConnection)
        self._done.connect(self.response, Qt.ConnectionType.QueuedConnection)
        self._evt.connect(self.event, Qt.ConnectionType.QueuedConnection)

    def shutdown(self) -> None:
        self._api.close()
        self._pool.shutdown(wait=False, cancel_futures=True)

    @Slot(str, str, str)
    def request(self, rid: str, method: str, args_json: str) -> None:
        try:
            args = json.loads(args_json or '{}')
        except json.JSONDecodeError:
            args = {}
        if method.startswith('dialog_') or method.startswith('window_'):
            fn = getattr(self, f'_ui_{method}', None)
            if fn is None or not isinstance(args, dict):
                out = {'ok': False, 'error': f'알 수 없는 요청: {method}'}
            else:
                try:
                    out = {'ok': True, 'data': fn(**args)}
                except Exception as e:
                    out = {'ok': False, 'error': str(e)}
            self.response.emit(rid, json.dumps(out, ensure_ascii=False))
            return

        if not isinstance(args, dict):
            args = {}

        def run():
            res = self._api.dispatch(method, args)
            self._done.emit(rid, json.dumps(res, ensure_ascii=False))
        self._pool.submit(run)

    # ── 메인 스레드 전용 (대화상자·창) ─────────────────────────

    def _cfg(self) -> Config:
        return Config.get()

    def _ui_dialog_open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self._win, '프로젝트 열기', str(self._cfg().projects_dir_path),
            'RT 프로젝트 (*.json);;모든 파일 (*)')
        return {'path': path or None}

    def _ui_dialog_save_project(self, name: str = '새 프로젝트'):
        default = str(self._cfg().projects_dir_path / f'{name}.json')
        path, _ = QFileDialog.getSaveFileName(
            self._win, '프로젝트 저장 위치', default, 'RT 프로젝트 (*.json)')
        return {'path': path or None}

    def _ui_dialog_open_iq(self):
        path, _ = QFileDialog.getOpenFileName(
            self._win, 'SDR 데이터 파일', str(self._cfg().data_dir_path),
            'SDR IQ 데이터 (*.wav *.bin);;모든 파일 (*)')
        if path:
            self._cfg().data_dir = str(Path(path).parent)
            self._cfg().save()
        return {'path': path or None, 'name': Path(path).name if path else None}

    def _ui_dialog_save_file(self, title: str = '저장', name: str = 'export',
                             filter: str = '모든 파일 (*)'):
        default = str(self._cfg().output_dir_path / name)
        path, _ = QFileDialog.getSaveFileName(self._win, title, default, filter)
        return {'path': path or None}

    def _ui_dialog_pick_dir(self, title: str = '폴더 선택'):
        path = QFileDialog.getExistingDirectory(self._win, title, str(self._cfg().projects_dir_path))
        return {'path': path or None}

    def _ui_window_theme(self, theme: str = 'dark'):
        dark = theme != 'light'
        _set_dark_titlebar(self._win, dark)
        self._win.view.page().setBackgroundColor(QColor(_BG['dark' if dark else 'light']))
        return {'theme': theme}

    def _ui_window_open_url(self, url: str):
        if url.startswith(('http://', 'https://')):
            QDesktopServices.openUrl(QUrl(url))
        return {}

    def _ui_window_reveal(self, path: str):
        p = Path(path)
        if not p.exists():
            return {}
        if sys.platform == 'win32':
            subprocess.Popen(['explorer', '/select,', str(p)])
        elif p.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p if p.is_dir() else p.parent)))
        return {}

    def _ui_window_title(self, title: str):
        self._win.setWindowTitle(title)
        return {}

    def _ui_window_quit(self):
        self._win.close()
        return {}

    def _ui_window_devtools(self):
        self._win.open_devtools()
        return {}


def _make_secure_page(profile, parent, home: Path):
    """앱 화면 전용 페이지: 우리 index.html 밖으로는 절대 나가지 않는다.

    QWebChannel 의 backend 객체는 '이 페이지에 로드된 모든 문서'가 부를 수 있다.
    끌어다 놓은 링크·팝업 등으로 외부 페이지가 열리면 그 페이지도 파일을 쓰는
    API 를 부를 수 있게 되므로, 탐색·새 창·권한 요청을 모두 막는다.
    """
    from PySide6.QtWebEngineCore import QWebEnginePage

    home_path = str(home.resolve()).replace('\\', '/').lower()

    class SecurePage(QWebEnginePage):
        def acceptNavigationRequest(self, url, nav_type, is_main_frame):
            if url.isLocalFile() and url.toLocalFile().replace('\\', '/').lower() == home_path:
                return True                                   # 앱 첫 화면(쿼리만 다른 것 포함)
            if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked \
                    and url.scheme() in ('http', 'https'):
                QDesktopServices.openUrl(url)                 # 링크는 기본 브라우저로
            return False                                      # 그 밖의 이동은 전부 차단

        def createWindow(self, _type):
            return None                                       # window.open / 새 창 차단

    page = SecurePage(profile, parent)
    # 카메라·마이크·위치·알림 등 권한 요청은 모두 거부
    try:
        page.permissionRequested.connect(lambda perm: perm.deny())
    except AttributeError:                                    # Qt < 6.8
        try:
            page.featurePermissionRequested.connect(
                lambda origin, feature: page.setFeaturePermission(
                    origin, feature, QWebEnginePage.PermissionPolicy.PermissionDeniedByUser))
        except AttributeError:
            pass
    return page


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
        from PySide6.QtWebEngineWidgets import QWebEngineView

        cfg = Config.get()
        theme = 'light' if cfg.theme == 'light' else 'dark'

        self.setWindowTitle('HI 21cm 전파망원경')
        icon_png = assets_dir() / 'icons' / 'app.png'
        if icon_png.is_file():
            self.setWindowIcon(QIcon(str(icon_png)))
        self.resize(1480, 920)
        self.setMinimumSize(1080, 680)
        self.setStyleSheet(f'QMainWindow{{background:{_BG[theme]};}}')

        index = WEB_DIR / 'index.html'
        self.view = QWebEngineView(self)
        self.view.setAcceptDrops(False)        # 파일·링크를 끌어다 놓아 다른 페이지로 바뀌는 것 방지
        self.view.setContextMenuPolicy(
            Qt.ContextMenuPolicy.DefaultContextMenu if os.environ.get('RWA_DEBUG')
            else Qt.ContextMenuPolicy.NoContextMenu)
        # 디스크에 캐시·쿠키를 남기지 않는 일회용 프로필 + 잠긴 페이지
        self._profile = QWebEngineProfile(self)
        page = _make_secure_page(self._profile, self.view, index)
        self.view.setPage(page)
        page.setBackgroundColor(QColor(_BG[theme]))
        s = page.settings()
        W = QWebEngineSettings.WebAttribute
        s.setAttribute(W.LocalContentCanAccessFileUrls, True)     # web/ 안의 글꼴·스크립트 읽기
        s.setAttribute(W.LocalContentCanAccessRemoteUrls, False)  # 인터넷 접근 없음
        s.setAttribute(W.JavascriptCanOpenWindows, False)
        s.setAttribute(W.JavascriptCanAccessClipboard, False)
        s.setAttribute(W.PluginsEnabled, False)
        s.setAttribute(W.PdfViewerEnabled, False)
        s.setAttribute(W.ScrollAnimatorEnabled, True)

        self.bridge = Bridge(self)
        self.channel = QWebChannel(page)
        self.channel.registerObject('backend', self.bridge)
        page.setWebChannel(self.channel)

        url = QUrl.fromLocalFile(str(index))
        url.setQuery(f'theme={theme}')
        self.view.setUrl(url)
        self.setCentralWidget(self.view)

        self._devtools = None
        QShortcut(QKeySequence('F12'), self, activated=self.open_devtools)
        _set_dark_titlebar(self, theme == 'dark')

    def closeEvent(self, e):
        # 관측 계산 프로세스 정리
        try:
            self.bridge.shutdown()
        except Exception:
            pass
        super().closeEvent(e)

    def open_devtools(self):
        if not os.environ.get('RWA_DEBUG'):
            return
        from PySide6.QtWebEngineWidgets import QWebEngineView
        if self._devtools is None:
            self._devtools = QWebEngineView()
            self._devtools.setWindowTitle('DevTools')
            self._devtools.resize(1100, 760)
            self.view.page().setDevToolsPage(self._devtools.page())
        self._devtools.show()


def chromium_flags(gpu_accel: str) -> str:
    """그래픽 가속 설정 → Chromium(Qt WebEngine) 실행 옵션.

    auto : GPU 사용. 오래된 내장 그래픽(LattePanda 의 Intel HD 등)은 Chromium 이
           '차단 목록'에 올려 캔버스를 CPU 로 그리는데, 이를 무시하고 GPU 로 그리게 한다.
    off  : 소프트웨어 렌더링 (드라이버 문제로 화면이 깨질 때). RWA_SOFTWARE_GL=1 도 같음.
    """
    flags = os.environ.get('QTWEBENGINE_CHROMIUM_FLAGS', '').split()
    if gpu_accel == 'off' or os.environ.get('RWA_SOFTWARE_GL'):
        flags += ['--disable-gpu', '--disable-gpu-compositing']
    else:
        flags += ['--ignore-gpu-blocklist', '--enable-gpu-rasterization',
                  '--enable-accelerated-2d-canvas']
    return ' '.join(dict.fromkeys(flags))


def main():
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass
    # Qt WebEngine 옵션은 QApplication 을 만들기 전에 정해야 한다
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = chromium_flags(Config.get().gpu_accel)

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName('RWA HI21cm')
    app.setOrganizationName('Team RWA')
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
