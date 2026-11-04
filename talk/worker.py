"""느린 작업(AI, 음성)을 스레드에서 돌리고, 결과는 UI 스레드에서 받는다."""

import queue
import threading
import traceback


class Worker:
    def __init__(self, root, poll_ms: int = 50):
        self.root = root
        self.poll_ms = poll_ms
        self._results: queue.Queue = queue.Queue()
        self._polling = False

    def run(self, fn, on_done=None, on_error=None) -> None:
        def task():
            try:
                self._results.put((on_done, fn(), None))
            except Exception as exc:
                self._results.put((on_error, None, exc))

        threading.Thread(target=task, daemon=True).start()
        if not self._polling:
            self._polling = True
            self.root.after(self.poll_ms, self._poll)

    def _poll(self) -> None:
        while True:
            try:
                callback, result, exc = self._results.get_nowait()
            except queue.Empty:
                break
            if callback is not None:
                try:
                    callback(exc if exc is not None else result)
                except Exception:
                    traceback.print_exc()  # 콜백 하나가 실패해도 다음 결과는 계속 받는다
        try:
            self.root.after(self.poll_ms, self._poll)
        except Exception:
            self._polling = False  # 창이 닫힘
