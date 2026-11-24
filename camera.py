"""카메라 입력. 세 가지 방식을 지원하고, 기본(auto)은 연결된 장치를 보고 자동으로 고른다.

  opencv : USB 웹캠(UVC). OV9726 같은 USB 카메라, Mac 내장 웹캠
  rpicam : 라즈베리파이 전용 카메라 모듈(CSI 플랫 케이블). rpicam-vid 프로그램이 보내 주는 영상을 읽는다
  가상   : config.FAKE_CAMERA_IMAGE 사진 또는 회색 화면 (카메라 없이 개발할 때)

왜 rpicam-vid를 쓰는가: CSI 카메라는 OpenCV로 바로 읽히지 않고, 공식 파이썬 라이브러리(Picamera2)는
시스템 패키지라 가상환경(venv)과 numpy 버전이 충돌할 수 있다. rpicam-vid는 OS에 이미 설치된 프로그램이라
가상환경과 무관하게 동작한다. 영상은 MJPEG(JPEG 사진이 이어진 형태)로 받는다.
"""
import glob
import shutil
import subprocess
import threading
import time

import cv2
import numpy as np

import config

SOI, EOI = b"\xff\xd8", b"\xff\xd9"      # JPEG 한 장의 시작/끝 표시


def _rpicam_cmd(size, fps=30):
    override = getattr(config, "RPICAM_CMD", None)       # 테스트용으로 명령을 바꿔 끼울 수 있다
    if override:
        return list(override)
    w, h = size
    cmd = ["rpicam-vid", "-t", "0", "--nopreview", "--codec", "mjpeg",
           "--width", str(w), "--height", str(h), "--framerate", str(fps), "-o", "-"]
    return cmd + list(getattr(config, "RPICAM_EXTRA_ARGS", []))   # 예: ["--rotation", "180"]


def _choose_backend():
    name = getattr(config, "CAMERA_BACKEND", "auto")
    if name != "auto":
        return name
    if config.FAKE_CAMERA_IMAGE:
        return "opencv"
    has_usb_camera = bool(glob.glob("/dev/v4l/by-id/*"))          # USB 카메라가 꽂혀 있으면 여기에 나타난다
    if not has_usb_camera and shutil.which("rpicam-vid"):
        return "rpicam"
    return "opencv"


class RpicamStream:
    """rpicam-vid의 출력을 별도 스레드로 계속 읽어 '가장 최근 한 장'만 보관한다.

    왜 스레드인가: 화면은 30ms마다 한 장씩 가져가는데, 카메라 프로그램이 더 빨리 보내면 오래된 프레임이
    쌓여 화면이 늦어진다. 계속 읽으면서 최신 한 장만 덮어쓰면 항상 지금 모습이 보인다.
    """

    def __init__(self, cmd):
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._frame = None
        self._time = 0.0
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self):
        buf = b""
        out = self._proc.stdout
        while not self._stop.is_set():
            chunk = out.read(65536)
            if not chunk:
                break                                   # 프로그램이 끝남
            buf += chunk
            last = None
            while True:
                s = buf.find(SOI)
                if s < 0:
                    buf = buf[-1:]                      # 표시가 조각 사이에 걸쳤을 수 있어 마지막 1바이트만 남김
                    break
                e = buf.find(EOI, s + 2)
                if e < 0:
                    buf = buf[s:]                       # 아직 한 장이 다 오지 않음 -> 더 읽는다
                    break
                last = buf[s:e + 2]                     # 여러 장이 쌓였으면 마지막 한 장만 쓴다
                buf = buf[e + 2:]
            if last is not None:
                frame = cv2.imdecode(np.frombuffer(last, np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    with self._lock:
                        self._frame, self._time = frame, time.monotonic()
            if len(buf) > 4_000_000:                    # 안전장치: 이상한 데이터가 계속 쌓이는 것을 막음
                buf = b""

    def wait_first_frame(self, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self._lock:
                if self._frame is not None:
                    return True
            if self._proc.poll() is not None:           # 프로그램이 이미 종료됨 -> 기다릴 필요 없음
                return False
            time.sleep(0.05)
        return False

    def read(self):
        """최근 프레임을 반환. 일정 시간 새 프레임이 없으면(카메라 멈춤/종료) None."""
        with self._lock:
            if self._frame is None:
                return None
            if time.monotonic() - self._time > getattr(config, "CAMERA_STALE_SECONDS", 2.0):
                return None
            return self._frame.copy()

    def close(self):
        self._stop.set()
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()


class Camera:
    def __init__(self, index=config.CAMERA_INDEX, size=config.CAMERA_SIZE):
        self.size = size
        self.backend = "virtual"
        self._fake = None
        self._cap = None
        self._stream = None

        if config.FAKE_CAMERA_IMAGE:
            img = cv2.imread(config.FAKE_CAMERA_IMAGE)
            if img is not None:
                self._fake = cv2.resize(img, size)
                self.backend = "virtual (photo)"

        if self._fake is None and _choose_backend() == "rpicam":
            try:
                stream = RpicamStream(_rpicam_cmd(size))
                if stream.wait_first_frame(5.0):
                    self._stream, self.backend = stream, "rpicam (CSI camera)"
                else:
                    stream.close()
                    print("camera: rpicam-vid에서 영상이 오지 않아 USB 방식으로 시도합니다")
            except OSError as e:
                print(f"camera: rpicam-vid를 실행할 수 없어 USB 방식으로 시도합니다 ({e})")

        if self._fake is None and self._stream is None:
            cap = cv2.VideoCapture(index)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
                self._cap, self.backend = cap, "opencv (USB camera)"

        self.is_real = self._stream is not None or self._cap is not None
        self.label = self.backend if self.is_real else "FAKE (no camera)"

    def read(self):
        """BGR 프레임 1장을 반환한다. 실패하면 None."""
        if self._stream is not None:
            return self._stream.read()
        if self._cap is not None:
            ok, frame = self._cap.read()
            return frame if ok else None
        if self._fake is not None:
            return self._fake.copy()
        return np.full((self.size[1], self.size[0], 3), 90, np.uint8)   # 카메라 없음: 회색 화면

    def close(self):
        if self._stream is not None:
            self._stream.close()
        if self._cap is not None:
            self._cap.release()
