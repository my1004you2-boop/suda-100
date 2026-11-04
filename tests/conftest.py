import pytest

from talk.config import Settings
from talk.llm import FakeLLM
from talk.store import Store


@pytest.fixture
def make_app(tmp_path):
    """FakeLLM과 임시 저장소로 앱을 만든다. 응답 목록은 테스트가 정한다."""
    from talk.ui.app import App, Services

    apps = []

    def factory(responses=(), settings=None, store=None):
        fake = FakeLLM(list(responses))
        services = Services(
            store=store or Store(tmp_path / "data"),
            settings=settings or Settings(api_key="test-key"),
            llm_factory=lambda s: fake,
            speech_enabled=False,
            run_startup=False,
            settings_path=tmp_path / "settings.json",
        )
        app = App(services)
        app.fake_llm = fake
        apps.append(app)
        return app

    yield factory
    for app in apps:
        try:
            app.destroy()
        except Exception:
            pass


def pump(app, until=lambda: True, timeout=5.0):
    """작업 스레드 결과가 UI에 반영될 때까지 이벤트 루프를 돌린다."""
    import time

    end = time.time() + timeout
    while time.time() < end:
        app.update()
        if until():
            return True
        time.sleep(0.02)
    return False
