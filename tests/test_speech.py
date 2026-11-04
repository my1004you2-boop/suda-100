import numpy as np

from talk.speech import SAMPLE_RATE, SPEED_RATE, Recorder, Transcriber


class FakeStream:
    def __init__(self, samples, callback, **kw):
        self.samples, self.callback = samples, callback
        self.closed = False

    def start(self):
        self.callback(np.ones((self.samples, 1), dtype="float32"), self.samples, None, None)

    def stop(self):
        pass

    def close(self):
        self.closed = True


def stream_of(samples):
    def factory(**kw):
        factory.last = FakeStream(samples, **kw)
        return factory.last
    return factory


def test_speed_rates():
    assert SPEED_RATE == {"slow": "-25%", "normal": "+0%", "native": "+15%"}


def test_recording_returns_mono_audio():
    factory = stream_of(SAMPLE_RATE)  # 1초
    rec = Recorder(None, stream_factory=factory)
    rec.start()
    audio = rec.stop()
    assert audio.shape == (SAMPLE_RATE,) and audio.dtype == np.float32
    assert factory.last.closed


def test_short_recording_returns_empty():
    rec = Recorder(None, stream_factory=stream_of(int(SAMPLE_RATE * 0.2)))
    rec.start()
    assert rec.stop().size == 0


def test_transcribe_joins_segments():
    class Seg:
        def __init__(self, text):
            self.text = text

    class FakeModel:
        def transcribe(self, audio, **kw):
            FakeModel.kw = kw
            return iter([Seg(" I went to "), Seg("the park. ")]), None

    t = Transcriber("base.en", model_factory=lambda name: FakeModel())
    assert not t.ready
    assert t.transcribe(np.zeros(16000, dtype="float32")) == "I went to the park."
    assert t.ready
    assert FakeModel.kw["language"] == "en" and FakeModel.kw["beam_size"] == 1
    assert FakeModel.kw["condition_on_previous_text"] is False
    assert FakeModel.kw["vad_filter"] is True  # 무음에서 "you" 같은 헛인식 방지
