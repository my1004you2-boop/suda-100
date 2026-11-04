"""음성: 영어 읽어주기(edge-tts)와 말한 걸 글자로 바꾸기(faster-whisper)."""

import asyncio
import ctypes
import tempfile
import threading
import uuid
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
MIN_SECONDS = 0.3
SPEED_RATE = {"slow": "-25%", "normal": "+0%", "native": "+15%"}

_play_lock = threading.Lock()


def _synth(text: str, voice: str, rate: str) -> Path:
    import edge_tts

    path = Path(tempfile.gettempdir()) / f"talk_{uuid.uuid4().hex[:8]}.mp3"
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    try:
        asyncio.run(asyncio.wait_for(communicate.save(str(path)), timeout=15))
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def _play_mp3(path: Path) -> None:
    def mci(command):
        return ctypes.windll.winmm.mciSendStringW(command, None, 0, None)

    alias = "talk" + path.stem[-8:]
    try:
        if mci(f'open "{path}" type mpegvideo alias {alias}') != 0:
            raise OSError("mp3 재생 실패")
        try:
            mci(f"play {alias} wait")
        finally:
            mci(f"close {alias}")
    finally:
        path.unlink(missing_ok=True)


def speak(text: str, voice: str, speed: str) -> None:
    """영어 문장을 읽는다. 끝날 때까지 기다리므로 작업 스레드에서 부른다. 동시에 하나만 재생한다."""
    path = _synth(text, voice, SPEED_RATE.get(speed, "+0%"))
    with _play_lock:
        _play_mp3(path)


def list_input_devices() -> list[tuple[int, str]]:
    import sounddevice as sd

    try:
        return [(i, d["name"]) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
    except Exception:
        return []


def _default_stream(**kw):
    import sounddevice as sd

    return sd.InputStream(**kw)


class Recorder:
    def __init__(self, device: int | None, stream_factory=_default_stream):
        self.device = device
        self.stream_factory = stream_factory
        self._chunks: list[np.ndarray] = []
        self._stream = None

    def start(self) -> None:
        self._chunks = []

        def callback(indata, frames, time, status):
            self._chunks.append(indata[:, 0].copy())

        self._stream = self.stream_factory(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                           device=self.device, callback=callback)
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        audio = np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype="float32")
        if audio.size < SAMPLE_RATE * MIN_SECONDS:
            return np.zeros(0, dtype="float32")
        return audio.astype("float32")


def _default_model(name: str):
    from faster_whisper import WhisperModel

    return WhisperModel(name, device="cpu", compute_type="int8")


class Transcriber:
    def __init__(self, model_name: str, model_factory=_default_model):
        self.model_name = model_name
        self.model_factory = model_factory
        self._model = None
        self._lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        with self._lock:
            if self._model is None:
                self._model = self.model_factory(self.model_name)

    def transcribe(self, audio: np.ndarray) -> str:
        self.load()
        segments, _ = self._model.transcribe(audio, language="en", beam_size=1, condition_on_previous_text=False,
                                               vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()
