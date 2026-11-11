"""포토부스의 동작 순서(상태 머신). 화면(Tkinter)과 분리해서 순서 로직만 담당한다.

IDLE(대기) -> 버튼 -> COUNTDOWN(카운트다운) -> 촬영 -> RESULT(결과 표시) -> PRINTING(인쇄) -> IDLE

왜 상태로 나누는가: '지금 무엇을 하는 중인지'를 한 변수(state)로 관리하면
촬영/인쇄 중 버튼이 또 눌려도 IDLE이 아닌 상태에서는 무시할 수 있다 (중복 입력 문제 해결).
인쇄는 시간이 걸리므로 별도 스레드로 돌려 화면이 멈추지 않게 한다.
"""
import math
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto

from PIL import Image

import config
from hand_gesture import Stabilizer
from image_utils import bgr_to_pil, to_printable


class State(Enum):
    IDLE = auto()
    COUNTDOWN = auto()
    RESULT = auto()
    PRINTING = auto()


@dataclass
class Frame:
    image: object          # 화면에 보여 줄 PIL 이미지
    state: State
    filter_label: str = ""
    big_text: str = ""     # 카운트다운 숫자
    hint: str = ""
    notice: str = ""       # 오류/안내 (잠깐 표시)


class Booth:
    def __init__(self, camera, button, printer, gesture, filter_bank):
        self.camera, self.button, self.printer = camera, button, printer
        self.gesture, self.filters = gesture, filter_bank
        self.state = State.IDLE
        self.filter_name = "basic"
        self._stab = Stabilizer(initial="basic")
        self._n = 0
        self._countdown_end = 0.0
        self._result_until = 0.0
        self._print_thread = None
        self._printable = None
        self._result_img = None
        self._notice, self._notice_until = "", 0.0
        self._print_error = ""

    # ---------- 내부 도구 ----------
    def _set_notice(self, text, now, seconds=3.0):
        self._notice, self._notice_until = text, now + seconds

    def _preview(self, frame_bgr):
        img = bgr_to_pil(frame_bgr)
        return img.transpose(Image.FLIP_LEFT_RIGHT) if config.MIRROR_PREVIEW else img

    def _label(self):
        return config.FILTER_LABELS.get(self.filter_name, self.filter_name.upper())

    def _update_filter_from_hand(self, frame_bgr):
        """N프레임마다 한 번만 손을 인식하고, 안정적으로 같은 결과일 때만 필터를 바꾼다."""
        self._n += 1
        if self._n % config.DETECT_EVERY_N_FRAMES or not self.gesture.available:
            return
        fingers = self.gesture.detect(frame_bgr)
        if fingers is not None:
            self.filter_name = self._stab.update(config.FILTER_BY_FINGERS.get(fingers, "basic"))

    def _capture(self, frame_bgr, now):
        """촬영 -> 필터 적용 -> 인쇄용 1비트 변환. 화면에는 '실제 인쇄될 모습'을 보여 준다."""
        filtered, msg = self.filters.apply(self.filter_name, bgr_to_pil(frame_bgr))
        self._printable = to_printable(filtered)
        self._result_img = self._printable.convert("RGB")
        if msg:
            self._set_notice(msg, now)
        self.state = State.RESULT
        self._result_until = now + config.RESULT_SECONDS

    def _print_job(self):
        try:
            self.printer.print_image(self._printable)
        except Exception as e:
            self._print_error = f"Printer error: {e}"

    # ---------- 프레임마다 호출 ----------
    def tick(self, now=None):
        now = time.monotonic() if now is None else now
        frame = self.camera.read()
        pressed = self.button.consume()          # 어떤 상태에서든 눌림은 소비 -> IDLE이 아니면 버려짐
        notice = self._notice if now < self._notice_until else ""

        if frame is None:
            return Frame(None, self.state, notice="Camera error")

        if self.state is State.IDLE:
            self._update_filter_from_hand(frame)
            if pressed:
                self.state = State.COUNTDOWN
                self._countdown_end = now + config.COUNTDOWN_SECONDS
            return Frame(self._preview(frame), self.state, self._label(), hint="Press the button (SPACE)", notice=notice)

        if self.state is State.COUNTDOWN:
            remaining = self._countdown_end - now
            if remaining <= 0:
                self._capture(frame, now)
                return Frame(self._result_img, self.state, self._label(), notice=self._notice)
            return Frame(self._preview(frame), self.state, self._label(), big_text=str(math.ceil(remaining)))

        if self.state is State.RESULT:
            if now >= self._result_until:
                self._print_error = ""
                self._print_thread = threading.Thread(target=self._print_job, daemon=True)
                self._print_thread.start()
                self.state = State.PRINTING
            return Frame(self._result_img, self.state, self._label(), notice=notice)

        # PRINTING
        if not self._print_thread.is_alive():
            self.state = State.IDLE
            if self._print_error:
                self._set_notice(self._print_error, now, 5.0)
        return Frame(self._result_img, self.state, self._label(), hint="Printing...")
