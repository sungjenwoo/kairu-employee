"""The camera check (voice.camera, VOICE.md): an utterance your lips didn't say is never yours; "Kairu, stop" still works from
anyone. A stand-in camera and face finder: no real camera is opened, nothing is shown or written."""

import types

import pytest

np = pytest.importorskip("numpy")

from kairu import config, executors  # noqa: E402
from kairu.voice import lips  # noqa: E402
from kairu.voice.whisper import Heard, WhisperHearing  # noqa: E402

BOX = (100, 60, 120, 120)  # x, y, w, h of the face the stand-in finder sees


class Camera:
    def __init__(self, frames):
        self.frames, self.released = list(frames), False

    def isOpened(self):
        return True

    def set(self, *args):
        return True

    def read(self):
        return (True, self.frames.pop(0)) if self.frames else (False, None)

    def release(self):
        self.released = True


def stand_in_cv2(frames, faces):
    camera = Camera(frames)
    found = list(faces)

    class Finder:
        def __init__(self, path):
            pass

        def detectMultiScale(self, grey, *args, **kwargs):
            return [BOX] if (found.pop(0) if found else False) else []

    def resize(picture, size):
        width, height = size
        rows = np.linspace(0, picture.shape[0] - 1, height).astype(int)
        cols = np.linspace(0, picture.shape[1] - 1, width).astype(int)
        return picture[rows][:, cols]

    return types.SimpleNamespace(VideoCapture=lambda *args: camera, CascadeClassifier=Finder, resize=resize,
                                 cvtColor=lambda frame, code: frame, COLOR_BGR2GRAY=6,
                                 data=types.SimpleNamespace(haarcascades="")), camera


def frames(count, moving):
    rng = np.random.default_rng(7)
    still = rng.integers(0, 255, (240, 320)).astype("uint8")
    out = []
    for n in range(count):
        frame = still.copy()
        if moving and 6 <= n < 16 and n % 2:  # still, then talking (frames 6-15), then still again
            x, y, w, h = BOX
            frame[int(y + 0.62 * h):int(y + 0.95 * h), int(x + 0.2 * w):int(x + 0.8 * w)] = 255 - frame[
                int(y + 0.62 * h):int(y + 0.95 * h), int(x + 0.2 * w):int(x + 0.8 * w)]  # the mouth opens and closes
        out.append(frame)
    return out


def watched(moving: bool, face: bool = True, count: int = 20) -> lips.LipWatch:
    cv2, _ = stand_in_cv2(frames(count, moving), [face] * count)
    now = [0.0]
    watch = lips.LipWatch(cv2=cv2, clock=lambda: now[0])
    watch.capture, watch.faces = cv2.VideoCapture(0), cv2.CascadeClassifier("")
    before = None
    for _ in range(count):
        before = watch.look(before)
        now[0] += 1 / lips.FPS
    return watch


def test_lips_moving_while_it_was_said_is_yours():
    watch = watched(moving=True)
    assert watch.verdict(0.6, 1.5) == "yours"
    assert watch.verdict(0.0, 0.3) == "lips still"  # before you spoke, the same face was still


def test_a_face_whose_lips_did_not_move_is_someone_else():
    assert watched(moving=False).verdict(0.2, 1.8) == "lips still"


def test_no_face_at_the_camera_is_not_yours_and_no_pictures_is_unchecked():
    assert watched(moving=True, face=False).verdict(0.2, 1.8) == "no face"
    assert watched(moving=True).verdict(50.0, 51.0) == "unchecked"


def test_the_camera_is_released_and_nothing_is_kept_when_the_mic_goes_off():
    cv2, camera = stand_in_cv2(frames(3, True), [True] * 3)
    watch = lips.LipWatch(cv2=cv2)
    watch.capture = camera
    watch.samples.append((0.0, True, 5.0))
    watch.close()
    assert camera.released and not watch.samples


def hearing_with(verdict: str) -> WhisperHearing:
    hearing = WhisperHearing(lambda sound: Heard("", False), background=False)
    hearing._lips[1] = verdict
    hearing._waiting = 1
    return hearing


@pytest.mark.parametrize("verdict", ["lips still", "no face"])
def test_an_order_your_lips_did_not_say_is_never_an_order(verdict):
    events = []
    hearing_with(verdict)._final(Heard("Kairu, open Notepad.", True), 0.0, 1, events)
    assert {"not_you": verdict} in events and not any("order" in event or "wake" in event for event in events)


def test_kairu_stop_works_from_anyone_whatever_the_camera_saw():
    events = []
    hearing_with("lips still")._final(Heard("Kairu, stop.", True), 0.0, 1, events)
    assert {"stop": True} in events


def test_your_lips_moving_lets_the_order_through_as_before():
    events = []
    hearing_with("yours")._final(Heard("Kairu, open Notepad.", True), 0.0, 1, events)
    assert any(event.get("order") == "open notepad" for event in events)


def test_voice_camera_in_config_yaml_and_from_guardian_only(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("voice:\n  camera: true\n", encoding="utf-8")
    assert config.load(path).voice_camera is True
    path.write_text("voice:\n  camera: always\n", encoding="utf-8")
    with pytest.raises(config.ConfigError):
        config.load(path)
    assert "voice_camera" in executors.EXECUTORS["voice.listen"].supplied


def test_without_opencv_kairu_says_so_once_and_hears_as_before(monkeypatch):
    from kairu.voice import listen
    told = []
    monkeypatch.setattr(lips, "load_cv2", lambda: (_ for _ in ()).throw(lips.CameraProblem("needs OpenCV")))
    monkeypatch.setattr(listen, "_tell", lambda line, events, **state: told.extend(events) or {})
    hearing = WhisperHearing(lambda sound: Heard("", False), background=False)
    assert listen._camera(None, hearing) is None and hearing.lips is None
    assert told and "No camera check" in told[0]["problem"]


def test_the_bar_says_why_it_did_nothing():
    from kairu.bar.voice import NOT_YOU
    assert "lips" in NOT_YOU["lips still"] and "camera" in NOT_YOU["no face"]
