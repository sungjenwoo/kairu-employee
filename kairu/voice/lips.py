"""The camera check (voice.camera: true; the owner's GO of 16 Nov 2026, VOICE.md "The camera check").

The laptop's mic hears everyone in the room: people talking nearby were taken as Kairu's owner. With this on, while the
mic is on, the camera watches the owner's mouth; when an utterance ends, it says whether the owner's lips were moving
during it:

    "yours"       a face was there and its lips moved for enough of the utterance
    "lips still"  a face was there, but its lips did not move: someone else talked
    "no face"     no face in front of the camera for most of it
    "unchecked"   the camera had no pictures for that time (it can't say)

An utterance that is not "yours" is never an order, a wake or an answer; "Kairu, stop" still works from anyone (the same
rule as voice.only_my_voice). What it cannot do: when the owner and someone else talk at the same moment, the sound is
still mixed; only a mic close to the mouth helps then.

The pictures: one small grey frame at a time, held in memory, compared with the one before and dropped. Never written to
disk, never sent, never shown. The camera is opened only while the listener runs (the mic is on) and released when it
ends. OpenCV (opencv-python) finds the face; without it, or without a camera, there is no camera check and Kairu says so.
"""

import sys
import threading
import time
from collections import deque

FPS = 10
KEEP_SECONDS = 30
MIN_MOTION = 2.5  # mean change of a grey mouth picture (0-255) that is movement, at the least
OVER_STILL = 2.0  # and this many times the mouth's own change when it is still (from the last KEEP_SECONDS)
MOVING_SHARE = 0.3  # lips moving in this share of the utterance's frames: it was you
FACE_SHARE = 0.4  # a face in fewer of its frames than this: "no face"
EDGE_SECONDS = 0.25  # a little before and after the utterance is looked at too (the mic and the camera aren't in step)
MOUTH = (0.62, 0.95, 0.2, 0.8)  # the mouth inside a face's box: top, bottom, left, right, as shares of the box


class CameraProblem(Exception):
    pass


def load_cv2():
    try:
        import cv2
    except ImportError:
        raise CameraProblem("the camera check needs OpenCV: py -3.12 -m pip install opencv-python") from None
    return cv2


class LipWatch:
    def __init__(self, index: int = 0, cv2=None, clock=time.monotonic, sleep=time.sleep):
        self.cv2 = cv2 or load_cv2()
        self.index, self.clock, self.sleep = index, clock, sleep
        self.samples: deque = deque(maxlen=FPS * KEEP_SECONDS)  # (time, face seen, mouth movement)
        self._stop = threading.Event()
        self._thread = None
        self.capture = None
        self.problem = ""

    def start(self) -> "LipWatch":
        cv2 = self.cv2
        backend = getattr(cv2, "CAP_DSHOW", 0) if sys.platform == "win32" else 0
        self.capture = cv2.VideoCapture(self.index, backend) if backend else cv2.VideoCapture(self.index)
        if not self.capture or not self.capture.isOpened():
            raise CameraProblem("the camera could not be opened (in use by another app, or blocked in Windows' privacy settings)")
        self.capture.set(getattr(cv2, "CAP_PROP_FRAME_WIDTH", 3), 320)
        self.capture.set(getattr(cv2, "CAP_PROP_FRAME_HEIGHT", 4), 240)
        self.faces = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self._thread = threading.Thread(target=self._watch, name="kairu-lips", daemon=True)
        self._thread.start()
        return self

    def _watch(self) -> None:
        before = None
        while not self._stop.is_set():
            started = self.clock()
            try:
                before = self.look(before)
            except Exception as error:  # one bad frame never ends the listener
                self.problem = f"camera: {type(error).__name__}"
            self.sleep(max(0.0, 1 / FPS - (self.clock() - started)))

    def look(self, before):
        """One frame: is a face there, and how much its mouth changed since the last frame. Returns this mouth picture."""
        cv2 = self.cv2
        ok, frame = self.capture.read()
        now = self.clock()
        if not ok or frame is None:
            return None
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if getattr(frame, "ndim", 2) == 3 else frame
        found = self.faces.detectMultiScale(grey, 1.2, 5, minSize=(60, 60))
        if len(found) == 0:
            self.samples.append((now, False, 0.0))
            return None
        x, y, w, h = max(found, key=lambda box: box[2] * box[3])  # the nearest face: the biggest
        top, bottom, left, right = MOUTH
        mouth = grey[int(y + top * h):int(y + bottom * h), int(x + left * w):int(x + right * w)]
        mouth = cv2.resize(mouth, (48, 24)).astype("float32")
        moved = float(abs(mouth - before).mean()) if before is not None and before.shape == mouth.shape else 0.0
        self.samples.append((now, True, moved))
        return mouth

    def verdict(self, start: float, end: float) -> str:
        samples = [s for s in list(self.samples) if start - EDGE_SECONDS <= s[0] <= end + EDGE_SECONDS]
        if len(samples) < 3:
            return "unchecked"
        faces = [moved for _, face, moved in samples if face]
        if len(faces) < FACE_SHARE * len(samples):
            return "no face"
        still = sorted(moved for _, face, moved in self.samples if face)
        baseline = still[len(still) // 5] if still else 0.0  # the mouth's change when it is still: its lowest fifth
        line = max(MIN_MOTION, OVER_STILL * baseline)
        moving = sum(moved > line for moved in faces)
        return "yours" if moving >= MOVING_SHARE * len(faces) else "lips still"

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        if self.capture is not None:
            self.capture.release()
        self.samples.clear()
