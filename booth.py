"""포토부스의 동작 순서(상태 머신). 화면(창)과 분리해서 순서 로직만 담당한다.

HOME(초기) -> SELECT(1컷/4컷 선택) -> LIVE(미리보기, 필터 선택)
  -> [COUNTDOWN(3,2,1) -> FLASH(촬영) -> INTERVAL(다음 컷 준비)] x 컷 수
  -> EJECT(인쇄 + 배출 연출) -> DONE(완료) -> HOME

왜 상태로 나누는가: '지금 무엇을 하는 중인지'를 한 변수(state)로 관리하면
그 상태에서 의미 있는 입력만 받고 나머지는 무시할 수 있다 (촬영 중 중복 입력 문제 해결).
4컷은 사용자가 한 번만 누르면 COUNTDOWN~INTERVAL을 컷 수만큼 스스로 반복한다.
인쇄는 시간이 걸리므로 별도 스레드로 돌려 화면이 멈추지 않게 한다.
"""
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto

from PIL import Image

import config
from hand_gesture import Stabilizer
from image_utils import bgr_to_pil
from strip import compose_strip

# 배출 연출의 시간표(초). 화면(render.py)도 같은 값을 쓴다.
EJECT_SLIDE = 1.2        # 스트립이 슬롯에서 나오며 튕기는 시간
EJECT_DEVELOP = 2.7      # 하얗게 흐린 상태에서 선명해지는 시간
EJECT_HOLD = 1.0         # 완료 표시(표시등, 반짝임)를 보여 주는 시간
EJECT_TOTAL = EJECT_SLIDE + EJECT_DEVELOP + EJECT_HOLD

MODES = (1, 4)           # 지원하는 컷 수
THUMB_SIZE = (96, 72)


class State(Enum):
    HOME = auto()
    SELECT = auto()
    LIVE = auto()
    COUNTDOWN = auto()
    FLASH = auto()
    INTERVAL = auto()
    EJECT = auto()
    DONE = auto()


@dataclass
class Frame:
    """화면을 그리는 데 필요한 모든 정보. render.py는 이것만 보고 그린다."""
    state: State
    t: float = 0.0             # 현재 상태에 들어온 뒤 지난 시간(초) -> 애니메이션 계산용
    image: object = None       # 사진 칸에 보여 줄 PIL 이미지
    filter_name: str = "basic"
    mode: int = 4              # 컷 수
    shots_done: int = 0        # 지금까지 찍은 장수
    remaining: float = 0.0     # 카운트다운 남은 시간(초)
    thumbs: tuple = ()         # 찍은 사진의 작은 미리보기
    strip: object = None       # 인쇄될 스트립(1비트 이미지)
    notice: str = ""           # 오류/안내 (잠깐 표시)
    devices: dict = field(default_factory=dict)


class Booth:
    def __init__(self, camera, button, printer, gesture, filter_bank):
        self.camera, self.button, self.printer = camera, button, printer
        self.gesture, self.filters = gesture, filter_bank
        self.state = State.HOME
        self.mode = getattr(config, "DEFAULT_MODE", 4)
        self.filter_name = "basic"
        self.devices = {
            "camera": getattr(camera, "label", "USB camera" if getattr(camera, "is_real", False) else "FAKE"),
            "camera_ok": bool(getattr(camera, "is_real", False)),
            "printer_ok": bool(getattr(printer, "is_real", False)),
            "hand_ok": bool(getattr(gesture, "available", False)),
        }
        self._t0 = None                          # 현재 상태에 들어온 시각
        self._stab = Stabilizer(initial="basic")
        self._last_gesture_filter = "basic"      # 마지막으로 안정적으로 인식된 손 모양이 가리키는 필터
        self._n = 0
        self._raw = None                         # 촬영 순간의 원본 프레임
        self._shots, self._thumbs = [], []
        self._strip = None
        self._print_thread = None
        self._print_error = ""
        self._notice, self._notice_until = "", 0.0

    # ---------- 내부 도구 ----------
    def _go(self, state, now):
        self.state, self._t0 = state, now

    def _set_notice(self, text, now, seconds=3.0):
        self._notice, self._notice_until = text, now + seconds

    @staticmethod
    def _mirror(img):
        return img.transpose(Image.FLIP_LEFT_RIGHT) if config.MIRROR_PREVIEW else img

    def _update_filter_from_hand(self, frame_bgr):
        """N프레임마다 한 번만 손을 인식하고, 손 모양이 '바뀐 순간'에만 필터를 바꾼다.

        바뀐 순간에만 반영하는 이유: 손이 안 보일 때마다 기본 필터로 되돌리면
        화면에서 직접 고른 필터가 바로 덮어써지기 때문이다.
        """
        self._n += 1
        if self._n % config.DETECT_EVERY_N_FRAMES or not self.gesture.available:
            return
        fingers = self.gesture.detect(frame_bgr)
        if fingers is None:
            return
        stable = self._stab.update(config.FILTER_BY_FINGERS.get(fingers, "basic"))
        if stable != self._last_gesture_filter:
            self._last_gesture_filter = stable
            self.filter_name = stable

    def _clear_session(self):
        """찍은 사진을 메모리에서 지운다 (다음 사람에게 이전 사진이 보이지 않게)."""
        self._raw, self._strip = None, None
        self._shots, self._thumbs = [], []

    def _start_session(self, now):
        self._clear_session()
        self._go(State.COUNTDOWN, now)

    def _finish_shot(self, now):
        """촬영한 한 장에 필터를 적용해 보관하고, 다음 컷 또는 인쇄로 넘어간다."""
        filtered, msg = self.filters.apply(self.filter_name, bgr_to_pil(self._raw))
        if msg:
            self._set_notice(msg.upper(), now)
        self._shots.append(filtered)
        thumb = self._mirror(filtered).copy()
        thumb.thumbnail(THUMB_SIZE)
        self._thumbs.append(thumb)
        if len(self._shots) < self.mode:
            self._go(State.INTERVAL, now)
            return
        self._strip = compose_strip(self._shots)
        self._print_error = ""
        self._print_thread = threading.Thread(target=self._print_job, args=(self._strip,), daemon=True)
        self._print_thread.start()
        self._go(State.EJECT, now)

    def _print_job(self, strip):
        try:
            self.printer.print_image(strip)
        except Exception as e:
            self._print_error = f"PRINTER ERROR: {e}"

    # ---------- 입력 ----------
    def handle(self, action, now=None):
        """터치/키보드 동작을 처리한다. 지금 상태에서 의미 없는 동작은 무시한다.

        action: ("primary",) 시작·다음 / ("mode", 1|4) / ("filter", 이름) / ("back",)
        """
        now = time.monotonic() if now is None else now
        if self._t0 is None:
            self._t0 = now
        kind = action[0]
        s = self.state
        if kind == "primary":
            if s is State.HOME:
                self._go(State.SELECT, now)
            elif s is State.SELECT:
                self._go(State.LIVE, now)
            elif s is State.LIVE:
                self._start_session(now)
            elif s is State.DONE:
                self._clear_session()
                self._go(State.HOME, now)
        elif kind == "mode" and s is State.SELECT and action[1] in MODES:
            self.mode = action[1]
            self._go(State.LIVE, now)
        elif kind == "filter" and s is State.LIVE and action[1] in config.FILTER_LABELS:
            self.filter_name = action[1]
            self._t0 = now                                   # 조작이 있었으니 대기 시간 초기화
        elif kind == "back":
            if s is State.LIVE:
                self._go(State.SELECT, now)
            elif s is State.SELECT:
                self._go(State.HOME, now)

    def select_filter(self, name):
        self.handle(("filter", name))

    # ---------- 프레임마다 호출 ----------
    def tick(self, now=None):
        now = time.monotonic() if now is None else now
        if self._t0 is None:
            self._t0 = now
        if self.button.consume():                            # 물리 버튼/SPACE = "시작·다음"
            self.handle(("primary",), now)
        frame_bgr = self.camera.read()
        image = self._step(frame_bgr, now)
        notice = self._notice if now < self._notice_until else ""
        if frame_bgr is None and self.state in (State.LIVE, State.COUNTDOWN):
            notice = "CAMERA ERROR"
        remaining = max(0.0, config.COUNTDOWN_SECONDS - (now - self._t0)) if self.state is State.COUNTDOWN else 0.0
        return Frame(state=self.state, t=now - self._t0, image=image, filter_name=self.filter_name,
                     mode=self.mode, shots_done=len(self._shots), remaining=remaining,
                     thumbs=tuple(self._thumbs), strip=self._strip, notice=notice, devices=self.devices)

    def _step(self, frame_bgr, now):
        """상태별 처리. 사진 칸에 보여 줄 이미지를 반환한다."""
        s, t = self.state, now - self._t0
        idle_limit = getattr(config, "IDLE_SECONDS", 60)

        if s is State.HOME:
            return None

        if s is State.SELECT:
            if t >= idle_limit:
                self._go(State.HOME, now)
            return None

        if s is State.LIVE:
            if frame_bgr is None:
                return None
            self._update_filter_from_hand(frame_bgr)
            if t >= idle_limit:                              # 아무도 없으면 초기 화면으로
                self._go(State.HOME, now)
            return self._mirror(bgr_to_pil(frame_bgr))

        if s is State.COUNTDOWN:
            if frame_bgr is None:                            # 촬영 도중 카메라가 끊기면 촬영을 취소한다
                if t >= config.COUNTDOWN_SECONDS:
                    self._clear_session()
                    self._set_notice("CAMERA ERROR", now)
                    self._go(State.LIVE, now)
                return None
            if t >= config.COUNTDOWN_SECONDS:
                self._raw = frame_bgr                        # 이 순간의 프레임이 사진이 된다
                self._go(State.FLASH, now)
            return self._mirror(bgr_to_pil(frame_bgr))

        if s is State.FLASH:
            image = self._mirror(bgr_to_pil(self._raw))
            if t >= getattr(config, "FLASH_SECONDS", 0.12):
                self._finish_shot(now)
            return image

        if s is State.INTERVAL:                              # 방금 찍힌 사진을 잠깐 보여 준다
            if t >= getattr(config, "INTERVAL_SECONDS", 1.2):
                self._go(State.COUNTDOWN, now)
            return self._mirror(self._shots[-1])

        if s is State.EJECT:
            if t >= EJECT_TOTAL and not self._print_thread.is_alive():
                if self._print_error:
                    self._set_notice(self._print_error, now, 5.0)
                self._go(State.DONE, now)
            return None

        if s is State.DONE:
            if t >= getattr(config, "DONE_SECONDS", 10):
                self._clear_session()
                self._go(State.HOME, now)
            return None
        return None
