"""
scripts/dev_server.py — UI 개발용 로컬 서버

데스크톱 앱(main_app.py)과 똑같은 api.py 를 HTTP 로 노출해서, web/ 화면을
일반 브라우저에서 열어 보고 고칠 수 있게 한다.  (배포에는 쓰이지 않음)

    python scripts/dev_server.py            → http://127.0.0.1:8765/
    python scripts/dev_server.py --port 9000

파일 대화상자는 브라우저에서 띄울 수 없으므로 dialog_* 요청에는
{'path': None, 'dev': True} 를 돌려주고, 화면 쪽이 경로 입력창으로 대신한다.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api import Api  # noqa: E402

WEB = ROOT / 'web'
_events: list = []
_lock = threading.Lock()        # API 호출 직렬화 (데스크톱 앱의 작업 스레드 1개와 동일)
_ev_lock = threading.Lock()     # 진행률 이벤트 큐


def _push(name, payload):
    with _ev_lock:
        _events.append((name, payload))


api = Api(emit=_push)

mimetypes.add_type('font/woff2', '.woff2')
mimetypes.add_type('text/javascript', '.js')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _local_only(self) -> bool:
        """DNS 리바인딩·다른 사이트의 요청 차단: Host 는 127.0.0.1/localhost,
        Origin 이 있으면 이 서버 자신이어야 한다."""
        host = (self.headers.get('Host') or '').split(':')[0]
        if host not in ('127.0.0.1', 'localhost'):
            return False
        origin = self.headers.get('Origin')
        port = self.server.server_address[1]
        return origin is None or origin in (f'http://127.0.0.1:{port}', f'http://localhost:{port}')

    def do_GET(self):
        if not self._local_only():
            return self._send(403, b'forbidden', 'text/plain')
        path = self.path.split('?', 1)[0]
        if path == '/api/events':
            with _ev_lock:
                ev = list(_events); _events.clear()
            return self._send(200, json.dumps(ev, ensure_ascii=False).encode(), 'application/json')
        rel = 'index.html' if path in ('', '/') else path.lstrip('/')
        f = (WEB / rel).resolve()
        if WEB not in f.parents or not f.is_file():
            return self._send(404, b'not found', 'text/plain')
        ctype = mimetypes.guess_type(str(f))[0] or 'application/octet-stream'
        self._send(200, f.read_bytes(), ctype)

    def do_POST(self):
        if self.path != '/api':
            return self._send(404, b'not found', 'text/plain')
        if not self._local_only() or 'application/json' not in (self.headers.get('Content-Type') or ''):
            return self._send(403, b'forbidden', 'text/plain')
        n = int(self.headers.get('Content-Length', 0))
        req = json.loads(self.rfile.read(n) or b'{}')
        method, args = req.get('method', ''), req.get('args') or {}
        if method.startswith('dialog_') or method.startswith('window_'):
            res = {'ok': True, 'data': {'path': None, 'dev': True}}
        else:
            with _lock:
                res = api.dispatch(method, args)
        self._send(200, json.dumps(res, ensure_ascii=False).encode(), 'application/json')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765)
    a = ap.parse_args()
    srv = ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
    print(f'UI dev server: http://127.0.0.1:{a.port}/')
    srv.serve_forever()


if __name__ == '__main__':
    main()
