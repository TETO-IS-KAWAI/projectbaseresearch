"""
compute.py
관측 처리(FFT·도플러·밴드패스)를 '별도 프로세스'에서 돌리는 계산 풀

왜 따로 돌리나
  파이썬 스레드는 GIL 때문에 무거운 계산 중에 화면 쪽(Qt 메인 스레드·QWebChannel)과
  CPU 를 나눠 써서 버벅일 수 있다. 계산 전용 프로세스를 하나 띄워 두면
  다른 CPU 코어에서 돌아가므로 지도·애니메이션이 끊기지 않는다.

  · 프로세스는 앱 시작 후 미리 하나 띄워(numpy·astropy import) 첫 관측도 빠르게 한다.
  · 진행 단계는 multiprocessing.Queue 로 받아 화면 파이프라인 표시로 넘긴다.
  · 프로세스를 못 띄우거나 죽으면 자동으로 예전처럼 스레드에서 계산한다(폴백).

PyInstaller 빌드에서는 run.pyw 의 multiprocessing.freeze_support() 가 필요하다.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import queue
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from typing import Callable, Optional

_q = None   # 자식 프로세스 안의 진행 큐


def _init(q) -> None:
    """자식 프로세스 초기화: 진행 큐 보관 + 무거운 모듈 미리 import."""
    global _q
    _q = q
    import numpy  # noqa: F401
    import astro_processing  # noqa: F401  (astropy·scipy 포함)


def _warm() -> int:
    return os.getpid()


def _run(params: dict) -> dict:
    from astro_processing import process_observation
    def step(name):
        try:
            _q.put_nowait(name)
        except Exception:
            pass
    return process_observation(**params, progress=step)


class ComputePool:
    """관측 처리 전용 프로세스 1개."""

    def __init__(self):
        self._lock = threading.Lock()
        self._pool: Optional[ProcessPoolExecutor] = None
        self._q = None
        self.mode = 'thread'          # 실제로 쓰고 있는 방식: 'process' | 'thread'
        self.error: Optional[str] = None

    def start(self) -> None:
        """(백그라운드에서) 계산 프로세스를 띄워 둔다. 실패하면 스레드 모드로 남는다."""
        with self._lock:
            if self._pool is not None or os.environ.get('RWA_NO_SUBPROCESS'):
                return
            try:
                ctx = mp.get_context('spawn')
                self._q = ctx.Queue()
                self._pool = ProcessPoolExecutor(
                    max_workers=1, mp_context=ctx, initializer=_init, initargs=(self._q,))
                self._pool.submit(_warm).result(timeout=120)
                self.mode = 'process'
            except Exception as e:                 # 프로세스를 못 띄우는 환경 → 스레드 폴백
                self.error = f'{type(e).__name__}: {e}'
                self._shutdown()
                self.mode = 'thread'

    def run(self, params: dict, progress: Callable[[str], None]) -> dict:
        if self._pool is None:
            self.start()
        if self._pool is not None:
            try:
                fut = self._pool.submit(_run, params)
                while True:
                    try:
                        progress(self._q.get(timeout=0.04))
                    except queue.Empty:
                        if fut.done():
                            break
                while True:                        # 남은 진행 메시지 비우기
                    try:
                        progress(self._q.get_nowait())
                    except queue.Empty:
                        break
                return fut.result()
            except BrokenProcessPool as e:          # 자식이 죽음 → 이번만 스레드로, 다음엔 새로 띄움
                self.error = f'계산 프로세스 종료: {e}'
                self._shutdown()
        from astro_processing import process_observation
        self.mode = 'thread' if self._pool is None else self.mode
        return process_observation(**params, progress=progress)

    def info(self) -> dict:
        return dict(mode=self.mode, cpus=os.cpu_count() or 1, error=self.error)

    def _shutdown(self) -> None:
        if self._pool is not None:
            try:
                self._pool.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
        self._pool = None

    def close(self) -> None:
        with self._lock:
            self._shutdown()
