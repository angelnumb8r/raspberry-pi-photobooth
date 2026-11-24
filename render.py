"""화면에 그릴 한 장의 이미지를 만든다 (창 방식과 분리된 순수 이미지 처리 코드).

테마: 모노크롬 테크. 검정·차콜·실버 + 가는 선 + 기계 로그 글자.
구조: 화면은 800x480 '기준 크기'로 그린 뒤 창 크기에 맞게 NEAREST(픽셀 그대로 확대)로 키운다.
카메라 사진만 확대된 위치에 따로 붙여서 부드럽게 보이게 한다. 카운트다운 숫자와 플래시는
확대된 화면 위에 직접 덮는다.

입력 좌표는 hit_test()가 같은 배치표(아래 BOX_*)로 해석한다 -> 그림과 터치 영역이 어긋나지 않는다.
"""
import math
import os
import random
import time

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import config
from booth import EJECT_DEVELOP, EJECT_SLIDE, EJECT_TOTAL, State

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(HERE, "assets", "fonts", "PressStart2P-Regular.ttf")   # SIL OFL 1.1 (같은 폴더의 OFL.txt)

BASE_W, BASE_H = 800, 480

# ---- 색: 검정/차콜/실버 + 표시등용 색 몇 개 ----
BG = (12, 13, 15)
BG_DOT = (26, 28, 31)
PANEL = (22, 24, 27)
LINE = (66, 70, 76)
SILVER = (176, 183, 192)
TEXT = (228, 232, 237)
DIM = (112, 118, 127)
LED_OK = (110, 245, 170)
LED_BUSY = (255, 184, 64)
ERR = (255, 96, 96)

FILTER_ORDER = ["basic", "contrast", "cat", "sketch"]
FILTER_NAMES = {"basic": "BASIC", "contrast": "CONTRAST", "cat": "CAT", "sketch": "SKETCH"}

# ---- 배치표 (기준 800x480 좌표). 그리기와 터치가 같은 값을 쓴다 ----
PHOTO_BOX = (40, 64, 520, 424)                       # 480x360 (카메라 4:3)
BOX_CHIPS = {name: (548, 84 + i * 44, 784, 120 + i * 44) for i, name in enumerate(FILTER_ORDER)}
BOX_SHUTTER = (548, 292, 784, 352)
BOX_BACK_LIVE = (548, 364, 784, 404)
BOX_CARD = {1: (120, 120, 380, 360), 4: (420, 120, 680, 360)}
BOX_BACK_SELECT = (320, 392, 480, 432)
SLOT = (240, 60, 560, 70)                            # 배출구 (가로 320)
STRIP_MAX = (240, 300)                               # 스트립이 그려지는 최대 크기
STRIP_TOP = SLOT[1] + 4

_fonts = {}


def _font(px):
    """픽셀 폰트는 8의 배수 크기에서 가장 선명하다. 폰트 파일이 없으면 기본 글꼴로 대체."""
    px = max(4, int(px))
    if px not in _fonts:
        try:
            _fonts[px] = ImageFont.truetype(FONT_PATH, px)
        except OSError:
            _fonts[px] = ImageFont.load_default(px)
    return _fonts[px]


def _inside(box, x, y):
    return box[0] <= x < box[2] and box[1] <= y < box[3]


def hit_test(x, y, size, state):
    """창 안의 눌린 위치(x, y) -> booth.handle()에 넘길 동작 또는 None."""
    w, h = size
    scale = min(w / BASE_W, h / BASE_H)
    ox, oy = (w - BASE_W * scale) / 2, (h - BASE_H * scale) / 2
    bx, by = (x - ox) / scale, (y - oy) / scale
    if state is State.HOME or state is State.DONE:
        return ("primary",)
    if state is State.SELECT:
        for mode, box in BOX_CARD.items():
            if _inside(box, bx, by):
                return ("mode", mode)
        if _inside(BOX_BACK_SELECT, bx, by):
            return ("back",)
    if state is State.LIVE:
        for name, box in BOX_CHIPS.items():
            if _inside(box, bx, by):
                return ("filter", name)
        if _inside(BOX_SHUTTER, bx, by):
            return ("primary",)
        if _inside(BOX_BACK_LIVE, bx, by):
            return ("back",)
    return None


# ---------------------------------------------------------------- 정적 배경 (한 번만 그림)
_bg_cache = {}


def _background():
    if "bg" not in _bg_cache:
        img = Image.new("RGB", (BASE_W, BASE_H), BG)
        d = ImageDraw.Draw(img)
        for gx in range(0, BASE_W, 20):                     # 희미한 점 격자
            for gy in range(0, BASE_H, 20):
                d.point((gx, gy), fill=BG_DOT)
        d.rectangle((0, 0, BASE_W, 40), fill=PANEL)
        d.line((0, 40, BASE_W, 40), fill=LINE)
        _bg_cache["bg"] = img
    return _bg_cache["bg"].copy()


# ---------------------------------------------------------------- 그림 도구
def _text(d, xy, s, px=8, fill=TEXT, anchor="la"):
    d.text(xy, s, font=_font(px), fill=fill, anchor=anchor)


def _brackets(d, box, color=SILVER, n=14):
    x0, y0, x1, y1 = box
    for (cx, cy, dx, dy) in ((x0, y0, 1, 1), (x1 - 1, y0, -1, 1), (x0, y1 - 1, 1, -1), (x1 - 1, y1 - 1, -1, -1)):
        d.line((cx, cy, cx + dx * n, cy), fill=color, width=2)
        d.line((cx, cy, cx, cy + dy * n), fill=color, width=2)


def _button(d, box, label, active=False, px=8):
    x0, y0, x1, y1 = box
    if active:
        d.rectangle(box, fill=SILVER)
        _text(d, ((x0 + x1) // 2, (y0 + y1) // 2), label, px, BG, "mm")
    else:
        d.rectangle(box, fill=PANEL, outline=LINE, width=2)
        _text(d, ((x0 + x1) // 2, (y0 + y1) // 2), label, px, TEXT, "mm")


def _led(d, cx, cy, color, on=True):
    d.rectangle((cx - 6, cy - 6, cx + 6, cy + 6), outline=LINE, width=2, fill=PANEL)
    if on:
        d.rectangle((cx - 3, cy - 3, cx + 3, cy + 3), fill=color)


def _camera_icon(d, cx, cy, s=1.0, color=SILVER):
    w, h = int(120 * s), int(80 * s)
    d.rectangle((cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2), outline=color, width=3)
    d.rectangle((cx - int(24 * s), cy - h // 2 - int(12 * s), cx + int(24 * s), cy - h // 2), outline=color, width=3)
    r = int(24 * s)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=3)
    r2 = int(10 * s)
    d.ellipse((cx - r2, cy - r2, cx + r2, cy + r2), fill=color)


def _blink(t, hz=2.0):
    return int(t * hz * 2) % 2 == 0


# ---- 배경 별: 천천히 떠다니며 반짝인다 (☆ 글자는 폰트에 없어서 픽셀 도형으로 직접 그린다) ----
STAR_COUNT = 30
STAR_AREA = (0, 48, BASE_W, 432)                     # 머리띠와 아래 로그 글자 줄은 피한다
STAR_SHAPE = ("...#...",
              "..#.#..",
              "###.###",
              ".#...#.",
              "..#.#..",
              ".#...#.",
              "#.....#")                              # ☆ 7x7 픽셀 (속이 빈 별)
_rnd = random.Random(7)
_STARS = [dict(x=_rnd.uniform(0, BASE_W), y=_rnd.uniform(0, STAR_AREA[3] - STAR_AREA[1]),
               vx=_rnd.uniform(3, 10), vy=_rnd.uniform(1, 6), ph=_rnd.random(), hz=_rnd.uniform(0.25, 0.7),
               kind=("star" if i < 9 else "plus" if i < 20 else "dot")) for i in range(STAR_COUNT)]


def _mix(a, b, k):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def _draw_stars(d, clock):
    """별마다 속도와 반짝임 주기가 달라 규칙이 눈에 띄지 않는다.
    ☆ 모양은 밝아질 때만 나타나고 어두워지면 작은 점으로 줄어든다."""
    h = STAR_AREA[3] - STAR_AREA[1]
    for st in _STARS:
        x = int((st["x"] + clock * st["vx"]) % BASE_W)
        y = int(STAR_AREA[1] + (st["y"] + clock * st["vy"]) % h)
        k = 0.5 + 0.5 * math.sin(2 * math.pi * (clock * st["hz"] + st["ph"]))     # 0~1
        color = _mix(LINE, TEXT, k)
        if st["kind"] == "star" and k > 0.45:
            for ry, row in enumerate(STAR_SHAPE):
                for rx, ch in enumerate(row):
                    if ch == "#":
                        d.point((x + rx - 3, y + ry - 3), fill=color)
        elif st["kind"] != "dot" and k > 0.4:
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                d.point((x + dx, y + dy), fill=color)
        else:
            d.point((x, y), fill=color)


def _header(d, frame):
    _text(d, (16, 16), "PHOTOBOOTH // MONO", 8, SILVER)
    dev = frame.devices or {}
    items = (("CAM", dev.get("camera_ok")), ("HAND", dev.get("hand_ok")), ("PRN", dev.get("printer_ok")))
    x = BASE_W - 16
    for name, ok in reversed(items):
        label = f"{name}:{'OK' if ok else ('VIRT' if name == 'PRN' else 'OFF')}"
        _text(d, (x, 16), label, 8, TEXT if ok else DIM, "ra")
        x -= len(label) * 8 + 16


def _footer(d, frame, lines):
    """아래쪽 기계 로그. 알림이 있으면 빨간 글자로 바꿔 보여 준다."""
    if frame.notice:
        text = frame.notice if len(frame.notice) <= 56 else frame.notice[:55] + "~"
        _text(d, (16, 452), "! " + text, 8, ERR)
        return
    for i, line in enumerate(lines[-2:]):
        _text(d, (16, 440 + i * 16), "> " + line, 8, DIM if i == 0 and len(lines) > 1 else SILVER)


# ---------------------------------------------------------------- 화면별
def _draw_home(d, frame, t):
    _camera_icon(d, 400, 150, 1.3)
    _text(d, (400, 250), "PHOTOBOOTH", 48, TEXT, "mm")
    d.line((200, 290, 600, 290), fill=LINE)
    _text(d, (400, 316), "SYSTEM READY" + ("_" if _blink(t, 1.0) else " "), 16, SILVER, "mm")
    if _blink(t, 1.0):
        _text(d, (400, 386), "TOUCH TO START", 16, TEXT, "mm")
    _footer(d, frame, ["BOOT OK", "WAITING FOR INPUT"])


def _strip_icon(d, box, n, active):
    x0, y0, x1, y1 = box
    color = TEXT if active else SILVER
    if n == 1:
        d.rectangle((x0 + 20, y0 + 6, x1 - 20, y1 - 6), outline=color, width=3)
        return
    cell = (y1 - y0 - 3 * 6) // 4
    for i in range(4):
        top = y0 + i * (cell + 6)
        d.rectangle((x0 + 28, top, x1 - 28, top + cell), outline=color, width=3)


def _draw_select(d, frame, t):
    _text(d, (400, 84), "SELECT MODE", 16, TEXT, "mm")
    labels = {1: ("1 CUT", "SINGLE PHOTO"), 4: ("4 CUT", "PHOTO STRIP")}
    for mode, box in BOX_CARD.items():
        active = frame.mode == mode
        d.rectangle(box, fill=PANEL, outline=SILVER if active else LINE, width=2)
        if active:
            _brackets(d, box, TEXT)
        _strip_icon(d, (box[0] + 40, box[1] + 24, box[2] - 40, box[1] + 150), mode, active)
        _text(d, ((box[0] + box[2]) // 2, box[1] + 182), labels[mode][0], 24, TEXT, "mm")
        _text(d, ((box[0] + box[2]) // 2, box[1] + 216), labels[mode][1], 8, DIM, "mm")
    _button(d, BOX_BACK_SELECT, "BACK")
    _footer(d, frame, ["MODE SELECT", f"CURRENT: {frame.mode} CUT"])


def _draw_right_live(d, frame):
    _text(d, (548, 66), "FILTER", 8, DIM)
    for name, box in BOX_CHIPS.items():
        _button(d, box, FILTER_NAMES[name], active=(frame.filter_name == name))
    _text(d, (548, 268), f"MODE {frame.mode} CUT", 8, SILVER)
    d.rectangle(BOX_SHUTTER, fill=TEXT)
    cx, cy = BOX_SHUTTER[0] + 40, (BOX_SHUTTER[1] + BOX_SHUTTER[3]) // 2
    d.ellipse((cx - 14, cy - 14, cx + 14, cy + 14), outline=BG, width=3)
    d.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), fill=BG)
    _text(d, (cx + 36, cy), "SHUTTER", 16, BG, "lm")
    _button(d, BOX_BACK_LIVE, "BACK")


def _draw_right_shooting(d, frame):
    _text(d, (548, 66), "SHOT", 8, DIM)
    _text(d, (548, 84), f"{min(frame.shots_done + (1 if frame.state in (State.COUNTDOWN, State.FLASH) else 0), frame.mode)}/{frame.mode}",
          24, TEXT)
    _text(d, (548, 130), FILTER_NAMES.get(frame.filter_name, frame.filter_name.upper()), 8, SILVER)
    cols = 2
    tw, th = 112, 84
    for i in range(frame.mode):
        x = 548 + (i % cols) * (tw + 12)
        y = 156 + (i // cols) * (th + 12)
        d.rectangle((x, y, x + tw, y + th), fill=PANEL, outline=LINE, width=2)
        if i < len(frame.thumbs):
            th_img = frame.thumbs[i].convert("RGB")
            fitted = ImageOps.contain(th_img, (tw - 4, th - 4))
            yield_box = (x + 2 + (tw - 4 - fitted.width) // 2, y + 2 + (th - 4 - fitted.height) // 2)
            d._image.paste(fitted, yield_box)
        else:
            _text(d, (x + tw // 2, y + th // 2), str(i + 1), 16, DIM, "mm")


def _draw_shooting_frame(d, frame, t):
    d.rectangle(PHOTO_BOX, fill=PANEL, outline=LINE, width=2)
    _brackets(d, PHOTO_BOX, SILVER)
    if frame.image is None:
        _text(d, ((PHOTO_BOX[0] + PHOTO_BOX[2]) // 2, (PHOTO_BOX[1] + PHOTO_BOX[3]) // 2), "NO CAMERA", 24, DIM, "mm")


def _live_log(frame):
    return ["CAM STREAM " + ("OK" if (frame.devices or {}).get("camera_ok") else "VIRTUAL"),
            f"FILTER: {FILTER_NAMES.get(frame.filter_name, '?')}  MODE: {frame.mode} CUT"]


# ---------------------------------------------------------------- 배출 연출
def _spring(t):
    """감쇠 스프링: 0에서 시작해 한 번 15% 정도 지나쳤다가 1에 안착한다."""
    if t <= 0:
        return 0.0
    return 1.0 - math.exp(-4.0 * t) * math.cos(7.0 * t)


_strip_cache = {}


def _strip_steps(strip):
    """스트립을 '현상' 단계(하얗고 흐림 -> 선명) 6장으로 미리 만들어 둔다. 프레임마다 필터를 돌리지 않기 위해서다."""
    key = id(strip)
    if _strip_cache.get("key") != key:
        base = ImageOps.contain(strip.convert("L"), STRIP_MAX, Image.LANCZOS).convert("RGB")
        steps = []
        for white, blur in ((0.95, 5), (0.8, 4), (0.6, 3), (0.35, 2), (0.15, 1), (0.0, 0)):
            im = base
            if blur:
                im = im.filter(ImageFilter.GaussianBlur(blur))
            if white:
                im = Image.blend(im, Image.new("RGB", im.size, (255, 255, 255)), white)
            steps.append(im)
        _strip_cache.update(key=key, steps=steps, ref=strip)   # ref: id 재사용을 막으려고 객체를 붙잡아 둔다
    return _strip_cache["steps"]


def _draw_eject(d, frame, t):
    """배출구에서 스트립이 튕기며 나오고, 하얗게 흐린 상태에서 선명해지며, 끝나면 표시등이 켜진다."""
    done = frame.state is State.DONE
    tt = EJECT_TOTAL if done else t
    steps = _strip_steps(frame.strip) if frame.strip is not None else None
    d.rectangle(SLOT, fill=BG, outline=SILVER, width=2)
    d.rectangle((SLOT[0] - 24, SLOT[1] - 8, SLOT[2] + 24, SLOT[1]), fill=PANEL, outline=LINE)

    if steps:
        dev_p = 1.0 if done else min(1.0, max(0.0, (tt - 0.5) / EJECT_DEVELOP))
        img = steps[min(len(steps) - 1, int(dev_p * len(steps)))]
        slide = 1.0 if done else _spring(min(tt, EJECT_SLIDE + 0.5))
        h = img.height
        bottom = STRIP_TOP + h * slide                       # 맨 아래 끝(먼저 나오는 쪽)의 위치
        x = (BASE_W - img.width) // 2
        top = bottom - h
        clip_y = STRIP_TOP                                   # 배출구 아래쪽만 보이게 자른다
        crop_from = max(0, int(clip_y - top))
        if crop_from < h:
            d._image.paste(img.crop((0, crop_from, img.width, h)), (x, int(top) + crop_from))
        d.rectangle((x - 2, clip_y - 2, x + img.width + 1, clip_y - 1), fill=LINE)

    # 빛 입자: 배출 직후와 완료 순간에 한 번씩 튄다
    for t0 in (0.15, EJECT_SLIDE + EJECT_DEVELOP):
        age = tt - t0
        if 0 <= age < 0.7:
            rnd = random.Random(int(t0 * 100))
            for _ in range(14):
                ang = rnd.uniform(math.pi * 0.05, math.pi * 0.95)
                sp = rnd.uniform(60, 190)
                px = 400 + rnd.uniform(-130, 130) + math.cos(ang) * sp * age * (1 if rnd.random() < .5 else -1)
                py = SLOT[3] + 2 + math.sin(ang) * sp * age + 140 * age * age
                if py < BASE_H - 40:
                    c = TEXT if age < 0.35 else SILVER
                    d.rectangle((px, py, px + 2, py + 2), fill=c)

    # 왼쪽: 기계 로그 / 오른쪽: 표시등
    log = [("PRINT JOB START", 0.0), ("1-BIT DITHER OK", 0.3), ("EJECT STRIP", 0.6),
           ("DEVELOPING", 1.2), ("COMPLETE", EJECT_SLIDE + EJECT_DEVELOP)]
    y = 100
    for line, at in log:
        if tt >= at:
            _text(d, (24, y), "> " + line, 8, TEXT if line == "COMPLETE" else SILVER)
            y += 20
    complete = done or tt >= EJECT_SLIDE + EJECT_DEVELOP
    if complete:
        _led(d, 640, 110, LED_OK)
        _text(d, (660, 106), "READY", 8, LED_OK)
    else:
        _led(d, 640, 110, LED_BUSY, on=_blink(tt, 4.0))
        _text(d, (660, 106), "PRINTING", 8, LED_BUSY)


def _draw_done(d, frame, t):
    _draw_eject(d, frame, t)
    _text(d, (400, 400), "TAKE YOUR PHOTO", 16, TEXT, "mm")
    if _blink(t, 1.0):
        _text(d, (400, 430), "TOUCH TO FINISH", 8, SILVER, "mm")


# ---------------------------------------------------------------- 합치기
def _base(frame, t, clock=0.0):
    img = _background()
    d = ImageDraw.Draw(img)
    s = frame.state
    _draw_stars(d, clock)                  # 배경 -> 별 -> 그 위에 패널/글자 순서로 그린다
    _header(d, frame)

    if s is State.HOME:
        _draw_home(d, frame, t)
    elif s is State.SELECT:
        _draw_select(d, frame, t)
    elif s is State.LIVE:
        _draw_shooting_frame(d, frame, t)
        _draw_right_live(d, frame)
        _footer(d, frame, _live_log(frame))
    elif s in (State.COUNTDOWN, State.FLASH, State.INTERVAL):
        _draw_shooting_frame(d, frame, t)
        _draw_right_shooting(d, frame)
        log = {State.COUNTDOWN: ["SHUTTER ARMED", "T-MINUS " + f"{max(0, math.ceil(frame.remaining))}"],
               State.FLASH: ["SHUTTER CLICK", "CAPTURE"],
               State.INTERVAL: ["SHUTTER CLICK", "GET READY"]}[s]
        _footer(d, frame, log)
    elif s is State.EJECT:
        _draw_eject(d, frame, t)
        _footer(d, frame, ["EJECT STRIP", "DO NOT TOUCH"])
    elif s is State.DONE:
        _draw_done(d, frame, t)
        _footer(d, frame, ["PRINT COMPLETE", "RETURN TO HOME ON TOUCH"])
    return img


def render(frame, size, t=None):
    """booth.Frame -> 화면 크기(size)에 맞춘 PIL 이미지. t는 깜빡임용 시간(초)이며, 상태별 연출은 frame.t를 쓴다."""
    clock = time.monotonic() if t is None else t
    anim_t = frame.t
    base = _base(frame, anim_t if frame.state in (State.EJECT, State.DONE) else clock, clock)

    w, h = size
    scale = min(w / BASE_W, h / BASE_H)
    tw, th = max(1, int(BASE_W * scale)), max(1, int(BASE_H * scale))
    ox, oy = (w - tw) // 2, (h - th) // 2
    canvas = Image.new("RGB", (w, h), BG)
    cd = ImageDraw.Draw(canvas)
    cd.rectangle((0, 0, w, oy + int(40 * scale)), fill=PANEL)                  # 비율이 달라도 머리띠는 끝까지
    canvas.paste(base.resize((tw, th), Image.NEAREST), (ox, oy))

    if frame.image is not None and frame.state in (State.LIVE, State.COUNTDOWN, State.FLASH, State.INTERVAL):
        bx0, by0, bx1, by1 = PHOTO_BOX
        box = (ox + int((bx0 + 2) * scale), oy + int((by0 + 2) * scale), ox + int((bx1 - 2) * scale), oy + int((by1 - 2) * scale))
        bw, bh = box[2] - box[0], box[3] - box[1]
        fitted = ImageOps.contain(frame.image.convert("RGB"), (bw, bh), Image.BILINEAR)
        canvas.paste(fitted, (box[0] + (bw - fitted.width) // 2, box[1] + (bh - fitted.height) // 2))
        pbox = (box[0], box[1], box[2], box[3])

        if frame.state is State.COUNTDOWN and frame.remaining > 0:
            n = math.ceil(frame.remaining)
            p = min(1.0, max(0.0, 1.0 - (frame.remaining - (n - 1))))          # 이 숫자가 뜬 뒤 지난 비율 0~1
            sc = 1.4 - 0.8 * p
            alpha = int(255 * (1.0 - 0.85 * p))
            layer = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
            ld, fnt = ImageDraw.Draw(layer), _font(144 * scale * sc)
            off = max(2, int(5 * scale))
            ld.text((bw // 2 + off, bh // 2 + off), str(n), font=fnt, fill=BG + (alpha,), anchor="mm")   # 그림자
            ld.text((bw // 2, bh // 2), str(n), font=fnt, fill=TEXT + (alpha,), anchor="mm")
            canvas.paste(layer, (box[0], box[1]), layer)

        flash = 0.0
        if frame.state is State.FLASH:
            flash = 0.85
        elif frame.state is State.INTERVAL and frame.t < 0.3:
            flash = 0.5 * (1.0 - frame.t / 0.3)
        if flash > 0:
            white = Image.new("RGB", (pbox[2] - pbox[0], pbox[3] - pbox[1]), (255, 255, 255))
            region = canvas.crop(pbox)
            canvas.paste(Image.blend(region, white, flash), (pbox[0], pbox[1]))
    return canvas
